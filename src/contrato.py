"""Contratos do sistema, validados em código com Pydantic.

Entrada do sistema: texto livre (mais thread_id e user_id, que não são digitados por ninguém).
Saída do sistema: `Saida`, com os três campos obrigatórios do contrato: resultado, fonte e suficiencia.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Intencao = Literal['PECA', 'MANUAL', 'FORA_DO_ESCOPO', 'INDEFINIDA']

# Por que a execução acabou. Quem define é código, nunca o modelo.
MotivoTermino = Literal[
    'respondido',
    'faltam_dados',
    'fora_do_escopo',
    'sem_base',
    'rejeitado_pelo_humano',
    'aprovacao_expirada',
    'desistiu_apos_3_perguntas',
    'erro_ferramenta',
    'erro_modelo',
    'limite_turnos',
]

Situacao = Literal['respondido', 'faltam_dados', 'fora_do_escopo', 'sem_base', 'rejeitado', 'expirado', 'erro']


class Extracao(BaseModel):
    """O que o modelo extrai do texto livre. null = o usuário não disse (nunca inventar)."""
    intencao: Intencao
    modelo: Optional[str]
    ano: Optional[int]
    motorizacao: Optional[str]
    fabricante: Optional[str]
    nome_peca: Optional[str]
    duvida: Optional[str]


class Peca(BaseModel):
    nome_peca: str
    codigo_peca: str
    carros_compativeis: list[str] = Field(default_factory=list)


class LeituraManual(BaseModel):
    """Resposta do modelo sobre os trechos recuperados do manual."""
    pensamento: str
    trecho_original: str
    resumo: str
    sanada: bool


class Fonte(BaseModel):
    """O que sustenta o resultado, conferível."""
    tipo: Literal['base_local', 'manual_pdf', 'catalogo_web', 'nenhuma']
    origem: str
    evidencia: str


class RespostaAprovacao(BaseModel):
    """O que a pessoa devolve na pausa. `candidatas` só vem quando ela editou a lista (aprovar editando)."""
    decisao: Literal['aprovar', 'rejeitar']
    candidatas: Optional[list[Peca]] = None


class Saida(BaseModel):
    resultado: str
    dados: Optional[list[Peca]] = None
    fonte: list[Fonte]
    suficiencia: bool
    situacao: Situacao
    pergunta_pendente: Optional[str] = None
