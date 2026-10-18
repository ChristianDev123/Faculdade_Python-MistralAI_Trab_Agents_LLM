"""Avalia o RAG do sistema com o conjunto de dados/perguntas_rag.json.

Uso:
  python avaliar_rag.py perguntas   as 10 perguntas oficiais, pelo grafo inteiro (uma conversa por pergunta, mesmo usuário)
  python avaliar_rag.py manual [n] [rotulo]   os 32 casos do leitor de manual (18 com resposta, 14 sem), 'n' vezes;
                                    grava logs/rag-avaliacao/manual-<rotulo>.json (rótulo padrão: atual)

O que mede (e o que não mede) está em docs/rag.md. O modelo local não é determinístico nem com temperature 0:
rode `manual` mais de uma vez e leia a faixa, não um número.
"""
import json
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

DADOS = json.loads((RAIZ / 'dados' / 'perguntas_rag.json').read_text(encoding='utf-8'))


def avaliar_perguntas(usuario: str = 'rag-avaliacao') -> int:
    from langchain_core.messages import HumanMessage
    from langgraph.types import Command

    from src.grafo import RECURSION_LIMIT, grafo
    from src.nos import _log, _traj
    from src.trajetoria import estado_do_codigo
    from src.util import modelo_em_uso

    saidas, acertos = [], 0
    for p in DADOS['perguntas']:
        cfg = {'configurable': {'thread_id': f"{usuario}:q{p['id']}"}, 'recursion_limit': RECURSION_LIMIT}
        inicio = time.time()
        resultado = grafo.invoke({'mensagens': [HumanMessage(p['pergunta'])]}, cfg)
        pausou = '__interrupt__' in resultado
        if pausou:  # a avaliação não grava no cache: rejeita a gravação pendente
            resultado = grafo.invoke(Command(resume={'decisao': 'rejeitar'}), cfg)
        saida = resultado['saida']
        esperado = p['esperado']
        ok = saida['situacao'] == esperado['situacao'] and esperado['contem'].lower() in saida['resultado'].lower()
        acertos += ok
        saidas.append({'id': p['id'], 'pergunta': p['pergunta'], 'forma': p['forma'], 'ok': ok, 'pausou_para_aprovacao': pausou,
                       'situacao': saida['situacao'], 'motivo': resultado['motivo_termino'], 'suficiencia': saida['suficiencia'],
                       'fonte': [f['tipo'] for f in saida['fonte']], 'chamadas_ao_modelo': len(resultado.get('passos') or []),
                       'segundos': round(time.time() - inicio, 1), 'resultado': saida['resultado'],
                       'coberta_pelo_grafo': p['coberta_pelo_grafo']})
        marca = 'OK  ' if ok else 'FALHA'
        print(f"{marca} #{p['id']:<2} [{saida['situacao']:<12}] {p['forma'][:38]:<38} {p['pergunta']}")
        print(f"        -> {saida['resultado'][:170].replace(chr(10), ' | ')}")
    print(f"\n{acertos}/{len(DADOS['perguntas'])} com a situação e o conteúdo esperados "
          f"({sum(1 for s in saidas if s['ok'] and s['coberta_pelo_grafo'])}/{sum(1 for s in saidas if s['coberta_pelo_grafo'])} entre as cobertas pelo grafo)")
    destino = RAIZ / 'logs' / usuario
    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'resultado.json').write_text(json.dumps(
        {**estado_do_codigo(), 'data': time.strftime('%Y-%m-%d'), 'modelo': modelo_em_uso(), 'resultados': saidas},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Resultado gravado em {destino / "resultado.json"}')
    return 0


def avaliar_manual(repeticoes: int = 1, rotulo: str = 'atual') -> int:
    import os
    from src.config import client
    from src.leitor_manual_pdf import LeitorManualPDF
    from src.trajetoria import carimbo_prompts, estado_do_codigo
    from src.util import modelo_em_uso

    d = DADOS['avaliacao_manual']
    leitor = LeitorManualPDF(client)
    rodadas = []
    for rodada in range(1, repeticoes + 1):
        sanadas = com_fato = falsas = recusas = erros = 0
        por_pergunta = {}
        total_sem = sum(len(g['perguntas']) for g in d['sem_resposta'])
        for caso in d['com_resposta']:
            for q in caso['perguntas']:
                r = leitor.ler(d['manual'], q.rstrip('?') + d['sufixo_da_pergunta'] + '?', d['veiculo'])
                if 'erro' in r:
                    erros += 1
                    continue
                x = r['leitura']
                sanadas += x.sanada
                acertou = bool(x.sanada and re.search(caso['fato'], (x.resumo + ' ' + x.trecho_original).lower()))
                com_fato += acertou
                por_pergunta[q] = acertou
        for grupo in d['sem_resposta']:
            for q in grupo['perguntas']:
                r = leitor.ler(d['manual'], q.rstrip('?') + d['sufixo_da_pergunta'] + '?', d['veiculo'])
                if 'erro' in r or not r['leitura'].sanada:
                    recusas += 1
                else:
                    falsas += 1
                    por_pergunta[q] = 'FALSA'
        n_com = sum(len(c['perguntas']) for c in d['com_resposta'])
        print(f"rodada {rodada}: respondeu {sanadas}/{n_com} | com o fato esperado {com_fato}/{n_com} | "
              f"recusou {recusas}/{total_sem} | FALSA RESPOSTA {falsas}/{total_sem} | erros {erros}", flush=True)
        rodadas.append({'respondeu': sanadas, 'com_fato': com_fato, 'recusou': recusas, 'falsas': falsas, 'erros': erros, 'por_pergunta': por_pergunta})
    destino = RAIZ / 'logs' / 'rag-avaliacao'
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f'manual-{rotulo}.json').write_text(json.dumps(
        {**estado_do_codigo(), 'data': time.strftime('%Y-%m-%d'), 'modelo': modelo_em_uso(), 'contexto_ollama': os.environ.get('CONTEXTO_OLLAMA', 'não informado'),
         'prompts': carimbo_prompts(), 'rotulo': rotulo, 'rodadas': rodadas}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Resultado gravado em {destino / ("manual-" + rotulo + ".json")}')
    return 0


if __name__ == '__main__':
    modo = sys.argv[1] if len(sys.argv) > 1 else ''
    if modo == 'perguntas':
        sys.exit(avaliar_perguntas())
    if modo == 'manual':
        sys.exit(avaliar_manual(int(sys.argv[2]) if len(sys.argv) > 2 else 1, sys.argv[3] if len(sys.argv) > 3 else 'atual'))
    print(__doc__)
    sys.exit(2)
