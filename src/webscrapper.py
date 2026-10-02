from pathlib import Path
import sys
sys.path.append(Path(__file__).resolve().parent.parent)
from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.json_format import createJsonFormat
from openai import Client


class WebScrapper(Agent):
    def __init__(self, client:Client, register:Agent):
        super().__init__('webscrapper', client)
        self.register = register
    
    def _get_catalog_site(self, make:str):
        # Make -> Fabricante
        return_format = createJsonFormat('retorno_tool_web_catalogo',[
            {'name':'fabricante', 'type':'string'},
            {'name':'link_webscrapper', 'type':'string'}
        ])

        messages = [Message('system',self.read_system_prompts('webscrapper/tool_webcatalog.md')).to_dict()]
        self.register.send_message(Message('user', 'Resgate os links de catálogo de Sites'))
        messages.append(Message('user',f"""
            Lista de Links: {self.register.run()}
            Fabricante Procurada: {make}
        """).to_dict())
        return self.client.chat.completions.create(
            model = self.model,
            messages = messages,
            response_format = return_format
        ).choices[0].message.content