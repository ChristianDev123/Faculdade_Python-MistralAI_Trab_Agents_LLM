from pathlib import Path

from src.config import MODEL

PROMPTS_PATH = Path(__file__).resolve().parent / 'prompts'
MODELO_PADRAO = 'openai/gpt-oss-120b'


def ler_prompt(nome: str) -> str:
    """Lê um prompt de src/prompts/ em tempo de execução (o carimbo de versão está em trajetoria.carimbo_prompts)."""
    return (PROMPTS_PATH / nome).read_text(encoding='utf-8')


def modelo_em_uso() -> str:
    return MODEL or MODELO_PADRAO
