"""Varre TODAS as estruturas procurando um identificador, de forma independente do código que apaga.

Uso:  python verificar_remocao.py <user_id> [--ignorar <arquivo>]...
  --ignorar  arquivo que guarda o identificador DE PROPÓSITO (ex.: o resultado.json da demonstração, que é
             documentação com a transcrição de um usuário de teste). Aparece na saída, para ninguém esquecer.
Sai com código 0 se não achou nada e 1 se achou. Use um identificador que não seja uma palavra comum.

O que varre: todas as colunas de todas as tabelas de todos os SQLite em databases/ (inclusive o checkpoint e o
banco interno do Chroma), os bytes brutos de todos os arquivos de databases/ (pega o que um DELETE deixou em
páginas livres), os arquivos e nomes em logs/ e os prompts em src/prompts/. O registro de remoções (logs/_remocoes.jsonl) guarda só o hash, por isso não conta.
"""
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def varrer_sqlite(arquivo: Path, alvo: bytes) -> list[str]:
    achados = []
    conn = sqlite3.connect(f'file:{arquivo}?mode=ro', uri=True)
    try:
        tabelas = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for tabela in tabelas:
            for coluna in [c[1] for c in conn.execute(f'PRAGMA table_info("{tabela}")')]:
                n = conn.execute(
                    f'SELECT count(*) FROM "{tabela}" WHERE instr(CAST("{coluna}" AS BLOB), CAST(? AS BLOB)) > 0', (alvo,)
                ).fetchone()[0]
                if n:
                    achados.append(f'{arquivo.relative_to(RAIZ)} :: {tabela}.{coluna}: {n} ocorrência(s)')
    finally:
        conn.close()
    return achados


def varrer_arquivos(pasta: Path, alvo: bytes, ignorar: tuple[str, ...] = (), caminhos_ignorados: frozenset = frozenset()) -> list[str]:
    achados = []
    if not pasta.exists():
        return achados
    for caminho in pasta.rglob('*'):
        if caminho.name in ignorar or '__pycache__' in caminho.parts or caminho.resolve() in caminhos_ignorados:
            continue
        if alvo.decode() in str(caminho.relative_to(pasta)):
            achados.append(f'{caminho.relative_to(RAIZ)} (no nome do caminho)')
        if caminho.is_file() and alvo in caminho.read_bytes():
            achados.append(f'{caminho.relative_to(RAIZ)} (no conteúdo)')
    return achados


def varrer_bytes_brutos(pasta: Path, alvo: bytes) -> list[str]:
    """Procura o identificador nos bytes do arquivo inteiro: pega o que um DELETE deixou em páginas livres."""
    achados = []
    for caminho in pasta.rglob('*'):
        if caminho.is_file() and 'manuais' not in caminho.parts and alvo in caminho.read_bytes():
            achados.append(f'{caminho.relative_to(RAIZ)} (bytes brutos: pode ser página livre ou log interno)')
    return achados


def main(user_id: str, ignorados: list[str] | None = None) -> int:
    alvo = user_id.encode('utf-8')
    caminhos_ignorados = frozenset((RAIZ / p).resolve() for p in (ignorados or []))
    achados: list[str] = []
    for banco in sorted((RAIZ / 'databases').rglob('*.sqlite*')) + sorted((RAIZ / 'databases').rglob('*.db')):
        if banco.is_file() and banco.suffix not in ('.sqlite-wal', '.sqlite-shm'):
            achados += varrer_sqlite(banco, alvo)
    achados += varrer_bytes_brutos(RAIZ / 'databases', alvo)
    achados += varrer_arquivos(RAIZ / 'logs', alvo, ignorar=('_remocoes.jsonl',), caminhos_ignorados=caminhos_ignorados)
    achados += varrer_arquivos(RAIZ / 'src' / 'prompts', alvo)

    print(f'Varredura por "{user_id}": {len(achados)} ocorrência(s).')
    for p in ignorados or []:
        print(f'  (ignorado de propósito: {p})')
    for a in achados:
        print('  -', a)
    return 1 if achados else 0


if __name__ == '__main__':
    args = sys.argv[1:]
    ignorados = [args[i + 1] for i, a in enumerate(args) if a == '--ignorar' and i + 1 < len(args)]
    posicionais = [a for i, a in enumerate(args) if a != '--ignorar' and not (i and args[i - 1] == '--ignorar')]
    if len(posicionais) != 1:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(posicionais[0], ignorados))
