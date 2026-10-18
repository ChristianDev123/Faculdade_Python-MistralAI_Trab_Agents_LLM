"""Remoção feita por quem administra o sistema (a pessoa usuária faz o mesmo pelo chat, pedindo para apagar os dados).

Uso:
  python src/esquecer.py <user_id>               apaga tudo do titular, inclusive todas as conversas salvas
  python src/esquecer.py --episodio <id_da_linha> apaga um episódio (a linha e o vetor): recuperação de incidente

Depois de apagar, confira com:  python verificar_remocao.py <user_id>
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.nos import servicos


def main(argv: list[str]) -> int:
    memoria = servicos().memoria
    if len(argv) == 3 and argv[1] == '--episodio':
        print('Episódio removido:', memoria.esquecer_episodio(int(argv[2])))
        return 0
    if len(argv) == 2 and not argv[1].startswith('--'):
        print('Removido:', memoria.esquecer_usuario(argv[1]))
        if memoria.procedural_cita(argv[1]):
            print('ATENÇÃO: src/prompts/procedural.md cita este identificador; edite o arquivo à mão.')
            return 1
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
