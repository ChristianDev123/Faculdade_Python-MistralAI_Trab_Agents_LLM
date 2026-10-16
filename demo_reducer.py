"""Demonstra o que o reducer de um campo faz num grafo com dois nós paralelos (§7.2 do trabalho).

O grafo do sistema é sequencial, então a demonstração usa um grafo mínimo à parte: dois nós rodam no mesmo
passo e cada um escreve no campo `evidencias`. A saída muda conforme a regra de combinação do campo.

Uso:  python demo_reducer.py        (sem modelo, sem rede)
"""
import operator
import sys
from pathlib import Path
from typing import Annotated, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.graph import END, START, StateGraph

from src.estado import acumular


def noh(nome: str):
    return lambda state: {'evidencias': [f'{nome}: achou 1 fonte']}


def executar(titulo: str, estado_cls) -> None:
    g = StateGraph(estado_cls)
    g.add_node('base_local', noh('base_local'))
    g.add_node('manual', noh('manual'))
    g.add_edge(START, 'base_local')   # os dois saem do mesmo ponto: rodam no mesmo super-passo
    g.add_edge(START, 'manual')
    g.add_edge('base_local', END)
    g.add_edge('manual', END)
    print(f'--- {titulo}')
    try:
        print('   resultado:', g.compile().invoke({'evidencias': []})['evidencias'])
    except Exception as err:
        print(f'   {type(err).__name__}: {str(err).splitlines()[0]}')


class SemReducer(TypedDict):
    evidencias: list


class ComReducer(TypedDict):
    evidencias: Annotated[list, operator.add]


class UltimoVence(TypedDict):
    evidencias: Annotated[list, lambda atual, novo: novo]


class AcumulaEZera(TypedDict):
    evidencias: Annotated[list, acumular]


executar('1. campo SEM reducer (padrão do framework)', SemReducer)
executar('2. reducer "o último que terminou vence" (o que um campo sem regra faria se não houvesse erro)', UltimoVence)
executar('3. reducer operator.add (soma as listas)', ComReducer)
executar('4. reducer `acumular` do sistema (soma e aceita zerar a cada turno)', AcumulaEZera)
