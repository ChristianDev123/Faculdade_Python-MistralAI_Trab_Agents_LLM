import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.tool_call import ToolCall
import os
from openai import OpenAI
import json

class LeitorManualPDF(Agent):
    def __init__(self, client:OpenAI, model=None, ):
        super().__init__('leitor_manual_pdf', client, model)
        self.tool_calls = []
        self.tool_calls_func_link = {}
        self._create_tool_calls()
        sys_prompt = self.read_system_prompts('leitor_manual_pdf_prompt.md')
        self.send_message(Message('system', sys_prompt))

    def _create_tool_calls(self):
        tool = ToolCall('get_pdf_filename', """
            Utilize para receber uma lista de nomes de arquivos
            de manuais de automóveis disponíveis para leitura.
        """)
        self.tool_calls.append(tool.to_dict())
        self.tool_calls_func_link['get_pdf_filename'] = self._get_pdf_filenames

    def _get_pdf_filenames(self):
        path_project = Path(__file__).resolve().parent.parent
        path_project = f'{path_project}/databases/manuais/'
        return list(filter(lambda x: str(x).endswith('.pdf'), os.listdir(path_project)))

    def run(self):
        sys_message = self.get_answer(tools=self.tool_calls)
        if(sys_message.tool_calls):
            self.send_message(sys_message)
            for tool in sys_message.tool_calls:
                result = self.tool_calls_func_link[tool.function.name]()
                self.send_message(Message(
                    role='tool', 
                    tool_call_id= tool.id,
                    content=json.dumps(result)
                ))
            sys_message = self.get_answer().content 