"""Compara duas rodadas da suíte.

Uso:
  python -m evals.comparar evals/resultados/<rodada-A> evals/resultados/<rodada-B>
"""
import json
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def carregar(pasta: str) -> dict:
    return json.loads((Path(pasta) / 'resultado.json').read_text(encoding='utf-8'))


def por_classe(rodada: dict) -> dict:
    classes = {}
    for caso in rodada['casos'].values():
        classes.setdefault(caso['classe'], []).append(caso['ok'])
    return {c: 100 * sum(v) / len(v) for c, v in classes.items()}


def linha_do_juiz() -> str:
    arquivo = RAIZ / 'juiz' / 'validacao.json'
    if not arquivo.exists():
        return 'JUIZ não validado'
    v = json.loads(arquivo.read_text(encoding='utf-8'))
    return f"JUIZ rubrica v{v['rubrica']}   concordância {v['concordancia']:.0f}%   limiar {v['limiar']:.0f}%"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a, b = carregar(sys.argv[1]), carregar(sys.argv[2])
    origens = Counter(c['origem'] for c in b['casos'].values())
    print(f"DATASET v{b['dataset']}   {len(b['casos'])} casos   (producao {origens['producao']} · desenvolvimento {origens['desenvolvimento']} · sintetico {origens['sintetico']})")
    print(linha_do_juiz())
    print(f"\n{'classe':<16}{'v' + a['versao']:>10}{'v' + b['versao']:>10}{'delta':>8}")
    ca, cb = por_classe(a), por_classe(b)
    for classe in sorted(set(ca) | set(cb)):
        va, vb = ca.get(classe, 0), cb.get(classe, 0)
        print(f"{classe:<16}{va:>9.0f}%{vb:>9.0f}%{vb - va:>+8.0f}")
    ma, mb = sum(ca.values()) / len(ca), sum(cb.values()) / len(cb)
    print(f"{'MÉDIA':<16}{ma:>9.0f}%{mb:>9.0f}%{mb - ma:>+8.0f}")
    comuns = set(a['casos']) & set(b['casos'])
    saiu = sorted(i for i in comuns if a['casos'][i]['ok'] and not b['casos'][i]['ok'])
    entrou = sorted(i for i in comuns if b['casos'][i]['ok'] and not a['casos'][i]['ok'])
    print(f"\nPassaram a falhar: {saiu or 'nenhum'}\nPassaram a acertar: {entrou or 'nenhum'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
