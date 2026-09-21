import sys
from pathlib import Path
sys.path.append(Path(__file__).resolve().parent.parent)
from interfaces.agent import Agent
from interfaces.message import Message
from openai import OpenAI

class Registrador(Agent):
    def __init__(self, client:OpenAI):
        super().__init__('Registrador',client)
        self.input = input
        self.send_message(Message('system',self.read_system_prompts('registrador_system_prompt.md')))

    def _verifica_arquivo_sqlite(self):
        pass

    def _cria_base(self, db_name):
        if(self._verifica_arquivo_sqlite()):
            pass
        pass

    def _insert_base(self, data:dict):
        pass

    def run(self):
        print(self.get_answer().content)
        pass