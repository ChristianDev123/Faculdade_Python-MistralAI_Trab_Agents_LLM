"""Imprime os nós e as arestas do grafo que o sistema executa (o mesmo objeto de src/grafo.py).

Uso:  python conferir_grafo.py
A saída vai colada em docs/grafo.md, ao lado do desenho. Se divergirem, vale o código.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.grafo import grafo

g = grafo.get_graph()

print('NÓS')
for nome in g.nodes:
    print(f'  {nome}')

print('\nARESTAS  (origem -> destino; [condicional] = o destino depende de uma regra)')
for aresta in g.edges:
    print(f"  {aresta.source} -> {aresta.target}" + ('  [condicional]' if aresta.conditional else ''))
