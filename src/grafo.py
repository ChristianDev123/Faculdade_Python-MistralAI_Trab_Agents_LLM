"""O grafo do sistema, compilado uma vez. `conferir_grafo.py` importa este mesmo objeto.

Desenho e justificativa em docs/grafo.md. Resumo: o modelo decide só a intenção e os dados (nó `extrair`);
toda aresta condicional é decidida por regra em código; as paradas humanas são `aprovar_gravacao` e `confirmar_esquecimento`.
"""
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src import nos
from src.estado import Estado
from src.memoria import CHECKPOINT_PATH

# Parâmetro que o framework tem com valor padrão (25) e que aqui é declarado: o grafo não tem ciclos, então
# uma execução usa no máximo 7 super-passos (entrada, extrair, consultar_base, raspar, aprovar_gravacao, gravar, emitir). Se um dia o padrão da biblioteca mudar, este valor continua valendo.
RECURSION_LIMIT = 25


def montar_grafo(checkpointer=None):
    g = StateGraph(Estado)
    for nome in ('entrada', 'extrair', 'recusar', 'perguntar', 'consultar_base', 'raspar',
                 'aprovar_gravacao', 'gravar', 'ler_manual', 'registrar_duvida', 'lembrar', 'memorizar',
                 'confirmar_esquecimento', 'esquecer', 'emitir'):
        g.add_node(nome, getattr(nos, nome))

    g.add_edge(START, 'entrada')
    g.add_conditional_edges('entrada', nos.rota_pos_entrada, {'lembrar': 'lembrar', 'extrair': 'extrair', 'emitir': 'emitir'})
    g.add_edge('lembrar', 'extrair')
    g.add_conditional_edges('extrair', nos.rota_pos_extracao, {
        'recusar': 'recusar', 'perguntar': 'perguntar', 'consultar_base': 'consultar_base',
        'confirmar_esquecimento': 'confirmar_esquecimento', 'emitir': 'emitir'})
    g.add_conditional_edges('confirmar_esquecimento', nos.rota_pos_confirmacao, {'esquecer': 'esquecer', 'emitir': 'emitir'})
    g.add_edge('esquecer', 'emitir')
    g.add_edge('recusar', 'emitir')
    g.add_edge('perguntar', 'emitir')
    g.add_conditional_edges('consultar_base', nos.rota_pos_base, {
        'emitir': 'emitir', 'raspar': 'raspar', 'ler_manual': 'ler_manual'})
    g.add_conditional_edges('raspar', nos.rota_pos_raspagem, {'aprovar_gravacao': 'aprovar_gravacao', 'emitir': 'emitir'})
    g.add_conditional_edges('aprovar_gravacao', nos.rota_pos_aprovacao, {'gravar': 'gravar', 'emitir': 'emitir'})
    g.add_edge('gravar', 'emitir')
    g.add_conditional_edges('ler_manual', nos.rota_pos_manual, {'registrar_duvida': 'registrar_duvida', 'emitir': 'emitir'})
    g.add_edge('registrar_duvida', 'emitir')
    g.add_conditional_edges('emitir', nos.rota_pos_emissao, {'memorizar': 'memorizar', '__end__': END})
    g.add_edge('memorizar', END)
    return g.compile(checkpointer=checkpointer)


def _criar_checkpointer() -> SqliteSaver:
    """Checkpoint em arquivo: a conversa e a aprovação pendente sobrevivem ao fim do processo."""
    conexao = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
    return SqliteSaver(conexao)


grafo = montar_grafo(_criar_checkpointer())
