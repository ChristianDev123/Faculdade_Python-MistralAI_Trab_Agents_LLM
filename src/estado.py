"""Estado que atravessa o grafo: um campo por informação, cada um com um reducer que diz o que acontece
quando um nó escreve nele. A lista de mensagens guarda só o texto da conversa; decisão, contador e
identificador são campos próprios.

Campo sem reducer é sobrescrito pelo último nó que escreve. Por isso todo campo escrito por mais de um
nó tem reducer, e os demais têm um único escritor (ver docs/grafo.md e demo_reducer.py).
"""
import operator
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

# Marcador que zera uma lista acumulada. O nó `entrada` o escreve no começo de cada turno.
ZERAR = {'__zerar__': True}
# Valor que apaga a chave num dict mesclado (ex.: ao trocar de veículo, o ano do anterior não vale mais).
LIMPAR = '__limpar__'


def acumular(atual: list | None, novo: list | None) -> list:
    """Acumula; se o novo trecho contém ZERAR, descarta tudo o que veio antes dele."""
    atual, novo = list(atual or []), list(novo or [])
    if ZERAR in novo:
        novo = novo[novo.index(ZERAR) + 1:]
        atual = []
    return atual + novo


def manter_se_definida(atual: Optional[str], novo: Optional[str]) -> Optional[str]:
    """INDEFINIDA e vazio nunca apagam uma intenção já conhecida."""
    return novo if novo not in (None, 'INDEFINIDA') else atual


def mesclar(atual: dict | None, novo: dict | None) -> dict:
    """Valor novo não nulo vence; nulo nunca apaga o que já se sabe; LIMPAR apaga de propósito."""
    resultado = dict(atual or {})
    for chave, valor in (novo or {}).items():
        if valor == LIMPAR:
            resultado.pop(chave, None)
        elif valor not in (None, ''):
            resultado[chave] = valor
    return resultado


def uniao(atual: list | None, novo: list | None) -> list:
    """Lista sem repetição que só cresce."""
    return list(dict.fromkeys([*(atual or []), *(novo or [])]))


def ultimo_nao_nulo(atual, novo):
    return novo if novo not in (None, '') else atual


def somar_por_chave(atual: dict | None, novo: dict | None) -> dict:
    resultado = dict(atual or {})
    for chave, valor in (novo or {}).items():
        resultado[chave] = resultado.get(chave, 0) + valor
    return resultado


class Estado(TypedDict, total=False):
    # --- conversa e orçamento ---
    mensagens: Annotated[list[AnyMessage], add_messages]   # só texto; add_messages acumula o histórico
    turno: int                                             # mensagens do usuário nesta conversa (escreve: entrada)
    passos: Annotated[list[str], acumular]                 # nós com chamada ao modelo no turno; entrada zera

    # --- o que o usuário já disse ---
    intencao: Annotated[Optional[str], manter_se_definida]
    veiculo: Annotated[dict, mesclar]                      # modelo, ano, motorizacao, fabricante
    nome_peca: Annotated[Optional[str], ultimo_nao_nulo]
    duvida: Annotated[Optional[str], ultimo_nao_nulo]
    avisos: Annotated[list[str], acumular]                 # escolhas declaradas (ex.: dado corrigido pelo usuário)
    tentativas_pergunta: Annotated[dict, somar_por_chave]  # quantas vezes cada campo foi perguntado
    perfil_lembrado: Optional[dict]                        # veículo que a memória semântica devolveu no turno 1
    campos_ditos: Annotated[list[str], uniao]              # campos do veículo que o próprio usuário disse nesta conversa

    # --- resultados por turno: um único escritor cada, entrada zera ---
    consulta: Optional[list]                               # linhas da base local
    candidatas: Optional[list]                             # peças raspadas; o humano pode editar
    aprovacao: Optional[dict]                              # decisão e carimbo de tempo da pausa
    gravadas: Optional[dict]                               # novas / ja_existiam / erros
    leitura: Optional[dict]                                # resposta do manual
    registro: Optional[dict]                               # registro da dúvida (ja_existia)
    memorizado: Optional[dict]                             # o que a memória semântica gravou no fim do turno
    esquecimento: Optional[dict]                           # decisão e contagens do pedido de apagar os dados
    evidencias: Annotated[list[dict], acumular]            # fontes consultadas no turno
    erro: Optional[dict]                                   # {'origem', 'mensagem'}
    pergunta: Optional[str]
    desvio: Optional[str]                                  # por que o fluxo foi direto à saída (entrada, recusar, perguntar: ramos exclusivos)

    # --- saída ---
    saida: Optional[dict]                                  # Saida validada
    motivo_termino: Optional[str]
