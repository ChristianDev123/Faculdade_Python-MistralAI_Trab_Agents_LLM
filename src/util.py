import os
import re
import unicodedata
from pathlib import Path

from src.config import MODEL

PROMPTS_PATH = Path(__file__).resolve().parent / 'prompts'
MODELO_PADRAO = 'openai/gpt-oss-120b'


def ler_prompt(nome: str) -> str:
    """Lê um prompt de src/prompts/ em tempo de execução (o carimbo de versão está em trajetoria.carimbo_prompts)."""
    return (PROMPTS_PATH / nome).read_text(encoding='utf-8')


def dobrar(texto) -> str:
    """Minúsculas, sem acento e com espaços normalizados: para comparar textos."""
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', str(texto).lower()) if not unicodedata.combining(c)))


def modelo_em_uso() -> str:
    return MODEL or MODELO_PADRAO


# Orçamento de contexto por chamada ao modelo, em tokens estimados (caracteres / 3,5 para português).
JANELA_TOKENS = int(os.environ.get('JANELA_TOKENS') or 3000)
CARACTERES_POR_TOKEN = 3.5


def tokens_estimados(texto: str) -> int:
    return int(len(texto) / CARACTERES_POR_TOKEN) + 1
