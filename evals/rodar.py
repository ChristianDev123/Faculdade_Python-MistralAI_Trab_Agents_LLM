"""Roda o golden dataset (evals/casos.json) no sistema entregue, pelo `processar` de src/main.py, e grava a rodada.

Uso:
  python -m evals.rodar [--versao X.Y.Z] [--casos id1 id2 ...]

Cada caso roda num processo próprio, com um usuário próprio, e os bancos são restaurados depois dele. Três níveis:
  determinístico  motivo de término, texto da resposta, schema de Saida
  trajetória      as ferramentas chamadas, lidas no trace
  resultado       as linhas gravadas nos bancos, contadas antes e depois

Grava em evals/resultados/v<versão>/: resultado.json (o carimbo e cada caso) e traces.jsonl (os traces das execuções).
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from gerar_exemplos import DB, LOGS, MARCADOR, RAIZ, TIMEOUT_CENARIO_S, copiar_estado, executar_cenario, restaurar_estado

DATASET = json.loads((RAIZ / 'evals' / 'casos.json').read_text(encoding='utf-8'))
TABELAS = ('pecas_automoveis', 'log_interacoes', 'memoria_semantica')


def contar_linhas() -> dict:
    with sqlite3.connect(DB / 'db.sqlite') as conn:
        return {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABELAS}


def ha_duplicatas() -> bool:
    with sqlite3.connect(DB / 'db.sqlite') as conn:
        return conn.execute('SELECT COUNT(*) FROM (SELECT 1 FROM pecas_automoveis GROUP BY nm_peca, codigo_peca, modelo, ano_fabricacao, motorizacao '
                            'HAVING COUNT(*) > 1)').fetchone()[0] > 0


def texto_da_memoria() -> str:
    with sqlite3.connect(DB / 'db.sqlite') as conn:
        return ' '.join(str(l) for t in ('log_interacoes', 'memoria_semantica') for l in conn.execute(f'SELECT * FROM {t}'))


def ler_traces(usuario: str) -> list[dict]:
    spans = []
    for arquivo in sorted((LOGS / usuario).rglob('trace.jsonl')):
        spans += [json.loads(l) for l in arquivo.read_text(encoding='utf-8').splitlines() if l.strip()]
    return sorted(spans, key=lambda s: s['start_time'])


def avaliar(esperado: dict, corpo: dict, spans: list[dict], novas: dict, duplicatas: bool, memoria: str) -> dict:
    """As propriedades conferidas no caso, por nível: {nível: {propriedade: passou}}."""
    from pydantic import ValidationError
    from src.contrato import Saida

    ultimo = (corpo.get('turnos') or [{}])[-1]
    texto = ultimo.get('resultado') or ''
    niveis = {'deterministico': {}, 'trajetoria': {}, 'resultado': {}}

    d = niveis['deterministico']
    d['executou'] = 'erro' not in corpo
    if 'motivo' in esperado:
        validos = esperado['motivo'] if isinstance(esperado['motivo'], list) else [esperado['motivo']]
        d['motivo'] = ultimo.get('motivo') in validos
    if 'contem' in esperado:
        d['contem'] = esperado['contem'].lower() in texto.lower()
    if 'regex' in esperado:
        d['regex'] = re.search(esperado['regex'], texto, re.IGNORECASE) is not None
    if 'nao_contem' in esperado:
        d['nao_contem'] = esperado['nao_contem'].lower() not in texto.lower()
    if 'pausa_pendente' in esperado:
        d['pausa_pendente'] = bool(ultimo.get('pausa_pendente')) == esperado['pausa_pendente']
    if 'saida' in ultimo:
        try:
            Saida.model_validate(ultimo['saida'])
            d['schema_saida'] = True
        except ValidationError:
            d['schema_saida'] = False

    ferramentas = [s['attributes']['gen_ai.tool.name'] for s in spans if 'gen_ai.tool.name' in s['attributes']]
    for nome in esperado.get('usa', []):
        niveis['trajetoria'][f'usa {nome}'] = nome in ferramentas
    for nome in esperado.get('nao_usa', []):
        niveis['trajetoria'][f'nao usa {nome}'] = nome not in ferramentas

    r = niveis['resultado']
    for tabela, quantas in esperado.get('linhas_novas', {}).items():
        r[f'linhas novas em {tabela} = {quantas}'] = novas[tabela] == quantas
    if 'nao_grava' in esperado:
        r[f"memoria sem {esperado['nao_grava']}"] = esperado['nao_grava'] not in memoria
    if esperado.get('sem_duplicatas'):
        r['sem duplicatas em pecas_automoveis'] = not duplicatas
    if esperado.get('varredura_limpa'):
        verificacoes = corpo.get('verificacoes') or []
        r['varredura sem o identificador'] = bool(verificacoes) and all(v['codigo_de_saida'] == 0 for v in verificacoes)
    return niveis


def rodar_caso(caso: dict, usuario: str) -> tuple[dict, list[dict]]:
    shutil.rmtree(LOGS / usuario, ignore_errors=True)
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', **caso.get('env', {})}
    try:
        proc = subprocess.run([sys.executable, '-m', 'evals.rodar', '--filho', caso['id'], usuario], capture_output=True,
                              text=True, encoding='utf-8', env=env, cwd=RAIZ, timeout=TIMEOUT_CENARIO_S)
        linhas = [l for l in proc.stdout.splitlines() if l.startswith(MARCADOR)]
        corpo = json.loads(linhas[-1][len(MARCADOR):]) if linhas else {'erro': proc.stderr[-1500:]}
    except subprocess.TimeoutExpired:
        corpo = {'erro': f'passou de {TIMEOUT_CENARIO_S} s'}
    return corpo, ler_traces(usuario)


def rodar(versao: str, ids: list[str]) -> int:
    from src.registrador import Registrador
    from src.trajetoria import estado_do_codigo
    from src.util import modelo_em_uso

    casos = [c for c in DATASET['casos'] if not ids or c['id'] in ids]
    destino = RAIZ / 'evals' / 'resultados' / (f'v{versao}' if not ids else f'v{versao}-parcial')
    destino.mkdir(parents=True, exist_ok=True)
    carimbo = estado_do_codigo()
    if not carimbo['codigo_limpo']:
        print('ATENÇÃO: há alterações não commitadas:', carimbo['arquivos_alterados'], '\n')

    remocoes = LOGS / '_remocoes.jsonl'
    tinha_remocoes = remocoes.exists()
    copias = Path(tempfile.mkdtemp(prefix='evals_estado_'))
    copiar_estado(DB, copias / 'original')
    resultados, traces = {}, []
    try:
        Registrador()  # aplica as migrações antes da contagem de linhas
        antes = contar_linhas()
        copiar_estado(DB, copias / 'migrado')
        for caso in casos:
            usuario = f"evals-{versao}-{caso['id']}"
            inicio = time.time()
            corpo, spans = rodar_caso(caso, usuario)
            depois, duplicatas, memoria = contar_linhas(), ha_duplicatas(), texto_da_memoria()
            novas = {t: depois[t] - antes[t] for t in TABELAS}
            restaurar_estado(copias / 'migrado')
            shutil.rmtree(LOGS / usuario, ignore_errors=True)
            niveis = avaliar(caso['esperado'], corpo, spans, novas, duplicatas, memoria)
            ok = all(all(n.values()) for n in niveis.values())
            traces += spans
            resultados[caso['id']] = {'classe': caso['classe'], 'origem': caso['origem'], 'ok': ok, 'niveis': niveis, 'linhas_novas': novas,
                                      'segundos': round(time.time() - inicio, 1), **corpo}
            falhas = [p for n in niveis.values() for p, passou in n.items() if not passou]
            print(f"{'OK   ' if ok else 'FALHA'} {caso['classe']:<8} {caso['id']:<28} {resultados[caso['id']]['segundos']:>6} s  {falhas or ''}", flush=True)
    finally:
        restaurar_estado(copias / 'original')
        shutil.rmtree(copias, ignore_errors=True)
        if remocoes.exists() and not tinha_remocoes:
            remocoes.unlink()

    (destino / 'resultado.json').write_text(json.dumps(
        {**carimbo, 'versao': versao, 'data': time.strftime('%Y-%m-%d'), 'modelo': modelo_em_uso(), 'contexto_ollama': os.environ.get('CONTEXTO_OLLAMA', 'não informado'),
         'dataset': DATASET['versao'], 'casos': resultados}, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    with open(destino / 'traces.jsonl', 'w', encoding='utf-8') as f:
        for span in traces:
            f.write(json.dumps(span, ensure_ascii=False) + '\n')
    print(f"\n{sum(r['ok'] for r in resultados.values())}/{len(resultados)} casos passaram. Resultado em {destino}")
    return 0


def main() -> int:
    if sys.argv[1:2] == ['--filho']:
        caso = next(c for c in DATASET['casos'] if c['id'] == sys.argv[2])
        print(MARCADOR + json.dumps(executar_cenario({**caso, 'usuario': sys.argv[3]}), ensure_ascii=False, default=str))
        return 0
    from src.trajetoria import VERSAO_SISTEMA
    parser = argparse.ArgumentParser(description='Roda o golden dataset no sistema entregue.')
    parser.add_argument('--versao', default=VERSAO_SISTEMA)
    parser.add_argument('--casos', nargs='*', default=[])
    args = parser.parse_args()
    if args.versao != VERSAO_SISTEMA:
        print(f'O código está na versão {VERSAO_SISTEMA}, não em {args.versao}.')
        return 2
    return rodar(args.versao, args.casos)


if __name__ == '__main__':
    sys.exit(main())
