import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

PROJECT_PATH = Path(__file__).resolve().parent.parent
PROMPTS_PATH = PROJECT_PATH / 'src' / 'prompts'


def commit_atual() -> str:
    if os.environ.get('CODE_COMMIT'):  # imagem Docker: não há .git lá dentro, o commit entra no build (--build-arg CODE_COMMIT=...)
        return os.environ['CODE_COMMIT']
    try:
        saida = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=PROJECT_PATH, capture_output=True, text=True, timeout=5
        )
        return saida.stdout.strip() or 'desconhecido'
    except Exception:
        return 'desconhecido'


# O que NÃO é código: documentação, logs e bancos mudam a cada execução e não alteram o comportamento do sistema.
FORA_DO_CODIGO = ('docs', 'logs', 'databases', 'venv', 'README.md', '01-primeira-entrega.md', '02-segunda-entrega.md')


def estado_do_codigo() -> dict:
    """Commit atual e se o código (src/, scripts, dados de cenário, requirements) tem alteração por commitar.
    Sem isto o commit do carimbo mente: um log com o commit X pode ter rodado com código que não está em X."""
    try:
        saida = subprocess.run(
            # autocrlf: o repositório é editado no Windows (CRLF) e rodado no WSL; sem normalizar, todo arquivo parece alterado.
            # --no-optional-locks: consultar o estado não pode reescrever o índice.
            ['git', '--no-optional-locks', '-c', 'core.autocrlf=true', 'status', '--porcelain', '--untracked-files=all', '--', '.',
             *[f':(exclude){c}' for c in FORA_DO_CODIGO]],
            cwd=PROJECT_PATH, capture_output=True, text=True, timeout=10
        )
        alterados = [linha[3:].strip() for linha in saida.stdout.splitlines() if linha.strip()]
        return {'commit': commit_atual(), 'codigo_limpo': not alterados, 'arquivos_alterados': alterados[:20]}
    except Exception:
        return {'commit': commit_atual(), 'codigo_limpo': None, 'arquivos_alterados': []}


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
