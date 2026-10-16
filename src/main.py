"""Linha de comando do assistente.

Uso:  python src/main.py [sessao]

O `thread_id` da conversa é "<usuario>:<sessao>" (usuário em USER_ID, padrão "local"). Passar a mesma sessão
retoma a conversa de onde ela parou, inclusive uma aprovação pendente, porque o estado está no checkpoint.
"""
import copy
import os
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.grafo import RECURSION_LIMIT, grafo
from src.nos import _traj, servicos

AJUDA_APROVACAO = 'Não entendi. Use: aprovar | rejeitar | editar remover 3,5 | editar codigo 2 ABC123'


def ler(prompt: str) -> str | None:
    try:
        texto = input(prompt).strip()
    except EOFError:
        return None
    return texto or None


def interpretar_aprovacao(linha: str, candidatas: list[dict]) -> dict | None:
    """Traduz o que a pessoa digitou na resposta que o grafo espera (RespostaAprovacao)."""
    partes = linha.split()
    comando = partes[0].lower() if partes else ''
    try:
        if comando in ('aprovar', 'rejeitar') and len(partes) == 1:
            return {'decisao': comando}
        if comando == 'editar' and len(partes) >= 3:
            editadas = copy.deepcopy(candidatas)
            if partes[1] == 'remover':
                fora = {int(i) for i in partes[2].split(',')}
                editadas = [c for pos, c in enumerate(editadas, 1) if pos not in fora]
            elif partes[1] == 'codigo' and len(partes) == 4:
                editadas[int(partes[2]) - 1]['codigo_peca'] = partes[3]
            else:
                return None
            return {'decisao': 'aprovar', 'candidatas': editadas}
    except (ValueError, IndexError):
        return None
    return None


def decidir(payload: dict) -> dict | None:
    print(payload['texto'])
    esquecer = payload['acao'] == 'esquecer_dados'
    while True:
        linha = ler('confirmação: ' if esquecer else 'aprovação: ')
        if linha is None:
            return None
        if esquecer:
            if linha.lower() in ('confirmar', 'cancelar'):
                return {'decisao': linha.lower()}
            print('Não entendi. Use: confirmar | cancelar')
            continue
        resposta = interpretar_aprovacao(linha, payload['candidatas'])
        if resposta is not None:
            return resposta
        print(AJUDA_APROVACAO)


def processar(entrada, cfg) -> dict | None:
    """Roda o grafo até ele terminar o turno. Se parar numa aprovação, pergunta e retoma; sem resposta, a pausa fica salva."""
    traj = _traj(cfg)
    resultado = grafo.invoke(entrada, cfg)
    while '__interrupt__' in resultado:
        payload = resultado['__interrupt__'][0].value
        traj.registrar('pausa', acao=payload['acao'], pausado_em=payload.get('pausado_em'), candidatas=len(payload.get('candidatas', [])))
        resposta = decidir(payload)
        if resposta is None:
            print('Pedido pendente: ele continua salvo nesta conversa. Rode de novo com a mesma sessão para responder.')
            return None
        traj.registrar('resposta_humana', resposta=resposta)
        resultado = grafo.invoke(Command(resume=resposta), cfg)
    return resultado


def mostrar(resultado: dict | None) -> None:
    if resultado is None:
        return
    print(f"Bot: {resultado['saida']['resultado']}")
    saida = resultado['saida']
    print(f"[{resultado['motivo_termino']} | suficiencia={saida['suficiencia']} | fonte: {', '.join(f['tipo'] for f in saida['fonte'])}]")


def encerrar_se_esquecido(resultado: dict | None, thread_id: str) -> bool:
    """Depois que o grafo terminou, apaga o checkpoint da própria conversa (o grafo não pode apagá-lo por dentro:
    o framework o recriaria no passo seguinte). Devolve True se a conversa acabou."""
    if resultado is None or resultado['motivo_termino'] != 'esquecido':
        return False
    servicos().memoria.apagar_thread(thread_id)
    print('Dados apagados. Conversa encerrada.')
    return True


def main() -> None:
    sessao = sys.argv[1] if len(sys.argv) > 1 else time.strftime('%Y%m%d-%H%M%S')
    thread_id = f"{os.environ.get('USER_ID') or 'local'}:{sessao}"
    cfg = {'configurable': {'thread_id': thread_id}, 'recursion_limit': RECURSION_LIMIT}
    print(f'Conversa {thread_id}  (Enter vazio encerra)')

    pendentes = getattr(grafo.get_state(cfg), 'interrupts', ())
    if pendentes:
        resposta = decidir(pendentes[0].value)
        if resposta is None:
            return
        _traj(cfg).registrar('resposta_humana', resposta=resposta)
        resultado = processar(Command(resume=resposta), cfg)
        mostrar(resultado)
        if encerrar_se_esquecido(resultado, thread_id):
            return

    while True:
        texto = ler('user: ')
        if texto is None:
            print(f'Conversa encerrada. Log: {_traj(cfg).path}')
            return
        resultado = processar({'mensagens': [HumanMessage(texto)]}, cfg)
        if resultado is None:
            return
        mostrar(resultado)
        if encerrar_se_esquecido(resultado, thread_id):
            return


if __name__ == '__main__':
    main()
