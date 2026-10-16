"""Gera os exemplos da documentação rodando os cenários de dados/exemplos.json no sistema REAL.

Uso:
  python gerar_exemplos.py               roda todos os cenários
  python gerar_exemplos.py feliz manual  roda só estes
  python gerar_exemplos.py --lista       lista os cenários

Saídas: logs/exemplos/<cenário>/trajetoria.jsonl (um por conversa; a segunda conversa é <cenário>-2...) e
logs/exemplos/resultado.json, com a entrada exata, a saída completa e o carimbo (commit, data, modelo, código limpo).

Cuidados:
  - Cada cenário roda num processo próprio, porque os tetos e prazos (MAX_TURNOS, LLM_TIMEOUT, PRAZO_APROVACAO_HORAS)
    são lidos na importação.
  - O banco, o índice do Chroma e o checkpoint são copiados antes e RESTAURADOS depois de cada cenário: rodar isto não
    deixa memória, peças gravadas nem conversas para trás.
  - Os exemplos só identificam o código se a árvore estiver limpa (`codigo_limpo: true` no resultado). Commite antes.
  - Precisa do modelo no ar (Ollama em MODE=local, com AI_MODEL=<nome com a tag>, ou a Groq em MODE=remote).
  - Os cenários com pausa raspam o catálogo da Chevrolet ao vivo (~35 s cada) e exigem o Chromium do sistema.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

DB = RAIZ / 'databases'
LOGS = RAIZ / 'logs'
CENARIOS = json.loads((RAIZ / 'dados' / 'exemplos.json').read_text(encoding='utf-8'))['cenarios']
MARCADOR = 'RESULTADO_JSON:'
TIMEOUT_CENARIO_S = 900


# ----------------------------------------------------------------------------- processo filho

def executar_cenario(cen: dict) -> dict:
    """Roda as conversas do cenário no sistema real e devolve o que aconteceu em cada mensagem."""
    from langchain_core.messages import HumanMessage

    from src.grafo import RECURSION_LIMIT
    from src.main import encerrar_se_esquecido, interpretar_aprovacao, processar

    usuario = cen['usuario']
    turnos, verificacoes = [], []
    for i, conversa in enumerate(cen['conversas']):
        sessao = cen['id'] if i == 0 else f"{cen['id']}-{i + 1}"
        thread_id = f'{usuario}:{sessao}'
        cfg = {'configurable': {'thread_id': thread_id}, 'recursion_limit': RECURSION_LIMIT}
        fila = list(conversa)
        while fila:
            passo = fila.pop(0)
            if passo.get('verificar_remocao'):
                # o resultado.json da demonstração guarda a transcrição do usuário de teste de propósito
                saida = subprocess.run([sys.executable, str(RAIZ / 'verificar_remocao.py'), usuario,
                                        '--ignorar', 'logs/exemplos/resultado.json'],
                                       capture_output=True, text=True, cwd=RAIZ)
                verificacoes.append({'usuario': usuario, 'codigo_de_saida': saida.returncode, 'saida': saida.stdout.strip()})
                continue
            if 'usuario' not in passo:
                raise ValueError(f"passo 'humano' sem pausa para recebê-lo: {passo}")

            pausas = []

            def decisor(payload):
                if not fila or 'humano' not in fila[0]:
                    return None  # ninguém responde: a pausa fica salva, como ao fechar o terminal
                linha = fila.pop(0)['humano']
                if payload['acao'] == 'esquecer_dados':
                    resposta = {'decisao': linha} if linha in ('confirmar', 'cancelar') else None
                else:
                    resposta = interpretar_aprovacao(linha, payload['candidatas'])
                pausas.append({'acao': payload['acao'], 'texto_mostrado': payload['texto'], 'resposta_digitada': linha})
                return resposta

            inicio = time.time()
            resultado = processar({'mensagens': [HumanMessage(passo['usuario'])]}, cfg, decisor)
            turno = {'conversa': i + 1, 'sessao': sessao, 'usuario': usuario, 'entrada': passo['usuario'], 'pausas': pausas,
                     'segundos': round(time.time() - inicio, 1)}
            if resultado is None:
                turno['pausa_pendente'] = True
            else:
                saida = resultado['saida']
                turno.update({'motivo': resultado['motivo_termino'], 'situacao': saida['situacao'], 'suficiencia': saida['suficiencia'],
                              'fonte': [f['tipo'] for f in saida['fonte']], 'chamadas_ao_modelo': len(resultado.get('passos') or []),
                              'resultado': saida['resultado'], 'saida': saida})
                if encerrar_se_esquecido(resultado, thread_id):
                    turno['conversa_apagada_ao_terminar'] = True
            turnos.append(turno)
    return {'turnos': turnos, 'verificacoes': verificacoes}


def avaliar(esperado: dict, ultimo: dict) -> bool:
    if 'motivo' in esperado and ultimo.get('motivo') != esperado['motivo']:
        return False
    return esperado.get('contem', '').lower() in ultimo.get('resultado', '').lower()


# ----------------------------------------------------------------------------- processo pai

def copiar_estado(origem: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem / 'db.sqlite', destino / 'db.sqlite')
    shutil.copytree(origem / 'chroma_db', destino / 'chroma_db')
    for f in origem.glob('checkpoints.sqlite*'):
        shutil.copy2(f, destino / f.name)


def restaurar_estado(copia: Path) -> None:
    shutil.copy2(copia / 'db.sqlite', DB / 'db.sqlite')
    shutil.rmtree(DB / 'chroma_db', ignore_errors=True)
    shutil.copytree(copia / 'chroma_db', DB / 'chroma_db')
    for f in DB.glob('checkpoints.sqlite*'):
        f.unlink()
    for f in copia.glob('checkpoints.sqlite*'):
        shutil.copy2(f, DB / f.name)


def rodar_pai(ids: list[str]) -> int:
    from src.trajetoria import estado_do_codigo
    from src.util import modelo_em_uso

    escolhidos = [c for c in CENARIOS if not ids or c['id'] in ids]
    desconhecidos = set(ids) - {c['id'] for c in CENARIOS}
    if desconhecidos:
        print('Cenários inexistentes:', sorted(desconhecidos))
        return 2

    carimbo = estado_do_codigo()
    if not carimbo['codigo_limpo']:
        print('ATENÇÃO: o código tem alterações não commitadas:', carimbo['arquivos_alterados'])
        print('         os exemplos NÃO identificarão o código que os gerou. Commite antes de usá-los na documentação.\n')

    remocoes = LOGS / '_remocoes.jsonl'
    tinha_remocoes = remocoes.exists()
    copia = Path(tempfile.mkdtemp(prefix='exemplos_estado_'))
    copiar_estado(DB, copia)
    arquivo = LOGS / 'exemplos' / 'resultado.json'
    anterior = json.loads(arquivo.read_text(encoding='utf-8'))['cenarios'] if arquivo.exists() else {}
    cenarios = dict(anterior)
    auditorias = {}
    try:
        for cen in escolhidos:
            print(f"== {cen['id']}: {cen['titulo']}", flush=True)
            for i in range(len(cen['conversas'])):
                shutil.rmtree(LOGS / cen['usuario'] / (cen['id'] if i == 0 else f"{cen['id']}-{i + 1}"), ignore_errors=True)
            env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', **cen.get('env', {})}
            inicio = time.time()
            try:
                proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--filho', cen['id']],
                                      capture_output=True, text=True, env=env, cwd=RAIZ, timeout=TIMEOUT_CENARIO_S)
                linhas = [l for l in proc.stdout.splitlines() if l.startswith(MARCADOR)]
                if not linhas:
                    corpo = {'erro': 'o processo filho não devolveu resultado', 'stderr': proc.stderr[-1500:]}
                else:
                    corpo = json.loads(linhas[-1][len(MARCADOR):])
            except subprocess.TimeoutExpired:
                corpo = {'erro': f'passou de {TIMEOUT_CENARIO_S} s'}
            finally:
                restaurar_estado(copia)
            if remocoes.exists():
                auditorias[cen['id']] = remocoes.read_text(encoding='utf-8').splitlines()[-1:]
            ultimo = (corpo.get('turnos') or [{}])[-1]
            varreduras_ok = all(v['codigo_de_saida'] == 0 for v in corpo.get('verificacoes', []))
            ok = 'erro' not in corpo and avaliar(cen['esperado'], ultimo) and varreduras_ok
            cenarios[cen['id']] = {'titulo': cen['titulo'], 'enunciado': cen['enunciado'], 'usuario': cen['usuario'],
                                   'env': cen.get('env', {}), 'esperado': cen['esperado'], 'ok': ok,
                                   'segundos': round(time.time() - inicio, 1), 'auditoria_da_remocao': auditorias.get(cen['id']),
                                   **corpo}
            print(f"   {'OK   ' if ok else 'FALHA'} motivo={ultimo.get('motivo')} ({cenarios[cen['id']]['segundos']} s)\n"
                  f"        {str(ultimo.get('resultado', corpo.get('erro')))[:150].replace(chr(10), ' | ')}", flush=True)
    finally:
        restaurar_estado(copia)
        shutil.rmtree(copia, ignore_errors=True)
        if remocoes.exists() and not tinha_remocoes:
            remocoes.unlink()  # só as remoções de demonstração deste script; o resultado guarda a linha de auditoria

    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps({**carimbo, 'data': time.strftime('%Y-%m-%d'), 'modelo': modelo_em_uso(), 'cenarios': cenarios},
                                  ensure_ascii=False, indent=2), encoding='utf-8')
    rodados = [cenarios[c['id']] for c in escolhidos]
    print(f"\n{sum(1 for r in rodados if r['ok'])}/{len(rodados)} cenários com o desfecho esperado. Resultado em {arquivo}")
    return 0


if __name__ == '__main__':
    argumentos = sys.argv[1:]
    if argumentos[:1] == ['--filho']:
        cenario = next(c for c in CENARIOS if c['id'] == argumentos[1])
        print(MARCADOR + json.dumps(executar_cenario(cenario), ensure_ascii=False, default=str))
        sys.exit(0)
    if argumentos[:1] == ['--lista']:
        for c in CENARIOS:
            print(f"{c['id']:<22} {c['titulo']}")
        sys.exit(0)
    sys.exit(rodar_pai(argumentos))
