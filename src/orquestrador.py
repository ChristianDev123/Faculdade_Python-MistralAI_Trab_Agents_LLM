import sys
from pathlib import Path
PROJECT_PATH = str(Path(__file__).resolve().parent.parent)
sys.path.append(PROJECT_PATH)
from interfaces.message import Message
from interfaces.agent import Agent
from interfaces.tool_call import ToolCall
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from interfaces.json_format import createJsonFormat
import json
import inspect

load_dotenv()

class Orquestrador(Agent):
    def __init__(self, client:OpenAI, agents:list[Agent] = []):
        super().__init__('conversacional', client = client, f_entrada="", f_saida="")
        self.agents = agents
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
        get_all_table_names = ToolCall('get_all_table_names', "Utilize para receber uma lista de nomes de tabelas préviamente criadas")
        self.tool_calls.append(get_all_table_names.to_dict())
        self.tool_calls_func_link['get_all_table_names'] = self._get_all_table_names

        rescue_db_data = ToolCall('rescue_db_data',"Utilize para resgatar dados dentro da base de dados local do projeto.")
        rescue_db_data.insert_prop('tablename', {'type':'string','description':'nome da tabela à ser lida'})
        rescue_db_data.insert_prop('query_filter', {'type':'string', 'description':'Filtros à serem aplicados na busca'})
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

        read_manual_pdf = ToolCall('read_manual_pdf',"Utilize para responder à dúvidas do usuário que não estejam relacionadas à compatibiidade de peças.")
        self.tool_calls.append(read_manual_pdf.to_dict())
        self.tool_calls_func_link['read_manual_pdf'] = self._read_manual_pdf

        execute_scrapping = ToolCall('execute_scrapping',"Utilize para responder à dúvidas do usuário que estejam relacionadas à compatibiidade de peças.")
        self.tool_calls.append(execute_scrapping.to_dict())
        self.tool_calls_func_link['execute_scrapping'] = self._execute_scrapping

    def _get_all_table_names(self):
        agent = next((a for a in self.agents if a.name.upper() == 'REGISTRADOR'), None)
        return agent.tabelas_criadas

    def _rescue_db_data(self, tablename:str, query_filter:list[str] = []):
        agent = next((a for a in self.agents if a.name.upper() == 'REGISTRADOR'), None)
        message_user = f'Resgate todos os dados da tabela {tablename}'
        if(len(query_filter)): message_user += f'\n aplicando os filtros: {query_filter}'
        agent.send_message(Message('user', message_user))
        retorno = agent.run()
        return retorno

    def _insert_db_question(self, modelo:str, ano:str, motorizacao:str, duvida:str, kw_duvidas:list[str], resolucao:str):
        agent = next((a for a in self.agents if a.name.upper() == 'REGISTRADOR'), None)
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
        
    def _write_conversation_log(self, user_id:str, section_id:str):
        logs_path = Path(PROJECT_PATH) / 'logs' / str(user_id) / str(section_id) / 'log.txt'
        logs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(logs_path, 'a', encoding='utf-8') as f:
            f.write(f'{self.messages}')

    def _read_manual_pdf(self):
        agent = next((a for a in self.agents if a.name.upper() == 'LEITOR_MANUAL_PDF'), None)
        self.send_message(Message('user', 'Estruture os dados que você recebeu em JSON'))
        formated_data = self.get_answer(
            temperature = 0,
            response_format = agent.f_entrada
        )
        agent.send_message(Message('user', formated_data))
        return agent.run()

    def _execute_scrapping(self):
        agent = next((a for a in self.agents if a.name.upper() == 'WEBSCRAPPER'), None)
        self.send_message(Message('user', 'Estruture os dados que você recebeu em JSON'))
        formated_data = self.get_answer(
            temperature = 0,
            response_format = agent.f_entrada
        )
        agent.send_message(Message('user', formated_data))
        return agent.run()

    def run(self):        
        for _ in range(10):
            # 1. Faz a chamada SEM forçar response_format estrito no topo 
            # (permitindo que o modelo decida chamar a Tool ou Responder)
            response = self.get_answer(
                tools=self.tool_calls,
                temperature=0
            )

            # 2. Loop de execução de ferramentas
            while getattr(response, 'tool_calls', None) and len(response.tool_calls) > 0:
                self.send_message(response)
                
                for tool in response.tool_calls:
                    func = self.tool_calls_func_link[tool.function.name]
                    argumentos = json.loads(tool.function.arguments)
                    sig = inspect.signature(func)
                    
                    print(f"""
                        --- Acionando TOOL CALL -- 
                        nome: {tool.function.name}
                        argumentos: {argumentos}
                    """)
                    
                    if len(sig.parameters) == 0: result = func()
                    else: result = func(**argumentos)
                    self._write_conversation_log('1','1')        
                    content_to_send = result if isinstance(result, str) else json.dumps(result)

                    self.send_message(Message(
                        role='tool',
                        tool_call_id=tool.id,
                        content=content_to_send
                    ))

                # Reconsulta o modelo para ele processar o retorno da Tool
                response = self.get_answer(
                    tools=self.tool_calls,
                    temperature=0
                )

            # 3. Quando o modelo NÃO chama mais tools, processa a mensagem para o usuário
            if response.content:
                try:
                    # Tenta fazer a leitura do JSON retornado pelo prompt
                    sys_message = json.loads(response.content)
                    if sys_message.get('acao') == 'RESPONDER_USUARIO':
                        print(f"Bot: {sys_message.get('conteudo')}")
                        user_input = input('user: ').strip()
                        if not user_input:
                            break
                        self.send_message(Message('user', user_input))
                except json.JSONDecodeError:
                    # Se não veio JSON estrito, mas o modelo respondeu em texto
                    print(f"Bot: {response.content}")
                    user_input = input('user: ').strip()
                    if not user_input:
                        break
                    self.send_message(Message('user', user_input))
