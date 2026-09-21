import sys
import os
import json
import pdfplumber
from pathlib import Path
from openai import OpenAI

sys.path.append(str(Path(__file__).resolve().parent.parent))

from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.tool_call import ToolCall

class LeitorManualPDF(Agent):
    def __init__(self, client: OpenAI, model=None):
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

        tool = ToolCall('read_pdf_pages', """
            Busca no manual do veículo utilizando palavras-chave para encontrar 
            o trecho que responde à dúvida do usuário.
        """)
        tool.insert_prop('namefile', 'string', 'Nome do arquivo pdf a ser lido')
        tool.insert_prop('duvida_usuario', 'string', 'Duvida do Usuario')
        self.tool_calls.append(tool.to_dict())
        self.tool_calls_func_link['read_pdf_pages'] = self._read_pdf_pages

    def _get_pdf_filenames(self):
        path_project = Path(__file__).resolve().parent.parent
        path_project = f'{path_project}/databases/manuais/'
        return list(filter(lambda x: str(x).endswith('.pdf'), os.listdir(path_project)))

    def _read_pdf_pages(self, namefile, duvida_usuario):
        path_projeto = Path(__file__).resolve().parent.parent
        path_pdf = path_projeto / "databases" / "manuais" / namefile

        # 1. Filtra palavras comuns para focar apenas nos termos técnicos
        stop_words = {'qual', 'que', 'devo', 'usar', 'para', 'como', 'onde', 'qual', 'pode'}
        palavras_chave = [
            p.lower().strip('?!.,') for p in duvida_usuario.split() 
            if len(p.strip('?!.,')) > 2 and p.lower() not in stop_words
        ]
        
        paginas_pontuadas = []
        
        # 2. Lê todas as páginas e pontua cada uma
        with pdfplumber.open(path_pdf) as pdf:
            for i, page in enumerate(pdf.pages):
                texto = page.extract_text()
                if texto:
                    texto_lower = texto.lower()
                    # Conta quantas palavras-chave únicas aparecem na página
                    score = sum(1 for palavra in palavras_chave if palavra in texto_lower)
                    
                    # Bônus de pontuação se encontrar combinações exatas (ex: "1.0")
                    if score > 0:
                        paginas_pontuadas.append((score, i+1, texto))

        # 3. Ordena da maior pontuação para a menor
        paginas_pontuadas.sort(key=lambda x: x[0], reverse=True)
        
        # 4. Pega apenas as 2 páginas mais relevantes
        trechos_relevantes = ""
        for score, num_pagina, texto in paginas_pontuadas[:2]:
            trechos_relevantes += f"\n--- Página {num_pagina} ---\n{texto}\n"

        if not trechos_relevantes:
            trechos_relevantes = "O manual não possui informações sobre os termos pesquisados."

        return {"status": "sucesso", "trechos_encontrados": trechos_relevantes}

    def run(self):
        for _ in range(4):
            sys_message = self.get_answer(tools=self.tool_calls)
            if sys_message.tool_calls:
                self.send_message(sys_message)
                for tool in sys_message.tool_calls:
                    argumentos = json.loads(tool.function.arguments)
                    print(f"\nAcionando tool_call:\nfunção: {tool.function.name}\nargumentos: {argumentos}\n")
                    result = self.tool_calls_func_link[tool.function.name](**argumentos)
                    self.send_message(Message(
                        role='tool', 
                        tool_call_id=tool.id,
                        content=json.dumps(result)
                    ))
                continue
            
            return sys_message.content
        