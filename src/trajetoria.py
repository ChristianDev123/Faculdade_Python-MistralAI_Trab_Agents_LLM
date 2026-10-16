import hashlib
import json
import subprocess
import time
from pathlib import Path

PROJECT_PATH = Path(__file__).resolve().parent.parent
PROMPTS_PATH = PROJECT_PATH / 'src' / 'prompts'


def commit_atual() -> str:
    try:
        saida = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=PROJECT_PATH, capture_output=True, text=True, timeout=5
        )
        return saida.stdout.strip() or 'desconhecido'
    except Exception:
        return 'desconhecido'


def carimbo_prompts() -> dict:
    """Hash de cada arquivo em src/prompts/: identifica a versão exata em uso na execução."""
    carimbo = {}
    for arquivo in sorted(PROMPTS_PATH.rglob('*.md')):
        conteudo = arquivo.read_bytes()
        carimbo[arquivo.relative_to(PROMPTS_PATH).as_posix()] = hashlib.sha256(conteudo).hexdigest()[:12]
    return carimbo


class Trajetoria:
    """Log da trajetória: uma linha JSON por evento (início, entrada, ferramenta, resposta, término)."""

    def __init__(self, user_id: str, session_id: str):
        self.path = PROJECT_PATH / 'logs' / str(user_id) / str(session_id) / 'trajetoria.jsonl'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.passo = 0

    def registrar(self, evento: str, **dados) -> None:
        self.passo += 1
        linha = {
            'passo': self.passo,
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'evento': evento,
            **dados,
        }
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(linha, ensure_ascii=False, default=str) + '\n')
