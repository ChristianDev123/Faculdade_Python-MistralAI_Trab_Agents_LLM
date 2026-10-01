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
    def __init__(self, client:OpenAI, model=None, agents:list[Agent] = []):
        if(model):
            super().__init__('conversacional',client, model)
        else:
            super().__init__('conversacional',client)

        self.agents = agents
        self.json_format_orquestrador = createJsonFormat('descisao_orquestrador',[
            {'name':'pensamento', 'type':'string'},
            {'name':'acao', 'type':'string', 'enum':["RESPONDER_USUARIO", "CHAMAR_SUBAGENTE"]},
            {'name':'conteudo', 'type':'string'},
            {'name':'subagente_destino', 'type':'string', 'enum':['CONVERSACIONAL'] + [str(agent.name).upper() for agent in agents]},
        ])
        self.send_message(Message('system', self.read_system_prompts('orquestrador_system_prompt.md')))

    def _call_sub_agent(self, sub_agent_name):
        agent = next((a for a in self.agents if a.name.upper() == sub_agent_name), None)
        if not agent:
            raise Exception(f"Erro: Subagente '{sub_agent_name}' não encontrado.")
        messages = [{"role":'system', "content":'Formate em JSON todos os dados enviados pelo usuario.'}]
        messages = messages + [message for message in self.messages if (message['role'] == 'user' or str(message['content']).lower().startswith('retorno agente'))]
        formated_data = self.client.chat.completions.create(
            model= self.model,
            messages=messages,
            temperature=0
        ).choices[0].message.content
        print(f"""
            --- ACIONANDO SUBAGENTE ---
            - nm_subagente: {agent.name}
            - dados enviados: {formated_data}
        """)
        agent.send_message(Message('user', formated_data))
        resultado_subagente = agent.run()
        self.send_message(Message('user', f"Retorno agente {agent.name}: {resultado_subagente}"))
        
    def run(self):        
        for _ in range(10):
            sys_message = json.loads(self.get_answer(response_format=self.json_format_orquestrador).content)
            
            if sys_message['acao'] == 'RESPONDER_USUARIO':
                print(f"Bot: {sys_message['conteudo']}")
                user_input = input('user: ').strip()
                if not user_input:
                    break
                self.send_message(Message('user', user_input))

            elif sys_message['acao'] == 'CHAMAR_SUBAGENTE':
                destino = sys_message['subagente_destino'].upper()
                self._call_sub_agent(destino)
                

                
                
