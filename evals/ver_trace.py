"""Mostra um arquivo de trace como árvore, execução por execução.

Uso:
  python -m evals.ver_trace logs/<usuario>/<sessao>/trace.jsonl
  python -m evals.ver_trace evals/resultados/v3.0.0/traces.jsonl [trecho do id da conversa]
"""
import json
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    spans = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    if len(sys.argv) > 2:
        spans = [s for s in spans if sys.argv[2] in s['attributes'].get('gen_ai.conversation.id', '')]
    execucoes = {}
    for s in spans:
        execucoes.setdefault(s['context']['trace_id'], []).append(s)
    print(f'{len(spans)} spans em {len(execucoes)} execuções')
    for trace_id, lista in execucoes.items():
        raiz = next((s for s in lista if not s.get('parent_id')), None)
        if raiz is None:
            continue
        a = raiz['attributes']
        print(f"\n{raiz['name']}  trace {trace_id}")
        print(f"  conversa {a.get('gen_ai.conversation.id')} | versão {a.get('agente.versao')} | commit {a.get('agente.commit')} | modelo {a.get('gen_ai.request.model')}")
        print(f"  entrada: {a.get('agente.entrada')}")
        print(f"  término: {a.get('agente.termino')}")
        for e in raiz.get('events', []):
            if e['name'] != 'no':
                print(f"  evento {e['name']}: {e['attributes']}")
        print('  nós:', ' > '.join(e['attributes']['no'] for e in raiz.get('events', []) if e['name'] == 'no'))
        for s in sorted((s for s in lista if s is not raiz), key=lambda s: s['start_time']):
            b = s['attributes']
            if b.get('gen_ai.operation.name') == 'chat':
                print(f"  ├── {s['name']}  tokens {b.get('gen_ai.usage.input_tokens')}/{b.get('gen_ai.usage.output_tokens')}")
                for e in s.get('events', []):
                    print(f"  │     resposta: {e['attributes'].get('conteudo', '')[:300]}")
            else:
                print(f"  ├── {s['name']}  [{s['status']['status_code']}]")
                print(f"  │     argumentos: {str(b.get('agente.tool.argumentos'))[:200]}")
                print(f"  │     resultado: {str(b.get('agente.tool.resultado'))[:200]}")
        if a.get('agente.saida'):
            print(f"  saída: {json.loads(a['agente.saida'])['resultado'][:300]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
