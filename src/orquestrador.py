import sys
from pathlib import Path
PROJECT_PATH = str(Path(__file__).resolve().parent.parent)
sys.path.append(PROJECT_PATH)
from interfaces.message import Message
from interfaces.agent import Agent
from interfaces.tool_call import ToolCall
from dotenv import load_dotenv
from openai import OpenAI
from interfaces.json_format import createJsonFormat
from src.trajetoria import Trajetoria, carimbo_prompts, commit_atual
import json
import inspect
import re
import time

load_dotenv()

MAX_ITERACOES = 10        # voltas do laço externo; cada volta termina esperando uma entrada do usuário
MAX_RODADAS_TOOL = 5      # rodadas seguidas de tool calls dentro de uma volta
MAX_ERROS_SEGUIDOS = 3    # a mesma ferramenta falhando N vezes seguidas encerra a execução
MAX_RESULTADO_LOG = 4000  # caracteres do retorno de ferramenta gravados no log
PARAMS_MODELO = {'temperature': 0, 'max_tokens': 400}
# Fontes de informação do sistema. As demais ferramentas só descrevem as tabelas ou gravam.
FERRAMENTAS_CONSULTA = {'rescue_db_data', 'read_manual_pdf', 'execute_scrapping'}
# Heurística de "o bot está pedindo um dado ao usuário": pergunta, ou verbo de pedido.
PEDIDO_DE_DADO = re.compile(r'\?|\b(informe|informar|preciso saber|gostaria de saber|poderia|qual)\b', re.IGNORECASE)

class Orquestrador(Agent):
    def __init__(self, client:OpenAI, agents:list[Agent] = [], user_id:str = 'local', session_id:str|None = None):
        super().__init__('conversacional', client = client, f_entrada="", f_saida="")
        self.agents = agents
        self.consultas = []  # ferramentas de consulta já concluídas sem erro nesta conversa
        self.user_id = user_id
        self.session_id = session_id or time.strftime('%Y%m%d-%H%M%S')
        self.trajetoria = Trajetoria(self.user_id, self.session_id)
        self.json_format_orquestrador = createJsonFormat('descisao_orquestrador',[
            {'name':'pensamento', 'type':'string'},
            {'name':'acao', 'type':'string', 'enum':["RESPONDER_USUARIO", "CHAMAR_SUBAGENTE"]},
            {'name':'conteudo', 'type':'string'},
        ])
        self.send_message(Message('system', self.read_system_prompts('orquestrador_system_prompt.md')))
        self.tool_calls = []
        self.tool_calls_func_link = {}
        self._create_tool_calls()

    def _create_tool_calls(self):
        get_all_table_names = ToolCall('get_all_table_names', "Utilize para receber as tabelas préviamente criadas e as colunas de cada uma")
        self.tool_calls.append(get_all_table_names.to_dict())
        self.tool_calls_func_link['get_all_table_names'] = self._get_all_table_names

        rescue_db_data = ToolCall('rescue_db_data',"Utilize para resgatar dados dentro da base de dados local do projeto.")
        rescue_db_data.insert_prop('tablename', {'type':'string','description':'nome da tabela à ser lida'})
        rescue_db_data.insert_prop('query_filter', {
            'type':'object',
            'description':'Filtros no formato {coluna: valor}. Use {} para trazer a tabela inteira. Colunas de texto casam por "contém", sem diferenciar maiúsculas; colunas numéricas casam por igualdade.',
            'additionalProperties': True
        })
        self.tool_calls.append(rescue_db_data.to_dict())
        self.tool_calls_func_link['rescue_db_data'] = self._rescue_db_data

        insert_db_question = ToolCall('insert_db_question',"Utilize para registrar dúvidas do usuário em base de dados local do projeto.")
        insert_db_question.insert_prop('modelo', {'type':'string','description':'Modelo do veículo informado pelo usuário'})
        insert_db_question.insert_prop('ano', {'type':'integer','description':'Ano do veículo informado pelo usuário'})
        insert_db_question.insert_prop('motorizacao', {'type':'string','description':'Motorização do veículo informado pelo usuário'})
        insert_db_question.insert_prop('duvida', {'type':'string','description':'Dúvida informada pelo usuário'})
        insert_db_question.insert_prop('kw_duvidas', {'type':'array', 'items':{'type':'string'},'description':'Palavras-chave que identificam a dúvida do usuário'})
        insert_db_question.insert_prop('resolucao', {'type':'string','description':'resolucao da dúvida do usuário'})
        self.tool_calls.append(insert_db_question.to_dict())
        self.tool_calls_func_link['insert_db_question'] = self._insert_db_question

        read_manual_pdf = ToolCall('read_manual_pdf',"""
            Ferramenta obrigatória para dúvidas técnicas que não sejam
            sobre compatibilidade de peças.
            Acione esta ferramenta quando:
            - A consulta à base de dúvidas tiver sido executada;
            - Os registros retornados não forem suficientes para responder;
            - A dúvida não for sobre compatibilidade de peças.
            Não responda tecnicamente ao usuário antes de receber
            o resultado desta ferramenta.
        """)
        self.tool_calls.append(read_manual_pdf.to_dict())
        self.tool_calls_func_link['read_manual_pdf'] = self._read_manual_pdf

        execute_scrapping = ToolCall('execute_scrapping',"Utilize para responder à dúvidas do usuário que estejam relacionadas à compatibiidade de peças.")
        self.tool_calls.append(execute_scrapping.to_dict())
        self.tool_calls_func_link['execute_scrapping'] = self._execute_scrapping

    def _agente(self, nome:str) -> Agent:
        return next((a for a in self.agents if a.name.upper() == nome), None)

    def _get_all_table_names(self):
        return self._agente('REGISTRADOR').esquema()

    def _rescue_db_data(self, tablename:str, query_filter:dict|str|None = None):
        # Consulta por regra em código: o orquestrador já sabe a tabela e os filtros,
        # então não há por que gastar uma chamada de modelo no Registrador para repassá-los.
        if isinstance(query_filter, str):
            try:
                query_filter = json.loads(query_filter) if query_filter.strip() else {}
            except json.JSONDecodeError:
                return {'erro': 'query_filter deve ser um objeto JSON no formato {coluna: valor}'}
        return self._agente('REGISTRADOR').resgatar(tablename, query_filter)

    def _insert_db_question(self, modelo:str, ano:str, motorizacao:str, duvida:str, kw_duvidas:list[str], resolucao:str):
        agent = self._agente('REGISTRADOR')
        message_user = f""" Registre essa dúvida:
            {{
                'modelo':{modelo},
                'ano':{ano},
                'motorizacao':{motorizacao},
                'duvida':{duvida},
                'kws_duvida':{kw_duvidas},
                'resolucao':{resolucao}
            }}
        """
        agent.send_message(Message('user', message_user))
        return agent.run()

    def _read_manual_pdf(self):
        agent = self._agente('LEITOR_MANUAL_PDF')
        self.send_message(Message('user', 'Estruture os dados do veículo e dúvida que você recebeu do usuário em JSON'))
        # Técnica: extração estruturada zero-shot, sobre o histórico da conversa.
        # Contrato: schema estrito `agent.f_entrada` (duvida_usuario, modelo, ano:int, motorizacao).
        # Impede: repassar texto livre ao leitor e ano como string.
        formated_data = self.get_answer(
            temperature = 0,
            response_format = agent.f_entrada
        ).content
        agent.send_message(Message('user', formated_data))
        return agent.run()

    def _execute_scrapping(self):
        agent = self._agente('WEBSCRAPPER')
        self.send_message(Message('user', 'Estruture os dados que você recebeu em JSON'))
        # Técnica: extração estruturada zero-shot, sobre o histórico da conversa.
        # Contrato: schema estrito `agent.f_entrada` (modelo, ano:int, motorizacao, fabricante).
        # Impede: o scrapper receber dados incompletos ou em formato livre.
        formated_data = self.get_answer(
            temperature = 0,
            response_format = agent.f_entrada
        ).content
        try:
            agent.pedido = json.loads(formated_data)
        except json.JSONDecodeError:
            agent.pedido = {}
        agent.send_message(Message('user', formated_data))
        return agent.run()

    @staticmethod
    def _eh_erro(result) -> bool:
        return isinstance(result, dict) and any(str(k).lower() == 'erro' for k in result)

    def _executar_tool(self, tool) -> object:
        """Executa uma tool call. Qualquer falha volta como dado {'erro': ...} para o modelo se corrigir."""
        nome = tool.function.name
        func = self.tool_calls_func_link.get(nome)
        if func is None:
            return {'erro': f"Ferramenta '{nome}' não existe.", 'ferramentas_disponiveis': list(self.tool_calls_func_link)}
        try:
            argumentos = json.loads(tool.function.arguments or '{}')
        except json.JSONDecodeError:
            return {'erro': f"Os argumentos de '{nome}' não são um JSON válido.", 'recebido': tool.function.arguments}

        print(f"""
            --- Acionando TOOL CALL --
            nome: {nome}
            argumentos: {argumentos}
        """)
        inicio = time.time()
        try:
            result = func() if len(inspect.signature(func).parameters) == 0 else func(**argumentos)
        except Exception as err:
            result = {'erro': f'{type(err).__name__}: {err}'}
        self.trajetoria.registrar(
            'tool',
            ferramenta=nome,
            argumentos=argumentos,
            resultado=str(result)[:MAX_RESULTADO_LOG],
            erro=self._eh_erro(result),
            duracao_s=round(time.time() - inicio, 3)
        )
        return result

    def _ler_usuario(self) -> str | None:
        try:
            texto = input('user: ').strip()
        except EOFError:
            return None
        if texto: self.trajetoria.registrar('entrada_usuario', texto=texto)
        return texto or None

    def _human_loop(self, limit_iterator):
        erros_seguidos = {}
        while True:
            if(limit_iterator == 0): return {'finish': 'LIMITE_ITERACOES', 'detalhe': f'Programa terminou por limite de {MAX_ITERACOES} iterações'}
            limit_iterator -= 1

            # Técnica: zero-shot com function calling; o campo `pensamento` do JSON é uma justificativa curta.
            # Contrato: ou `tool_calls`, ou JSON {pensamento, acao: RESPONDER_USUARIO|CHAMAR_SUBAGENTE, conteudo}.
            #   `json_format_orquestrador` não é passado à chamada: o contrato vale só pelo prompt,
            #   e o código tolera texto fora do JSON (ramo JSONDecodeError abaixo).
            # Impede: responder tecnicamente sem consultar ferramenta e pedir vários dados de uma vez.
            response = self.get_answer(
                tools=self.tool_calls,
                **PARAMS_MODELO
            )

            rodadas = 0
            while getattr(response, 'tool_calls', None) and len(response.tool_calls) > 0:
                if rodadas == MAX_RODADAS_TOOL:
                    return {'finish': 'LIMITE_RODADAS_TOOL', 'detalhe': f'Mais de {MAX_RODADAS_TOOL} rodadas seguidas de ferramentas sem resposta ao usuário'}
                rodadas += 1
                self.send_message(response)

                for tool in response.tool_calls:
                    result = self._executar_tool(tool)

                    nome = tool.function.name
                    if self._eh_erro(result):
                        erros_seguidos[nome] = erros_seguidos.get(nome, 0) + 1
                        if erros_seguidos[nome] >= MAX_ERROS_SEGUIDOS:
                            return {'finish': 'ERRO_SISTEMICO', 'ferramenta': nome, 'erro': result}
                    else:
                        erros_seguidos[nome] = 0
                        if nome in FERRAMENTAS_CONSULTA: self.consultas.append(nome)

                    content_to_send = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
                    self.send_message(Message(
                        role='tool',
                        tool_call_id=tool.id,
                        content=content_to_send
                    ))

                # Reconsulta o modelo para ele processar o retorno da Tool
                response = self.get_answer(
                    tools=self.tool_calls,
                    **PARAMS_MODELO
                )

            if response.content:
                try:
                    sys_message = json.loads(response.content)
                except json.JSONDecodeError:
                    # texto fora do JSON é tolerado como resposta ao usuário (ver contrato acima)
                    acao, texto, formato = 'RESPONDER_USUARIO', response.content, 'texto_livre'
                else:
                    ehdict = isinstance(sys_message, dict)
                    acao = sys_message.get('acao') if ehdict else None
                    texto = sys_message.get('conteudo') if ehdict else None
                    formato = 'json'

                if acao != 'RESPONDER_USUARIO':
                    # `acao` não executa nada sozinha: devolve o erro ao modelo, que corrige na próxima volta.
                    self.trajetoria.registrar('acao_invalida', acao=acao)
                    self.send_message(Message('system', (
                        f"A ação '{acao}' não executa nada: ferramenta não se chama escrevendo o nome no campo 'acao'. "
                        "Use o mecanismo de tool call, ou responda com acao RESPONDER_USUARIO. "
                        f"{self._ferramentas_validas()}"
                    )))
                    continue

                if self._afirma_sem_consulta(texto):
                    # Trava: afirmação ao usuário sem nenhuma fonte consultada antes é resposta inventada.
                    self.trajetoria.registrar('resposta_bloqueada', texto=texto, consultas=list(self.consultas))
                    self.send_message(Message('system', (
                        "Resposta recusada: você afirmou algo ao usuário sem ter consultado nenhuma fonte nesta conversa. "
                        "Se ainda faltam dados do veículo, peça-os ao usuário em forma de pergunta. "
                        "Caso contrário, consulte a ferramenta adequada por tool call antes de responder. "
                        f"{self._ferramentas_validas()}"
                    )))
                    continue

                self.trajetoria.registrar('resposta', texto=texto, formato=formato, consultas=list(self.consultas))
                print(f"Bot: {texto}")
                user_input = self._ler_usuario()
                if not user_input:
                    return {'finish': 'ENCERRADO_PELO_USUARIO', 'detalhe': 'O usuário terminou o programa ao não enviar input.'}
                self.send_message(Message('user', user_input))

    def _ferramentas_validas(self) -> str:
        return (f"Ferramentas válidas: {list(self.tool_calls_func_link)}. "
                f"Fontes de consulta: {sorted(FERRAMENTAS_CONSULTA)}.")

    def _afirma_sem_consulta(self, texto) -> bool:
        """Código decide (não o modelo): pedir dado ao usuário é livre; afirmar algo exige consulta prévia."""
        if self.consultas:
            return False
        return not PEDIDO_DE_DADO.search(texto or '')

    def _carimbo(self) -> dict:
        return {
            'commit': commit_atual(),
            'modelos': {a.name: a.model for a in [self, *self.agents]},
            'parametros_orquestrador': PARAMS_MODELO,
            'limites': {
                'max_iteracoes': MAX_ITERACOES,
                'max_rodadas_tool': MAX_RODADAS_TOOL,
                'max_erros_seguidos': MAX_ERROS_SEGUIDOS,
            },
            'prompts': carimbo_prompts(),
        }

    def run(self):
        self.trajetoria.registrar('inicio', user_id=self.user_id, session_id=self.session_id, **self._carimbo())
        total_execution_time = time.time()
        finish_reason = self._human_loop(MAX_ITERACOES)
        total_execution_time = time.time() - total_execution_time
        self.trajetoria.registrar('termino', tempo_s=round(total_execution_time, 3), **finish_reason)
        print(finish_reason)
        print(f'Tempo total de execução da aplicação: {total_execution_time:.6f} segundos')
        print(f'Trajetória gravada em: {self.trajetoria.path}')
        return finish_reason
