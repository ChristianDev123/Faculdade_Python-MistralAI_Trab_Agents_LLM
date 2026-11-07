"""O trace de cada execução, nas convenções GenAI do OpenTelemetry. É o único registro do sistema.

Spans: `invoke_agent` (a raiz, uma por execução), `chat <modelo>` (cada chamada ao modelo) e `execute_tool <ferramenta>`.
Uma execução é uma chamada ao grafo: a que para numa aprovação termina como `aguardando_humano`, e a retomada é outra execução
da mesma conversa (`gen_ai.conversation.id`).

Destino: logs/<usuario>/<sessao>/trace.jsonl, um span por linha. Fica na pasta de logs do usuário, então a remoção de dados
o apaga junto. Fora de uma execução (scripts que chamam um nó direto) nada é gravado.
"""
import json
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from src.trajetoria import PROJECT_PATH, VERSAO_SISTEMA, carimbo_prompts, estado_do_codigo
from src.util import modelo_em_uso

AGENTE = 'assistente-automotivo'
LIMITE_RESULTADO = 2000  # caracteres do resultado de ferramenta e da resposta do modelo guardados no trace

_conversa = ContextVar('conversa', default=None)
_silenciadas = set()  # conversas cujos dados foram apagados: a pasta de log não pode ser recriada


def caminho_do_trace(thread_id: str):
    usuario, _, sessao = thread_id.partition(':')
    return PROJECT_PATH / 'logs' / usuario / (sessao or 'sessao') / 'trace.jsonl'


def silenciar(thread_id: str) -> None:
    _silenciadas.add(thread_id)


class ExportadorArquivo(SpanExporter):
    def export(self, spans) -> SpanExportResult:
        for span in spans:
            conversa = span.attributes.get('gen_ai.conversation.id')
            if not conversa or conversa in _silenciadas:
                continue
            caminho = caminho_do_trace(conversa)
            caminho.parent.mkdir(parents=True, exist_ok=True)
            with open(caminho, 'a', encoding='utf-8') as f:
                f.write(json.dumps(json.loads(span.to_json(indent=None)), ensure_ascii=False) + '\n')
        return SpanExportResult.SUCCESS


# Provedor próprio, e não o global: o Chroma também usa OpenTelemetry, e os spans dele não fazem parte deste trace.
_provedor = TracerProvider()
_provedor.add_span_processor(SimpleSpanProcessor(ExportadorArquivo()))
_tracer = _provedor.get_tracer(AGENTE)


def _valor(v):
    return v if isinstance(v, (str, bool, int, float)) else json.dumps(v, ensure_ascii=False, default=str)


def _atributos(**dados) -> dict:
    return {k: _valor(v) for k, v in dados.items() if v is not None}


def _base(operacao: str) -> dict:
    return _atributos(**{'gen_ai.operation.name': operacao, 'gen_ai.conversation.id': _conversa.get()})


def _provedor_do_modelo() -> str:
    return 'ollama' if os.environ.get('MODE') == 'local' else 'groq'


@lru_cache(maxsize=1)
def _carimbo() -> dict:
    """As versões que a raiz registra. Calculadas uma vez por processo: o código e os prompts não mudam com ele no ar."""
    codigo = estado_do_codigo()
    return _atributos(**{
        'agente.versao': VERSAO_SISTEMA, 'agente.commit': codigo['commit'], 'agente.codigo_limpo': codigo['codigo_limpo'],
        'agente.arquivos_alterados': codigo['arquivos_alterados'], 'agente.prompts': carimbo_prompts(),
    })


@contextmanager
def execucao(thread_id: str, entrada: str | None = None, resposta_humana: dict | None = None):
    """A raiz do trace. `entrada` é o texto que a pessoa digitou; `resposta_humana`, o que ela respondeu a uma pausa."""
    token = _conversa.set(thread_id)
    try:
        atributos = {**_base('invoke_agent'), **_carimbo(), **_atributos(**{
            'gen_ai.agent.name': AGENTE, 'gen_ai.provider.name': _provedor_do_modelo(),
            'gen_ai.request.model': modelo_em_uso(), 'agente.entrada': entrada})}
        with _tracer.start_as_current_span(f'invoke_agent {AGENTE}', attributes=atributos) as raiz:
            if resposta_humana is not None:
                # "quem" é o usuário da conversa: o sistema não autentica ninguém (risco aceito, docs/seguranca.md).
                raiz.add_event('aprovacao_humana', _atributos(quem=thread_id.partition(':')[0], quando=time.strftime('%Y-%m-%dT%H:%M:%S%z'), resposta=resposta_humana))
            try:
                yield raiz
            except Exception:
                raiz.set_attribute('agente.termino', 'erro_nao_tratado')
                raise
    finally:
        _conversa.reset(token)


def concluir(raiz, resultado: dict) -> None:
    """Grava na raiz como a execução terminou: o motivo de término, a saída ou a pausa."""
    if '__interrupt__' in resultado:
        pausa = resultado['__interrupt__'][0].value
        raiz.set_attribute('agente.termino', 'aguardando_humano')
        raiz.add_event('pausa', _atributos(acao=pausa['acao'], pausado_em=pausa.get('pausado_em'), texto=pausa['texto']))
        return
    saida = resultado['saida']
    raiz.set_attributes(_atributos(**{'agente.termino': resultado['motivo_termino'], 'agente.situacao': saida['situacao'],
                                      'agente.suficiencia': saida['suficiencia'], 'agente.saida': saida}))


def evento(nome: str, **dados) -> None:
    trace.get_current_span().add_event(nome, _atributos(**dados))


def chamar_modelo(client, **parametros):
    """O único caminho até o modelo: abre o span `chat`, com modelo e tokens."""
    modelo = parametros['model']
    atributos = {**_base('chat'), **_atributos(**{'gen_ai.request.model': modelo, 'gen_ai.provider.name': _provedor_do_modelo()})}
    with _tracer.start_as_current_span(f'chat {modelo}', attributes=atributos) as span:
        resposta = client.chat.completions.create(**parametros)
        uso = getattr(resposta, 'usage', None)
        if uso is not None:
            span.set_attributes({'gen_ai.usage.input_tokens': uso.prompt_tokens, 'gen_ai.usage.output_tokens': uso.completion_tokens})
        escolha = resposta.choices[0]
        span.set_attribute('gen_ai.response.finish_reasons', [str(escolha.finish_reason)])
        span.add_event('resposta_do_modelo', _atributos(conteudo=(escolha.message.content or '')[:LIMITE_RESULTADO]))
        return resposta


@contextmanager
def ferramenta(nome: str, **argumentos):
    atributos = {**_base('execute_tool'), **_atributos(**{'gen_ai.tool.name': nome, 'gen_ai.tool.call.id': uuid.uuid4().hex, 'agente.tool.argumentos': argumentos})}
    with _tracer.start_as_current_span(f'execute_tool {nome}', attributes=atributos) as span:
        yield span


def registrar_resultado(span, resultado) -> None:
    span.set_attribute('agente.tool.resultado', str(_valor(resultado))[:LIMITE_RESULTADO])


def como_ferramenta(nome: str, argumentos):
    """Faz de um nó do grafo uma ferramenta no trace. `argumentos(state)` diz o que ela recebeu; o resultado é o que o nó devolveu.
    Erro de ferramenta vira status ERROR no span: é o que alimenta a taxa de erro por ferramenta."""
    def decorador(func):
        @wraps(func)
        def interno(state, config):
            with ferramenta(nome, **argumentos(state)) as span:
                saida = func(state, config)
                registrar_resultado(span, saida)
                erro = saida.get('erro')
                if erro and erro.get('origem') != 'sem_base':
                    span.set_status(Status(StatusCode.ERROR, erro['mensagem']))
                return saida
        return interno
    return decorador
