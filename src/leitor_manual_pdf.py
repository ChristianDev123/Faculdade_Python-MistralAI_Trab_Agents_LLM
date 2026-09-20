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

        tool = ToolCall('read_pdf_pages',"""
            Resposabilidade: ler arquivos de manuais arquivados em formato pdf.
            Utilize assim que tiver o nome do arquivo à ser lido.
        """)
        tool.insert_prop('namefile', 'string', 'Nome do arquivo pdf à ser lido')
        tool.insert_prop('duvida_usuario', 'string', 'Duvida do Usuário')
        self.tool_calls.append(tool.to_dict())
        self.tool_calls_func_link['read_pdf_pages'] = self._read_pdf_pages

    def _get_pdf_filenames(self):
        path_project = Path(__file__).resolve().parent.parent
        path_project = f'{path_project}/databases/manuais/'
        return list(filter(lambda x: str(x).endswith('.pdf'), os.listdir(path_project)))

    def _read_pdf_pages(self, namefile, duvida_usuario):
        path = Path(__file__).resolve().parent.parent
        path = f"{path}/databases/manuais/{namefile}"
        json_format = createJsonFormat('read_pdf_pages_return', [
            {'name':'num_pagina', 'type':'integer'},
            {'name':'fl_contem_info', 'type':'boolean'},
            {'name':'descricao', 'type':'string'},
        ])

        with pdfplumber.open(path) as pdf:
            qtd_paginas = len(pdf.pages)
            while qtd_paginas > 1:
                messages = [
                    {
                        'role':'system',
                        'content':f"""
                            Você é um assistente de mecânico automotivo.
                            O usuário informou a dúvida: {duvida_usuario}.
                            O usuário te enviará páginas de pdf,
                            identifique entre as páginas a informação que o usuário
                            te solicitou anteriormente.
                            Devolva em um JSON com as informações: 
                            num_pagina (número da página);
                            fl_contem_info (True/False);
                            descricao;
                            Se a página contém informações que o usuário solicitou, 
                            preencha o campo descrição com um breve resumo do que a página especifica.
                            Se não, mantenha o campo descrição com string vazia.
                        """
                    }
                ]
                messages.append(Message('user', pdf.pages[qtd_paginas - 1].extract_text()).to_dict())
                response_completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    response_format=json_format
                )
                resultado = json.loads(response_completion.choices[0].message.content)
                if(resultado['fl_contem_info']):
                    return resultado
                print(f"página {qtd_paginas-1} lida")
                qtd_paginas -= 1

    def run(self):
        for _ in range(4):
            sys_message = self.get_answer(tools=self.tool_calls)
            if(sys_message.tool_calls):
                self.send_message(sys_message)
                for tool in sys_message.tool_calls:
                    argumentos = json.loads(tool.function.arguments)
                    print(f"""
                        Acionando tool_call:
                        função: {tool.function.name}
                        argumentos: {argumentos}
                    """)
                    result = self.tool_calls_func_link[tool.function.name](**argumentos)
                    self.send_message(Message(
                        role='tool', 
                        tool_call_id= tool.id,
                        content=json.dumps(result)
                    ))
                continue
            print(sys_message.content)