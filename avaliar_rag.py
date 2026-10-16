"""Avalia o RAG do sistema com o conjunto de dados/perguntas_rag.json.

Uso:
  python avaliar_rag.py perguntas   as 10 perguntas oficiais, pelo grafo inteiro (uma conversa por pergunta, mesmo usuário)
  python avaliar_rag.py manual      os 30 casos do leitor de manual (18 com resposta, 12 sem), 'n' vezes

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
    from src.trajetoria import commit_atual
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
        {'commit': commit_atual(), 'data': time.strftime('%Y-%m-%d'), 'modelo': modelo_em_uso(), 'resultados': saidas},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Resultado gravado em {destino / "resultado.json"}')
    return 0


def avaliar_manual(repeticoes: int = 1) -> int:
    from src.config import client
    from src.leitor_manual_pdf import LeitorManualPDF

    d = DADOS['avaliacao_manual']
    leitor = LeitorManualPDF(client)
    for rodada in range(1, repeticoes + 1):
        sanadas = com_fato = falsas = recusas = erros = 0
        total_sem = sum(len(g['perguntas']) for g in d['sem_resposta'])
        for caso in d['com_resposta']:
            for q in caso['perguntas']:
                r = leitor.ler(d['manual'], q.rstrip('?') + d['sufixo_da_pergunta'] + '?', d['veiculo'])
                if 'erro' in r:
                    erros += 1
                    continue
                x = r['leitura']
                sanadas += x.sanada
                com_fato += bool(x.sanada and re.search(caso['fato'], (x.resumo + ' ' + x.trecho_original).lower()))
        for grupo in d['sem_resposta']:
            for q in grupo['perguntas']:
                r = leitor.ler(d['manual'], q.rstrip('?') + d['sufixo_da_pergunta'] + '?', d['veiculo'])
                if 'erro' in r or not r['leitura'].sanada:
                    recusas += 1
                else:
                    falsas += 1
        n_com = sum(len(c['perguntas']) for c in d['com_resposta'])
        print(f"rodada {rodada}: respondeu {sanadas}/{n_com} | com o fato esperado {com_fato}/{n_com} | "
              f"recusou {recusas}/{total_sem} | FALSA RESPOSTA {falsas}/{total_sem} | erros {erros}")
    return 0


if __name__ == '__main__':
    modo = sys.argv[1] if len(sys.argv) > 1 else ''
    if modo == 'perguntas':
        sys.exit(avaliar_perguntas())
    if modo == 'manual':
        sys.exit(avaliar_manual(int(sys.argv[2]) if len(sys.argv) > 2 else 1))
    print(__doc__)
    sys.exit(2)
