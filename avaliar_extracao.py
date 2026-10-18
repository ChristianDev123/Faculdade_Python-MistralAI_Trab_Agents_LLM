"""Avalia o nó `extrair` (intenção e ficha do veículo) com dados/casos_extracao.json.

Uso:
  python avaliar_extracao.py [rodadas]     linha de base do prompt atual (padrão: 3 rodadas)

Chama a função REAL do nó (`nos.extrair`), com o prompt e as regras aprendidas que estão em src/prompts/, e a
normalização em código (a montadora sai do nome do modelo e é completada pela lista de modelos conhecidos). Não grava
log de trajetória nem toca nos bancos. O modelo local não é determinístico nem com temperature=0, por isso as rodadas.

Vazamento: um caso cuja entrada o prompt já mostra como exemplo (semelhança >= 0,80, calculada na hora contra o prompt
ORIGINAL) é contado à parte. A medida que vale é a dos casos que o prompt nunca viu (`heldout`).

Acerto da intenção: igual ao esperado. Acerto da ficha: intenção certa E modelo, ano, motorização, montadora e nome da
peça iguais (sem diferenciar maiúsculas nem acentos); a peça só conta quando a intenção é PECA; `duvida` só precisa estar
preenchida quando a intenção é MANUAL.
"""
import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

CASOS = json.loads((RAIZ / 'dados' / 'casos_extracao.json').read_text(encoding='utf-8'))['casos']
CAMPOS = ('modelo', 'ano', 'motorizacao', 'fabricante', 'nome_peca')


def _norm(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = ''.join(c for c in unicodedata.normalize('NFKD', v.lower().strip()) if not unicodedata.combining(c))
        return s or None
    return v


def _chave(texto: str) -> str:
    t = ''.join(c for c in unicodedata.normalize('NFKD', texto.lower()) if not unicodedata.combining(c))
    return ' '.join(sorted(re.sub(r'\b(meu|minha|do|da|de|o|a)\b', ' ', re.sub(r'[^a-z0-9 ]', ' ', t)).split()))


def casos_vazados() -> list[int]:
    """Casos cuja entrada já aparece (ou quase) como exemplo no prompt original."""
    prompt = (RAIZ / 'src' / 'prompts' / 'extracao.md').read_text(encoding='utf-8')
    exemplos = [re.sub(r'^"|"$', '', e) for e in re.findall(r'(?:Mensagem|Conversa): (.+)', prompt)]
    vazados = []
    for c in CASOS:
        if len(c['conversa']) > 1:
            texto = ' / '.join(('usuário "' if p == 'usuario' else 'atendente "') + t + '"' for p, t in c['conversa'])
        else:
            texto = c['conversa'][0][1]
        if max(difflib.SequenceMatcher(None, _chave(texto), _chave(e)).ratio() for e in exemplos) >= 0.80:
            vazados.append(c['id'])
    return vazados


VAZADOS = casos_vazados()


def preparar_nos():
    """Isola o nó do resto do sistema: sem log, sem bancos. Devolve o módulo `nos` já preparado."""
    from src import nos
    from src.config import client
    nos._log = lambda *a, **k: None
    nos.servicos = lambda: SimpleNamespace(client=client)
    return nos


def montar_estado(conversa):
    from langchain_core.messages import AIMessage, HumanMessage
    return {'mensagens': [HumanMessage(t) if papel == 'usuario' else AIMessage(t) for papel, t in conversa], 'veiculo': {}}


def avaliar_caso(nos, caso) -> dict:
    cfg = {'configurable': {'thread_id': 'avaliacao-extracao:caso'}}
    saida = nos.extrair.__wrapped__(montar_estado(caso['conversa']), cfg)
    esperado = caso['esperado']
    if 'erro' in saida:
        return {'id': caso['id'], 'grupo': caso['grupo'], 'intencao_ok': False, 'ficha_ok': False,
                'erro': saida['erro']['mensagem'], 'divergencias': {}}
    v = saida.get('veiculo') or {}
    obtido = {'modelo': v.get('modelo'), 'ano': v.get('ano'), 'motorizacao': v.get('motorizacao'), 'fabricante': v.get('fabricante'),
              'nome_peca': saida.get('nome_peca')}
    intencao_ok = saida['intencao'] == esperado['intencao']
    divergencias = {}
    for campo in CAMPOS:
        if campo == 'nome_peca' and esperado['intencao'] != 'PECA':
            continue
        if _norm(obtido[campo]) != _norm(esperado[campo]):
            divergencias[campo] = {'obtido': obtido[campo], 'esperado': esperado[campo]}
    if esperado['intencao'] == 'MANUAL' and not saida.get('duvida'):
        divergencias['duvida'] = {'obtido': saida.get('duvida'), 'esperado': 'preenchida'}
    return {'id': caso['id'], 'grupo': caso['grupo'], 'intencao_ok': intencao_ok, 'ficha_ok': intencao_ok and not divergencias,
            'intencao_obtida': saida['intencao'], 'divergencias': divergencias}


def rodar(nos, rodadas: int) -> list[list[dict]]:
    return [[avaliar_caso(nos, c) for c in CASOS] for _ in range(rodadas)]


def resumir(resultados: list[list[dict]]) -> dict:
    por_rodada = [{'intencao': sum(r['intencao_ok'] for r in rodada), 'ficha': sum(r['ficha_ok'] for r in rodada)} for rodada in resultados]
    n = len(CASOS)
    por_caso = {}
    for rodada in resultados:
        for r in rodada:
            por_caso.setdefault(r['id'], []).append(r)
    instaveis = [i for i, rs in por_caso.items() if len({x['ficha_ok'] for x in rs}) > 1]
    sempre_erra = [i for i, rs in por_caso.items() if not any(x['ficha_ok'] for x in rs)]
    grupos = {}
    for rodada in resultados:
        for r in rodada:
            g = grupos.setdefault(r['grupo'], [0, 0])
            g[0] += r['ficha_ok']
            g[1] += 1
    ho = [{'intencao': sum(r['intencao_ok'] for r in rodada if r['id'] not in VAZADOS),
           'ficha': sum(r['ficha_ok'] for r in rodada if r['id'] not in VAZADOS)} for rodada in resultados]
    n_ho = n - len(VAZADOS)
    return {'casos': n, 'vazados': VAZADOS, 'casos_heldout': n_ho, 'heldout_por_rodada': ho,
            'heldout_media_ficha': round(sum(x['ficha'] for x in ho) / len(ho), 2),
            'heldout_media_intencao': round(sum(x['intencao'] for x in ho) / len(ho), 2),
            'heldout_min_ficha': min(x['ficha'] for x in ho), 'heldout_max_ficha': max(x['ficha'] for x in ho),
            'por_rodada': por_rodada,
            'media_intencao': round(sum(x['intencao'] for x in por_rodada) / len(por_rodada), 2),
            'media_ficha': round(sum(x['ficha'] for x in por_rodada) / len(por_rodada), 2),
            'min_ficha': min(x['ficha'] for x in por_rodada), 'max_ficha': max(x['ficha'] for x in por_rodada),
            'casos_instaveis': instaveis, 'casos_que_sempre_erram': sempre_erra,
            'ficha_por_grupo': {g: f'{a}/{b}' for g, (a, b) in grupos.items()}}


def main(rodadas: int) -> int:
    from src.trajetoria import estado_do_codigo
    from src.util import modelo_em_uso
    nos = preparar_nos()
    inicio = time.time()
    resultados = rodar(nos, rodadas)
    resumo = resumir(resultados)
    print(f"{len(CASOS)} casos x {rodadas} rodadas ({time.time() - inicio:.0f} s) | modelo {modelo_em_uso()}")
    for i, r in enumerate(resumo['por_rodada'], 1):
        print(f"  rodada {i}: intenção {r['intencao']}/{len(CASOS)} | ficha completa {r['ficha']}/{len(CASOS)}")
    print(f"  média (todos): intenção {resumo['media_intencao']}/{len(CASOS)} | ficha {resumo['media_ficha']}/{len(CASOS)} (faixa {resumo['min_ficha']} a {resumo['max_ficha']})")
    print(f"  casos que o prompt já mostra: {resumo['vazados']}")
    print(f"  MEDIDA QUE VALE (fora do prompt, {resumo['casos_heldout']} casos): intenção {resumo['heldout_media_intencao']}/{resumo['casos_heldout']} | "
          f"ficha {resumo['heldout_media_ficha']}/{resumo['casos_heldout']} (faixa {resumo['heldout_min_ficha']} a {resumo['heldout_max_ficha']})")
    print('  ficha por grupo (soma das rodadas):', resumo['ficha_por_grupo'])
    print('  casos que mudam de resultado entre rodadas:', resumo['casos_instaveis'], '| que sempre erram:', resumo['casos_que_sempre_erram'])
    for rodada in resultados[-1:]:
        for r in rodada:
            if not r['ficha_ok']:
                print(f"    #{r['id']} ({r['grupo']}) intenção {r.get('intencao_obtida')} {json.dumps(r['divergencias'], ensure_ascii=False)}{' ' + r['erro'] if 'erro' in r else ''}")
    destino = RAIZ / 'logs' / 'avaliacao-extracao'
    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'resultado.json').write_text(json.dumps(
        {**estado_do_codigo(), 'data': time.strftime('%Y-%m-%d'), 'modelo': modelo_em_uso(), 'resumo': resumo, 'rodadas': resultados},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Resultado em {destino / "resultado.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3))
