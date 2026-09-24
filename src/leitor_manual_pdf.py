import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.tool_call import ToolCall
from interfaces.json_format import createJsonFormat
import os
from openai import OpenAI
import pdfplumber
import json
import time

class LeitorManualPDF(Agent):
    def __init__(self, client:OpenAI, model=None):
        if(model):
            super().__init__('leitor_manual_pdf', client, model)
        else:
            super().__init__('leitor_manual_pdf', client)

        self.tool_calls = []
        self.tool_calls_func_link = {}
        self._create_tool_calls()
        self.send_message(Message('system', self.read_system_prompts('leitor_manual_pdf_prompt.md')))

    def _create_tool_calls(self):
        get_pdf_filename = ToolCall('get_pdf_filename', """
            Utilize para receber uma lista de nomes de arquivos
            de manuais de automóveis disponíveis para leitura.
        """)
        self.tool_calls.append(get_pdf_filename.to_dict())
        self.tool_calls_func_link['get_pdf_filename'] = self._get_pdf_filenames

        read_pdf_pages = ToolCall('read_pdf_pages',"""
            Resposabilidade: ler arquivos de manuais arquivados em formato pdf.
            Utilize assim que tiver o nome do arquivo à ser lido.
        """)
        read_pdf_pages.insert_prop('namefile', {'type':'string','description':'Nome do arquivo pdf à ser lido'})
        read_pdf_pages.insert_prop('duvida_usuario', {'type':'string', 'description':'Duvida do Usuário'})
        read_pdf_pages.insert_prop('palavras_chave', {'type':'array', 'item':{'type':'string'}, 'description':'palavras chaves baseada na dúvida do usuário'})
        self.tool_calls.append(read_pdf_pages.to_dict())
        self.tool_calls_func_link['read_pdf_pages'] = self._read_pdf_pages

    def _get_pdf_filenames(self):
        path_project = Path(__file__).resolve().parent.parent
        path_project = f'{path_project}/databases/manuais/'
        return list(filter(lambda x: str(x).endswith('.pdf'), os.listdir(path_project)))

    def _read_pdf_pages(self, namefile, duvida_usuario, palavras_chave):
        path = Path(__file__).resolve().parent.parent
        path = f"{path}/databases/manuais/{namefile}"

        json_format = createJsonFormat('read_pdf_pages_return', [
            {'name':'trecho_original', 'type':'string'},
            {'name':'resumo', 'type':'string'},
            {'name':'fl_duvida_sanada', 'type':'boolean', 'enum':[True, False]},
        ])

        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                pagina = page.extract_text()

                if(not any(map(lambda x: str(x).lower() in str(pagina).lower(), palavras_chave))): continue
                messages = [
                    {'role':'system', 'content': self.read_system_prompts('tool_call_leitura_pdf.md')},
                    {'role':'system', 'content':f"Dúvida do usuário: {duvida_usuario}."}
                ]
                messages.append(Message('user', pagina).to_dict())
                response_completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    response_format=json_format
                )
                resultado = json.loads(response_completion.choices[0].message.content)
                print(f"página {i+1} lida")
                if(resultado['fl_duvida_sanada']):
                    return resultado
                time.sleep(0.25)

    def run(self):
        json_format_retorno = createJsonFormat('retorno_leitura_pdf',[
            {'name':'duvida_usuario', 'type':'string'},
            {'name':'kws_duvida_usuario', 'type':'array', 'items':{'type':'string'}},
            {'name':'resolucao', 'type':'string'},
        ])
        for _ in range(4):
            sys_message = self.get_answer(tools=self.tool_calls)
            if(sys_message.tool_calls):
                self.send_message(sys_message)
                for tool in sys_message.tool_calls:
                    argumentos = json.loads(tool.function.arguments)
                    result = self.tool_calls_func_link[tool.function.name](**argumentos)
                    self.send_message(Message(
                        role='tool', 
                        tool_call_id= tool.id,
                        content=json.dumps(result)
                    ))
                continue
            self.send_message(Message('system', """
                Devolva em formato de string as informações: 
                    - duvida do usuário (duvida_usuario),
                    - palavras-chave da duvida do usuário (kws_duvida_usuario),
                    - resumo elaborado à partir da leitura do manual (resolucao)   
            """))
            return self.get_answer(
                response_format = json_format_retorno,
                temperature=0
            ).content