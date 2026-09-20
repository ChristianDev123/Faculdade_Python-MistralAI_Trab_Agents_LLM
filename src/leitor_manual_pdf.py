import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from interfaces.agent import Agent
from interfaces.message import Message
import os
from openai import OpenAI
import json

class LeitorManualPDF(Agent):
    def __init__(self, client:OpenAI, model=None, ):
        super().__init__('leitor_manual_pdf', client, model)
        sys_prompt = self.read_system_prompts('leitor_manual_pdf_prompt.md')
        self.send_message(Message('system', sys_prompt))

    def _get_pdf_filenames():
        path_project = Path(__file__).resolve().parent.parent
        return list(filter(lambda x: str(x).endswith('.pdf'), os.path.dirname(f'{path_project}/manuais/')))

    def run(self):
        sys_message = self.get_answer().content
        print(sys_message)      
        