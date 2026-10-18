"""Nós e funções de rota do grafo (ver docs/grafo.md).

Quem decide o quê:
  - MODELO: `extrair` (intenção e dados a partir do texto livre), `raspar` (extração da página) e `ler_manual`
    (resposta fundamentada nos trechos). Nada além disso passa por modelo.
  - CÓDIGO: todas as rotas, os portões, a consulta à base, a gravação e o texto da saída.
  - HUMANO: `aprovar_gravacao` e `confirmar_esquecimento`, via interrupt.
"""
import os
import time
from datetime import datetime, timezone
from functools import wraps

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt
from openai import APIError
from pydantic import ValidationError

from src.contrato import Extracao, Fonte, Peca, RespostaAprovacao, RespostaConfirmacao, Saida
from src.estado import LIMPAR, ZERAR
from src.memoria import COLECAO_EPISODICA as COLECAO, JANELA_TOKENS, Memoria, janela_historico, texto_procedural
from src.trajetoria import Trajetoria, carimbo_prompts, estado_do_codigo
from src.util import ler_prompt, modelo_em_uso, tokens_estimados

MAX_TURNOS = int(os.environ.get('MAX_TURNOS') or 15)                      # mensagens do usuário por conversa
MAX_PERGUNTAS_IGUAIS = 3                                                  # mesma pergunta sem resposta: desiste
PRAZO_APROVACAO_HORAS = float(os.environ.get('PRAZO_APROVACAO_HORAS') or 24)
PARAMS_EXTRACAO = {'temperature': 0, 'max_tokens': 300}
MAX_ITENS_TEXTO = 15                                                      # peças listadas no texto de resposta

OBRIGATORIOS = {
    'PECA': ['modelo', 'ano', 'motorizacao', 'fabricante', 'nome_peca'],
    'MANUAL': ['modelo', 'ano', 'duvida'],
}
PERGUNTAS = {
    'intencao': 'Você procura uma peça compatível com o seu veículo ou quer tirar uma dúvida do manual do proprietário?',
    'modelo': 'Qual é o modelo do veículo?',
    'ano': 'Qual é o ano do veículo?',
    'motorizacao': 'Qual é a motorização do veículo (por exemplo 1.0 ou 1.6)?',
    'fabricante': 'Qual é a montadora do veículo?',
    'nome_peca': 'Qual peça você procura?',
    'duvida': 'Qual é a sua dúvida sobre o veículo?',
}
# Conhecimento de domínio para não perguntar o óbvio. Só preenche `fabricante` quando o usuário não o disse.
# Lista curta de propósito: modelo fora dela gera a pergunta da montadora. Ampliar com revisão de quem conhece o domínio.
MODELO_FABRICANTE = {
    'fox': 'Volkswagen', 'gol': 'Volkswagen', 'polo': 'Volkswagen', 'up': 'Volkswagen',
    'corsa': 'Chevrolet', 'onix': 'Chevrolet', 'celta': 'Chevrolet', 'prisma': 'Chevrolet', 'cruze': 'Chevrolet',
    'palio': 'Fiat', 'uno': 'Fiat', 'siena': 'Fiat',
    'corolla': 'Toyota', 'etios': 'Toyota',
    'civic': 'Honda', 'fit': 'Honda',
}
MONTADORAS = ['volkswagen', 'chevrolet', 'fiat', 'toyota', 'honda', 'ford', 'hyundai', 'renault', 'nissan', 'jeep']

_servicos = None
_trajetorias = {}
_silenciados = set()  # conversas cujos dados foram apagados: nada mais é gravado no log delas


def servicos():
    """Cria os serviços na primeira vez que um nó precisa deles (importar o grafo não abre banco nem modelo)."""
    global _servicos
    if _servicos is None:
        from src.config import client
        from src.leitor_manual_pdf import LeitorManualPDF
        from src.registrador import Registrador
        from src.webscrapper import WebScrapper
        _servicos = type('Servicos', (), {})()
        _servicos.client = client
        _servicos.reg = Registrador()
        _servicos.leitor = LeitorManualPDF(client)
        _servicos.scraper = WebScrapper(client)
        _servicos.memoria = Memoria(_servicos.reg, _servicos.leitor.chroma_client)
    return _servicos


def _traj(config) -> Trajetoria:
    thread_id = config['configurable']['thread_id']
    if thread_id not in _trajetorias:
        usuario, _, sessao = thread_id.partition(':')
        _trajetorias[thread_id] = Trajetoria(usuario, sessao or 'sessao')
        _trajetorias[thread_id].registrar('inicio', thread_id=thread_id, **estado_do_codigo(),
                                          modelo=modelo_em_uso(), parametros_extracao=PARAMS_EXTRACAO,
                                          limites={'max_turnos': MAX_TURNOS, 'max_perguntas_iguais': MAX_PERGUNTAS_IGUAIS,
                                                   'prazo_aprovacao_horas': PRAZO_APROVACAO_HORAS},
                                          prompts=carimbo_prompts())
    return _trajetorias[thread_id]


def _usuario(config) -> str:
    return config['configurable']['thread_id'].partition(':')[0]


def _log(config, evento: str, **dados) -> None:
    if config['configurable']['thread_id'] in _silenciados:
        return
    _traj(config).registrar(evento, **dados)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _resumo(dados: dict) -> dict:
    return {k: (v if len(str(v)) < 300 else str(v)[:300] + '…') for k, v in dados.items()}


def registrando(func):
    """Registra no log da trajetória cada nó que terminou: nome, o que escreveu no estado e quanto levou."""
    @wraps(func)
    def interno(state, config):
        inicio = time.time()
        saida = func(state, config)
        _log(config, 'no', no=func.__name__, escreveu=_resumo(saida), duracao_s=round(time.time() - inicio, 3))
        return saida
    return interno


# ----------------------------- apoio -----------------------------

def faltando(state) -> list[str]:
    intencao = state.get('intencao')
    if intencao not in OBRIGATORIOS:
        return ['intencao']
    veiculo = state.get('veiculo') or {}
    valores = {**veiculo, 'nome_peca': state.get('nome_peca'), 'duvida': state.get('duvida')}
    return [campo for campo in OBRIGATORIOS[intencao] if valores.get(campo) in (None, '')]


def normalizar_veiculo(campos: dict) -> dict:
    """Tira a montadora do nome do modelo ("Chevrolet Corsa" -> "Corsa") e completa a montadora de modelo conhecido."""
    modelo = (campos.get('modelo') or '').strip()
    fabricante = campos.get('fabricante')
    for montadora in MONTADORAS + ['vw', 'gm']:
        if modelo.lower().startswith(montadora + ' '):
            modelo = modelo[len(montadora) + 1:].strip()
    fabricante = {'vw': 'Volkswagen', 'gm': 'Chevrolet'}.get((fabricante or '').lower(), fabricante)
    if modelo and not fabricante:
        fabricante = MODELO_FABRICANTE.get(modelo.lower())
    return {**campos, 'modelo': modelo or None, 'fabricante': fabricante}


def _linhas_pecas(pecas: list[dict]) -> str:
    linhas = [f"  {i}. {p['nome_peca']} — código {p['codigo_peca']}" for i, p in enumerate(pecas[:MAX_ITENS_TEXTO], 1)]
    if len(pecas) > MAX_ITENS_TEXTO:
        linhas.append(f"  ... e mais {len(pecas) - MAX_ITENS_TEXTO}")
    return "\n".join(linhas)


def texto_aprovacao(veiculo: dict, candidatas: list[dict]) -> str:
    return (
        f"Vou GRAVAR {len(candidatas)} peça(s) na base local (tabela pecas_automoveis) para "
        f"{veiculo.get('modelo')} {veiculo.get('ano')} {veiculo.get('motorizacao')}, vindas do catálogo da {veiculo.get('fabricante')}:\n"
        + "\n".join(f"  {i}. {p['nome_peca']} — código {p['codigo_peca']}" for i, p in enumerate(candidatas, 1))
        + "\nConsequência: respostas futuras sobre este veículo passam a usar estes dados, sem nova consulta ao catálogo. "
          "Para desfazer, é preciso apagar as linhas da base.\n"
        f"Prazo: {PRAZO_APROVACAO_HORAS:g} h; depois disso nada é gravado.\n"
        'Responda: aprovar | rejeitar | editar remover 3,5 | editar codigo 2 ABC123'
    )


# ----------------------------- nós -----------------------------

@registrando
def entrada(state, config):
    turno = state.get('turno', 0) + 1
    mensagens = state.get('mensagens') or []
    if mensagens:  # o texto exato que a pessoa digitou: sem ele o log não prova de qual entrada saiu a resposta
        _log(config, 'entrada_usuario', turno=turno, texto=mensagens[-1].content)
    return {
        'turno': turno,
        'passos': [ZERAR], 'evidencias': [ZERAR], 'avisos': [ZERAR],
        'consulta': None, 'candidatas': None, 'aprovacao': None, 'gravadas': None, 'leitura': None,
        'registro': None, 'memorizado': None, 'esquecimento': None, 'erro': None, 'pergunta': None, 'saida': None,
        'motivo_termino': None,
        'desvio': 'limite_turnos' if turno > MAX_TURNOS else None,
    }


@registrando
def extrair(state, config):
    # Técnica: few-shot (6 exemplos no prompt) sobre saída estruturada. Zero-shot errava a intenção MANUAL.
    # Contrato: Extracao {intencao: Literal, modelo, ano:int|null, motorizacao, fabricante, nome_peca, duvida}; null = não disse.
    #   O schema garante uma intenção válida, não a certa: a rota seguinte confia no valor, então ele é testado em execução real.
    # Impede: o modelo inventar dado do veículo, e o sistema agir sobre uma intenção que o usuário não expressou.
    # Janela: só as últimas mensagens que cabem no orçamento. O que saiu já está no estado (veículo, intenção).
    sistema = ler_prompt('extracao.md') + '\n\n# Regras aprendidas (escritas por uma pessoa)\n' + texto_procedural('extrair')
    conversa = [{'role': 'user' if isinstance(m, HumanMessage) else 'assistant', 'content': m.content} for m in state['mensagens']]
    enviadas = janela_historico(conversa, JANELA_TOKENS - tokens_estimados(sistema))
    _log(config, 'janela', no='extrair', mensagens_total=len(conversa), mensagens_enviadas=len(enviadas),
         tokens_estimados=tokens_estimados(sistema) + sum(tokens_estimados(m['content']) for m in enviadas))
    historico = [{'role': 'system', 'content': sistema}] + enviadas
    try:
        resposta = servicos().client.chat.completions.create(
            model=modelo_em_uso(), messages=historico, **PARAMS_EXTRACAO,
            response_format={'type': 'json_schema', 'json_schema': {
                'name': 'extracao', 'strict': True, 'schema': Extracao.model_json_schema()}},
        )
        ext = Extracao.model_validate_json(resposta.choices[0].message.content)
    except APIError as err:
        return {'erro': {'origem': 'modelo', 'mensagem': f'{type(err).__name__}: {err}'}, 'passos': ['extrair']}
    except ValueError as err:
        return {'erro': {'origem': 'modelo', 'mensagem': f'Resposta fora do contrato Extracao: {err}'}, 'passos': ['extrair']}

    campos = normalizar_veiculo({'modelo': ext.modelo, 'ano': ext.ano, 'motorizacao': ext.motorizacao, 'fabricante': ext.fabricante})
    atual = state.get('veiculo') or {}
    avisos = [f"Considerei {k} = {v} (antes: {atual[k]})." for k, v in campos.items()
              if v not in (None, '') and atual.get(k) not in (None, '') and str(atual[k]).lower() != str(v).lower()]
    ditos = [k for k, v in campos.items() if v not in (None, '')]
    if campos['modelo'] and atual.get('modelo') and campos['modelo'].lower() != str(atual['modelo']).lower():
        # Outro veículo: o que sobrou do anterior (ano, motorização, montadora) não vale mais.
        descartados = [k for k in ('ano', 'motorizacao', 'fabricante') if campos.get(k) in (None, '') and atual.get(k)]
        for k in descartados:
            campos[k] = LIMPAR
        if descartados:
            avisos.append(f"Como o modelo mudou, descartei {', '.join(descartados)} do veículo anterior.")
    return {
        'intencao': ext.intencao, 'veiculo': campos, 'campos_ditos': ditos,
        'nome_peca': ext.nome_peca if ext.intencao == 'PECA' else None,
        'duvida': ext.duvida if ext.intencao == 'MANUAL' else None,
        'avisos': avisos, 'passos': ['extrair'],
    }


@registrando
def recusar(state, config):
    return {'desvio': 'fora_do_escopo'}


@registrando
def perguntar(state, config):
    campo = faltando(state)[0]
    if state.get('tentativas_pergunta', {}).get(campo, 0) >= MAX_PERGUNTAS_IGUAIS:
        return {'desvio': 'desistiu_apos_3_perguntas', 'pergunta': campo}
    return {'desvio': 'faltam_dados', 'pergunta': PERGUNTAS[campo], 'tentativas_pergunta': {campo: 1}}


@registrando
def consultar_base(state, config):
    s, v = servicos(), state['veiculo']
    if state['intencao'] == 'MANUAL':
        # Memória episódica: pergunta parecida, do mesmo modelo e ano, já respondida antes (similaridade, não texto exato).
        achado = s.memoria.buscar_episodio(state['duvida'], v)
        hit = achado['hit']
        detalhe = (f"pergunta parecida encontrada (similaridade {hit['similaridade']})" if hit
                   else f"nenhuma pergunta parecida (melhor distância {achado['melhor_distancia']}, limiar de corte em memoria.py)")
        fonte = Fonte(tipo='memoria_episodica', origem=COLECAO, evidencia=detalhe)
        return {'consulta': [hit] if hit else [], 'evidencias': [fonte.model_dump()]}
    tabela, filtros = 'pecas_automoveis', {'modelo': v['modelo'], 'ano_fabricacao': v['ano'],
                                          'motorizacao': v['motorizacao'], 'nm_peca': state['nome_peca']}
    linhas = s.reg.resgatar(tabela, filtros)
    if isinstance(linhas, dict):
        return {'erro': {'origem': 'ferramenta', 'mensagem': linhas['erro']}}
    fonte = Fonte(tipo='base_local', origem=tabela, evidencia=f'{len(linhas)} linha(s) com {filtros}')
    return {'consulta': linhas, 'evidencias': [fonte.model_dump()]}


@registrando
def raspar(state, config):
    # Dentro do scraper: os cartões `/peca/<código>/` são lidos em código; só a página sem esse formato vai ao modelo (one-shot, em lotes), e o código é conferido contra o texto.
    # Aqui só se decide, em código, qual catálogo abrir e com quais dados; nada é gravado neste nó.
    s, v = servicos(), state['veiculo']
    catalogos = s.reg.resgatar('webcatalogos', {'fabricante': v['fabricante']})
    if not isinstance(catalogos, list) or not catalogos:
        return {'erro': {'origem': 'sem_base', 'mensagem': f"Não há catálogo cadastrado para a montadora {v['fabricante']}."}}
    achado = s.scraper.buscar_candidatas(catalogos[0]['link'], catalogos[0]['regra'],
                                         v['modelo'], v['ano'], v['motorizacao'], state['nome_peca'])
    modo = 'em código' if set(achado['modo']) == {'codigo'} else ('pelo modelo' if set(achado['modo']) == {'modelo'} else 'em código e pelo modelo')
    fonte = Fonte(tipo='catalogo_web', origem=achado['consulta'],
                  evidencia=f"{len(achado['pecas'])} peça(s) extraída(s) {modo} em {achado['paginas_lidas']} página(s)").model_dump()
    if achado['erro'] and not achado['pecas']:
        return {'erro': {'origem': 'ferramenta', 'mensagem': achado['erro']}, 'passos': ['raspar'], 'evidencias': [fonte]}
    avisos = list(achado['avisos']) + ([f"A raspagem terminou antes do fim ({achado['erro']})."] if achado['erro'] else [])
    candidatas = [Peca(**p).model_dump() for p in achado['pecas']]
    saida = {'candidatas': candidatas, 'passos': ['raspar'], 'evidencias': [fonte], 'avisos': avisos}
    if candidatas:
        # O carimbo de tempo da pausa nasce aqui: o nó da aprovação roda de novo na retomada e não pode recalculá-lo.
        saida['aprovacao'] = {'decisao': None, 'pausado_em': _agora().isoformat()}
    return saida


@registrando
def aprovar_gravacao(state, config):
    # Nada com efeito colateral antes do interrupt: na retomada este nó roda de novo desde o começo.
    candidatas, veiculo = state['candidatas'], state['veiculo']
    pausado_em = datetime.fromisoformat(state['aprovacao']['pausado_em'])
    resposta = interrupt({
        'acao': 'gravar_pecas', 'tabela': 'pecas_automoveis', 'veiculo': veiculo, 'candidatas': candidatas,
        'prazo_horas': PRAZO_APROVACAO_HORAS, 'pausado_em': state['aprovacao']['pausado_em'],
        'texto': texto_aprovacao(veiculo, candidatas),
    })
    agora = _agora()
    decisao, motivo, editada = 'rejeitar', None, False
    try:
        r = RespostaAprovacao.model_validate(resposta)
    except ValidationError as err:
        r, motivo = None, f'resposta fora do contrato: {err.errors()[0]["msg"]}'
    if (agora - pausado_em).total_seconds() > PRAZO_APROVACAO_HORAS * 3600:
        decisao, motivo = 'expirada', f'passou de {PRAZO_APROVACAO_HORAS:g} h sem resposta'
    elif r is not None and r.decisao == 'aprovar':
        decisao = 'aprovar'
        if r.candidatas is not None:
            editada = [p.model_dump() for p in r.candidatas] != candidatas
            candidatas = [p.model_dump() for p in r.candidatas]
            if not candidatas:
                decisao, motivo = 'rejeitar', 'nenhuma peça restou depois da edição'
    elif r is not None:
        motivo = 'rejeitado pela pessoa'
    return {'aprovacao': {'decisao': decisao, 'motivo': motivo, 'editada': editada,
                          'pausado_em': state['aprovacao']['pausado_em'], 'respondido_em': agora.isoformat()},
            'candidatas': candidatas}


@registrando
def gravar(state, config):
    reg, v = servicos().reg, state['veiculo']
    novas = ja_existiam = 0
    erros = []
    for p in state['candidatas']:
        resultado = reg.inserir('pecas_automoveis', {
            'nm_peca': p['nome_peca'], 'codigo_peca': p['codigo_peca'], 'modelo': v['modelo'],
            'ano_fabricacao': v['ano'], 'motorizacao': v['motorizacao'],
            'carros_compatíveis': ','.join(p['carros_compativeis']),
        })
        if resultado.get('erro'): erros.append(resultado['erro'])
        elif resultado['ja_existia']: ja_existiam += 1
        else: novas += 1
    fonte = Fonte(tipo='base_local', origem='pecas_automoveis', evidencia=f'{novas} nova(s), {ja_existiam} já existia(m)')
    return {'gravadas': {'novas': novas, 'ja_existiam': ja_existiam, 'erros': erros}, 'evidencias': [fonte.model_dump()]}


@registrando
def ler_manual(state, config):
    s, v = servicos(), state['veiculo']
    try:
        manual = s.leitor.escolher_manual(v['modelo'], v['ano'])
        if manual is None:
            return {'erro': {'origem': 'sem_base', 'mensagem':
                             f"Não tenho o manual do {v['modelo']} {v['ano']}. Manuais disponíveis: {', '.join(s.leitor.manuais())}."}}
        lido = s.leitor.ler(manual, state['duvida'], v)
    except APIError as err:
        return {'erro': {'origem': 'modelo', 'mensagem': f'{type(err).__name__}: {err}'}, 'passos': ['ler_manual']}
    except Exception as err:
        return {'erro': {'origem': 'ferramenta', 'mensagem': f'{type(err).__name__}: {err}'}, 'passos': ['ler_manual']}
    if 'erro' in lido:
        return {'erro': {'origem': 'ferramenta', 'mensagem': lido['erro']}, 'passos': ['ler_manual']}
    fonte = Fonte(tipo='manual_pdf', origem=manual, evidencia=f"páginas {lido['paginas']}")
    return {'leitura': {**lido['leitura'].model_dump(), 'manual': manual, 'paginas': lido['paginas'],
                        'trechos_descartados': lido['trechos_descartados']},
            'passos': ['ler_manual'], 'evidencias': [fonte.model_dump()]}


@registrando
def registrar_duvida(state, config):
    """Memória episódica: guarda a dúvida respondida (linha na tabela + vetor no índice), só se foi sanada."""
    resultado = servicos().memoria.registrar_episodio(
        _usuario(config), state['veiculo'], state['duvida'], state['leitura']['resumo'])
    return {'registro': resultado}


@registrando
def lembrar(state, config):
    """Memória semântica, leitura: no primeiro turno, preenche o veículo que o usuário já declarou em outra conversa."""
    perfil = servicos().memoria.lembrar_veiculo(_usuario(config))
    if not perfil:
        return {'perfil_lembrado': None}
    fonte = Fonte(tipo='memoria_semantica', origem='memoria_semantica',
                  evidencia=f"veículo declarado em {perfil['created_at'][:10]} ({perfil['declaracoes']} declaração(ões))")
    return {'veiculo': perfil['valor'], 'perfil_lembrado': perfil['valor'], 'evidencias': [fonte.model_dump()]}


@registrando
def memorizar(state, config):
    """Memória semântica, escrita: depois de uma resposta entregue, guarda o veículo. Idempotente (ja_existia)."""
    return {'memorizado': servicos().memoria.memorizar_veiculo(_usuario(config), state['veiculo'])}


@registrando
def confirmar_esquecimento(state, config):
    # Nada com efeito colateral antes do interrupt; contar é só leitura.
    usuario = _usuario(config)
    c = servicos().memoria.contar_usuario(usuario)
    resposta = interrupt({
        'acao': 'esquecer_dados', 'usuario': usuario, 'contagem': c,
        'texto': (
            f"Vou APAGAR todos os dados do usuário {usuario}: {c['fatos_veiculo']} fato(s) sobre o veículo, "
            f"{c['duvidas_registradas']} dúvida(s) registrada(s) e {c['vetores_episodicos']} item(ns) do índice, "
            f"{c['conversas_salvas']} conversa(s) salva(s) (esta inclusive) e {c['arquivos_de_log']} arquivo(s) de log.\n"
            "Não dá para desfazer. Se ninguém confirmar, nada é apagado.\n"
            "Responda: confirmar | cancelar"),
    })
    try:
        decisao = RespostaConfirmacao.model_validate(resposta).decisao
    except ValidationError:
        decisao = 'cancelar'
    return {'esquecimento': {'decisao': decisao}}


@registrando
def esquecer(state, config):
    """Remoção a pedido do titular. A conversa em andamento fica para o fim: a CLI a apaga depois do grafo terminar."""
    thread_id = config['configurable']['thread_id']
    contagens = servicos().memoria.esquecer_usuario(_usuario(config), manter_thread=thread_id)
    _silenciados.add(thread_id)  # a pasta de log acabou de ser apagada: não pode ser recriada por este turno
    return {'esquecimento': {'decisao': 'confirmar', 'contagens': contagens}}


@registrando
def emitir(state, config):
    """Único ponto de saída: monta o texto por código e valida o contrato Saida antes de devolver."""
    saida, motivo = _montar_saida(state)
    mensagens = [AIMessage(content=saida.resultado)]
    if motivo == 'esquecido':
        _silenciados.add(config['configurable']['thread_id'])
    _log(config, 'termino', motivo=motivo, situacao=saida.situacao, suficiencia=saida.suficiencia,
         passos=len(state.get('passos') or []), saida=saida.model_dump())
    return {'saida': saida.model_dump(), 'motivo_termino': motivo, 'mensagens': mensagens}


def _montar_saida(state) -> tuple[Saida, str]:
    fontes = [Fonte(**f) for f in state.get('evidencias') or []] or [Fonte(tipo='nenhuma', origem='sistema', evidencia='sem consulta')]
    v = state.get('veiculo') or {}
    notas = list(state.get('avisos') or [])
    perfil, ditos = state.get('perfil_lembrado') or {}, state.get('campos_ditos') or []
    if state.get('intencao') in OBRIGATORIOS and [k for k in perfil if k not in ditos and v.get(k) == perfil[k]]:
        lembrado = ' '.join(str(perfil[k]) for k in ('modelo', 'ano', 'motorizacao') if perfil.get(k))
        notas.append(f"Usei o veículo que você informou antes ({lembrado}). Se mudou, é só dizer.")
    avisos = ''.join(f"\nObs.: {a}" for a in notas)
    carro = f"{v.get('modelo')} {v.get('ano')}" + (f" {v['motorizacao']}" if v.get('motorizacao') else '')

    def saida(situacao, texto, suficiencia, dados=None, pergunta=None):
        return Saida(resultado=texto + avisos, dados=dados, fonte=fontes, suficiencia=suficiencia,
                     situacao=situacao, pergunta_pendente=pergunta)

    desvio = state.get('desvio')
    if desvio == 'limite_turnos':
        return saida('erro', f'Esta conversa chegou ao limite de {MAX_TURNOS} mensagens. Inicie uma nova conversa.', False), 'limite_turnos'
    if desvio == 'fora_do_escopo':
        return saida('fora_do_escopo', 'Eu só informo peças compatíveis com o veículo e respostas do manual do proprietário. '
                     'Não faço compra, reserva, cotação de preço nem diagnóstico de defeito.', False), 'fora_do_escopo'
    if desvio == 'faltam_dados':
        return saida('faltam_dados', state['pergunta'], False, pergunta=state['pergunta']), 'faltam_dados'
    if desvio == 'desistiu_apos_3_perguntas':
        return saida('faltam_dados', f"Perguntei {MAX_PERGUNTAS_IGUAIS} vezes sobre \"{state['pergunta']}\" e não obtive a informação. "
                     'Sem ela não consigo continuar; reformule o pedido ou procure o balcão.', False), 'desistiu_apos_3_perguntas'

    esquecimento = state.get('esquecimento')
    if esquecimento:
        if esquecimento['decisao'] == 'confirmar':
            c = esquecimento['contagens']
            return saida('esquecido', (
                f"Apaguei seus dados: {c['fatos_veiculo']} fato(s) sobre o veículo, {c['duvidas_registradas']} dúvida(s) "
                f"registrada(s), {c['vetores_episodicos']} item(ns) do índice, {c['conversas_salvas']} conversa(s) salva(s) "
                f"e {c['arquivos_de_log']} arquivo(s) de log. Esta conversa também é apagada ao terminar."), True), 'esquecido'
        return saida('rejeitado', 'Cancelei: nada foi apagado.', False), 'esquecimento_recusado'

    erro = state.get('erro')
    if erro:
        if erro['origem'] == 'sem_base':
            return saida('sem_base', erro['mensagem'], False), 'sem_base'
        motivo = 'erro_modelo' if erro['origem'] == 'modelo' else 'erro_ferramenta'
        return saida('erro', f"Não consegui concluir a consulta: {erro['mensagem']}", False), motivo

    aprovacao = state.get('aprovacao') or {}
    if aprovacao.get('decisao') == 'expirada':
        return saida('expirado', f"A aprovação não veio a tempo ({aprovacao['motivo']}). Nada foi gravado.", False), 'aprovacao_expirada'
    if aprovacao.get('decisao') == 'rejeitar':
        return saida('rejeitado', f"Não gravei as peças encontradas ({aprovacao.get('motivo')}). Nada foi alterado na base.", False), 'rejeitado_pelo_humano'

    if state.get('gravadas') is not None:
        g, pecas = state['gravadas'], state['candidatas']
        texto = (f"Encontrei {len(pecas)} peça(s) para {carro} no catálogo da {v['fabricante']} e gravei na base "
                 f"({g['novas']} nova(s), {g['ja_existiam']} já existia(m)):\n{_linhas_pecas(pecas)}")
        return saida('respondido', texto, True, dados=[Peca(**p) for p in pecas]), 'respondido'

    if state['intencao'] == 'PECA':
        linhas = state.get('consulta') or []
        # Peça sem código no catálogo ("N/A") não é resposta: a regra do domínio é dizer que não encontrou, nunca aproximar.
        com_codigo = [r for r in linhas if (r['codigo_peca'] or '').strip().upper() not in ('', 'N/A')]
        if linhas and not com_codigo:
            nomes = ', '.join(sorted({r['nm_peca'] for r in linhas}))
            return saida('sem_base', f"Encontrei \"{nomes}\" para {carro} no catálogo, mas sem código cadastrado. "
                         'Sem o código não indico a peça; confirme no balcão ou com o distribuidor.', False), 'sem_base'
        if com_codigo:
            pecas = [Peca(nome_peca=r['nm_peca'], codigo_peca=r['codigo_peca'],
                          carros_compativeis=[c.strip() for c in (r['carros_compatíveis'] or '').split(',') if c.strip()]) for r in com_codigo]
            texto = f"Encontrei {len(pecas)} peça(s) para {carro} na base local:\n{_linhas_pecas([p.model_dump() for p in pecas])}"
            if len(com_codigo) < len(linhas):
                texto += f"\n({len(linhas) - len(com_codigo)} outra(s) correspondência(s) sem código cadastrado não foram listadas.)"
            return saida('respondido', texto, True, dados=pecas), 'respondido'
        return saida('sem_base', f"Não encontrei \"{state['nome_peca']}\" para {carro} na base local nem no catálogo.", False), 'sem_base'

    leitura = state.get('leitura')
    if leitura:
        if leitura['sanada']:
            texto = f"{leitura['resumo']}\n(Manual {leitura['manual']}, páginas {leitura['paginas']})"
            return saida('respondido', texto, True), 'respondido'
        texto = (f"O manual {leitura['manual']} não traz uma resposta clara para essa dúvida. {leitura['resumo']} "
                 'Consulte a concessionária para confirmar.')
        return saida('sem_base', texto, False), 'sem_base'
    linhas = state.get('consulta') or []
    if linhas:
        texto = (f"Já respondi uma pergunta parecida para {carro} (similaridade {linhas[0]['similaridade']}): "
                 f"{linhas[0]['resolucao']}")
        return saida('respondido', texto, True), 'respondido'
    return saida('erro', 'O fluxo terminou sem resultado: estado inesperado.', False), 'erro_ferramenta'


# ----------------------------- rotas (todas decididas por código) -----------------------------

def rota_pos_entrada(state) -> str:
    if state.get('desvio') == 'limite_turnos': return 'emitir'
    return 'lembrar' if state['turno'] == 1 else 'extrair'


def rota_pos_extracao(state) -> str:
    if state.get('erro'): return 'emitir'
    if state.get('intencao') == 'ESQUECER': return 'confirmar_esquecimento'
    if state.get('intencao') == 'FORA_DO_ESCOPO': return 'recusar'
    return 'perguntar' if faltando(state) else 'consultar_base'


def rota_pos_base(state) -> str:
    if state.get('erro') or state.get('consulta'): return 'emitir'
    return 'raspar' if state['intencao'] == 'PECA' else 'ler_manual'


def rota_pos_raspagem(state) -> str:
    return 'aprovar_gravacao' if not state.get('erro') and state.get('candidatas') else 'emitir'


def rota_pos_aprovacao(state) -> str:
    return 'gravar' if state['aprovacao']['decisao'] == 'aprovar' else 'emitir'


def rota_pos_manual(state) -> str:
    return 'registrar_duvida' if not state.get('erro') and state['leitura']['sanada'] else 'emitir'


def rota_pos_confirmacao(state) -> str:
    return 'esquecer' if state['esquecimento']['decisao'] == 'confirmar' else 'emitir'


def rota_pos_emissao(state) -> str:
    """Só o que foi entregue com base (`respondido`) vira memória."""
    return 'memorizar' if state.get('motivo_termino') == 'respondido' else '__end__'
