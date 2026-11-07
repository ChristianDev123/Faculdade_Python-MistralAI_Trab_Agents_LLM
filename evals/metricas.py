"""As métricas de docs/observabilidade.md, lidas dos traces de cada rodada.

Uso:
  python -m evals.metricas evals/resultados/<rodada> [evals/resultados/<rodada> ...]

Uma execução é um trace: a raiz `invoke_agent`, com os spans `chat` e `execute_tool` abaixo dela.
"""
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Preço de referência do modelo remoto (docs/modelos.md), em dólares por milhão de tokens. O modelo local custa zero por token.
PRECO_ENTRADA, PRECO_SAIDA = 0.15, 0.60

# SLO de qualidade. Boa é a execução que entregou um desfecho do contrato: resposta, recusa, pergunta de volta ou decisão humana cumprida.
# Ruim é a que parou no meio, por limite ou erro. Pausa não conta como válida: a execução seguinte da conversa é que termina.
OBJETIVO = 95.0
RUINS = {'desistiu_apos_3_perguntas', 'limite_turnos', 'erro_modelo', 'erro_ferramenta', 'erro_nao_tratado'}
FORA_DO_SLI = {'aguardando_humano'}


def percentil(valores: list[float], p: float) -> float:
    return statistics.quantiles(valores, n=100, method='inclusive')[int(p) - 1]


def duracao(span: dict) -> float:
    return (datetime.fromisoformat(span['end_time'].replace('Z', '+00:00')) - datetime.fromisoformat(span['start_time'].replace('Z', '+00:00'))).total_seconds()


def medir(pasta: str) -> dict:
    spans = [json.loads(l) for l in (Path(pasta) / 'traces.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    raizes = [s for s in spans if not s.get('parent_id')]
    chats = [s for s in spans if s['attributes'].get('gen_ai.operation.name') == 'chat']
    ferramentas = [s for s in spans if s['attributes'].get('gen_ai.operation.name') == 'execute_tool']
    latencias = [duracao(s) for s in raizes]
    entrada = sum(s['attributes'].get('gen_ai.usage.input_tokens', 0) for s in chats)
    saida = sum(s['attributes'].get('gen_ai.usage.output_tokens', 0) for s in chats)
    motivos = Counter(s['attributes'].get('agente.termino', 'sem_termino') for s in raizes)
    por_ferramenta = {}
    for s in ferramentas:
        total, erros = por_ferramenta.get(s['attributes']['gen_ai.tool.name'], (0, 0))
        por_ferramenta[s['attributes']['gen_ai.tool.name']] = (total + 1, erros + (s['status']['status_code'] == 'ERROR'))
    validas = sum(n for m, n in motivos.items() if m not in FORA_DO_SLI)
    ruins = sum(n for m, n in motivos.items() if m in RUINS)
    sli = 100 * (validas - ruins) / validas
    return {'execucoes': len(raizes), 'versoes': sorted({s['attributes'].get('agente.versao') for s in raizes}), 'chamadas_ao_modelo': len(chats),
            'latencia_p50_s': percentil(latencias, 50), 'latencia_p95_s': percentil(latencias, 95),
            'tokens_entrada_por_execucao': entrada / len(raizes), 'tokens_saida_por_execucao': saida / len(raizes),
            'custo_por_execucao_usd': (entrada * PRECO_ENTRADA + saida * PRECO_SAIDA) / 1e6 / len(raizes),
            'motivos': dict(motivos.most_common()), 'ferramentas': {k: {'chamadas': t, 'erros': e} for k, (t, e) in sorted(por_ferramenta.items())},
            'sli_pct': sli, 'objetivo_pct': OBJETIVO, 'validas': validas, 'ruins': ruins,
            'orcamento_de_erro_consumido_pct': 100 * (ruins / validas) / ((100 - OBJETIVO) / 100)}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for pasta in sys.argv[1:]:
        m = medir(pasta)
        print(f"\n=== {Path(pasta).name}: versão {m['versoes']}, {m['execucoes']} execuções, {m['chamadas_ao_modelo']} chamadas ao modelo")
        print(f"latência p50 {m['latencia_p50_s']:.1f} s | p95 {m['latencia_p95_s']:.1f} s")
        print(f"tokens por execução: {m['tokens_entrada_por_execucao']:.0f} de entrada, {m['tokens_saida_por_execucao']:.0f} de saída | custo de referência US$ {m['custo_por_execucao_usd']:.6f}")
        print('motivos de término:', m['motivos'])
        print('ferramentas (chamadas, erros):', {k: (v['chamadas'], v['erros']) for k, v in m['ferramentas'].items()})
        print(f"SLO: {m['sli_pct']:.1f}% boas de {m['validas']} válidas (objetivo {m['objetivo_pct']:.0f}%) | {m['ruins']} ruim(ns) | orçamento de erro consumido {m['orcamento_de_erro_consumido_pct']:.0f}%")
    return 0


if __name__ == '__main__':
    sys.exit(main())
