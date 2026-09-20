import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from interfaces.message import Message
from interfaces.agent import Agent
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from interfaces.json_format import createJsonFormat
import json
load_dotenv()

class Orquestrador(Agent):
    def __init__(self, client:OpenAI, model=None):
        super().__init__(client, model)
        self.json_format_orquestrador = createJsonFormat('descisao_orquestrador',[
            {'name':'pensamento', 'type':'string'},
            {'name':'acao', 'type':'string', 'enum':["RESPONDER_USUARIO", "CHAMAR_SUBAGENTE"]},
            {'name':'conteudo', 'type':'string'},
            {'name':'subagente_destino', 'type':'string', 'enum':['LEITOR MANUAL PDF', 'CONVERSACIONAL']},
        ])

        self.json_format_leitura_manual = createJsonFormat('envio_dados_leitor_manual',[
            {'name':'modelo', 'type':'string'},
            {'name':'ano', 'type':'integer'},
            {'name':'motorizacao', 'type':'string'},
        ])

    def run(self):        
        self.send_message(Message('system', self.read_system_prompts('orquestrador_system_prompt.md')))
        sys_message = json.loads(self.get_answer(response_format=self.json_format_orquestrador).content)
        print(f'Bot: {sys_message['conteudo']}')

        while True:
            user_input = input('user: ').strip()
            if(not user_input): break
            self.send_message(Message('user', user_input))
            sys_message = json.loads(self.get_answer(response_format=self.json_format_orquestrador).content)

            if(sys_message['acao'] == 'RESPONDER_USUARIO'):
                print(f'Bot: {sys_message['conteudo']}')

            elif(sys_message['acao'] == 'CHAMAR_SUBAGENTE'):
                self.send_message(Message('system', 'Apresente os dados coletados na conversa com usuário em um JSON contendo apenas as características do veículo'))
                sys_message = json.loads(self.get_answer(response_format=self.json_format_leitura_manual).content)
                print(sys_message)
        

