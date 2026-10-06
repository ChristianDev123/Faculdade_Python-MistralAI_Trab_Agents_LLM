from pathlib import Path
import sys
sys.path.append(Path(__file__).resolve().parent.parent)
from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.json_format import createJsonFormat
from interfaces.tool_call import ToolCall
import requests
import json
import inspect
from openai import Client
from bs4 import BeautifulSoup, Comment
from playwright.sync_api import sync_playwright
class WebScrapper(Agent):
    def __init__(self, client:Client, register:Agent):
        super().__init__('webscrapper', client)
        self.register = register
        self.send_message(Message('system',self.read_system_prompts('webscrapper/geral.md')))
        self.tool_calls = []
        self.tool_calls_links = {}
        self._create_tool_calls()

    def _create_tool_calls(self):
        get_catalog_site = ToolCall('get_catalog_site', '''
            Devolve o webcatalogo previamente cadastrado de uma montadora.
        ''')
        get_catalog_site.insert_prop('make', {'type':'string', 'description':'fabricante do veículo'})
        self.tool_calls.append(get_catalog_site.to_dict())
        self.tool_calls_links[get_catalog_site.name] = self._get_catalog_site

        get_data = ToolCall('get_data', 'Executa Webscrapping sobre o link informado')
        get_data.insert_prop('link', {'type':'string', 'description':'endereço do webcatalogo à ser consultado'})
        self.tool_calls.append(get_data.to_dict())
        self.tool_calls_links[get_data.name] = self._get_data

    def _get_catalog_site(self, make:str):
        # Make -> Fabricante
        return_format = createJsonFormat('retorno_tool_web_catalogo',[
            {'name':'fabricante', 'type':'string'},
            {'name':'link', 'type':'string'},
            {'name':'regra', 'type':'string'}
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

    def _get_data(self, link:str, regra:str ,nm_modelo:str, ano:int, motorizacao:str):
        curr_num_page = 1
        mx_num_page = 1
        HEADERS = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        if(link.endswith('/') or link.endswith('?')): link = link[:-1]
        
        link += f'?{
            regra.replace('<modelo>', nm_modelo)\
            .replace('<ano>', str(ano))\
            .replace('<motorizacao>', motorizacao)\
        }'
        print(f"""--- EXTRAINDO DADOS VIA WEBSCRAPPING ---""")

        json_format_return = createJsonFormat('retorno_webscrapping', [
            {
                'name': 'dados_peca', 
                'type':'array', 
                'items': {
                    'type': 'object',
                    'properties': {
                        'nome_peca': {'type': 'string', 'description': 'Nome da peça automotiva'},
                        'carros_compativeis': {
                            'type': 'array', 
                            'items': {'type': 'string'}, 
                            'description': 'Lista de carros compatíveis'
                        },
                        'codigo_peca': {'type': 'string', 'description': 'Código da peça (ex: VW 373201238A)'}
                    },
                    'required': ['nome_peca', 'carros_compativeis', 'codigo_peca']
                }, 
                'description': 'Lista de peças encontradas no HTML'
            }, 
            {
                'name':'max_pagina',
                'type':'integer',
                'description':'página final do site'
            }
        ])
        sys_prompt = self.read_system_prompts('webscrapper/tool_scrapping.md')
        pecas_processadas = set()
        with sync_playwright() as p:
            # Usa o Chromium nativo do Arch Linux para evitar dependências ausentes
            browser = p.chromium.launch(
                executable_path="/usr/bin/chromium", 
                headless=True
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            while curr_num_page <= mx_num_page:
                n_link = link.replace('<num_page>', str(curr_num_page))
                print(f'Navegando na Página {curr_num_page}/{mx_num_page}: {n_link}')
                
                try:
                    # 1. Abre a URL e aguarda até que não haja requisições de rede ativas por 500ms (Fetch/XHR do React)
                    page.goto(n_link, wait_until="networkidle", timeout=30000)
                    
                    # 2. Aguarda um elemento chave carregar (opcional, mas recomendado para React)
                    # page.wait_for_selector('a', timeout=5000) 

                except Exception as e:
                    print(f"Erro ao carregar página {n_link} via Playwright: {e}")
                    break

                # 3. Extrai o DOM totalmente renderizado pelo React/JS
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Limpeza de elementos pesados do DOM
                for element in soup(['script', 'style', 'img', 'image', 'path', 'svg', 'rect', 'head', 'footer', 'header']):
                    element.decompose()
                    
                for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                    comment.extract()

                # Sanitização de tags <a> para economizar tokens
                links_tags = []
                for a in soup.find_all('a'):
                    if not a.find_parent('nav') and not a.find('nav'):
                        for attr in list(a.attrs):
                            if attr not in ['href']:
                                del a[attr]
                        
                        texto_a = " ".join(str(a).split())
                        if len(texto_a) > 10:  # Descarta links vazios/curtos
                            links_tags.append(texto_a)

                nav_tags = [" ".join(str(nav).split()) for nav in soup.find_all('nav')]
                
                html_filtrado = "--- LINKS E CARDS DA PAGINA ---\n" + "\n".join(links_tags)
                if nav_tags:
                    html_filtrado += "\n\n--- COMPONENTES DE NAVEGACAO E PAGINACAO ---\n" + "\n".join(nav_tags)

                print(html_filtrado)
                messages = [
                    Message('system', sys_prompt).to_dict(),
                    Message('user', html_filtrado).to_dict()        
                ]  

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=json_format_return,
                    temperature=0
                )

                data = json.loads(response.choices[0].message.content)
                
                mx_num_page = data.get('max_pagina', mx_num_page)
                novas_pecas = 0
                
                for peca in data.get('dados_peca', []):
                    chave_unica = f"{peca.get('codigo_peca')}_{peca.get('nome_peca')}"
                    
                    if chave_unica not in pecas_processadas:
                        pecas_processadas.add(chave_unica)
                        peca['modelo'] = nm_modelo
                        peca['ano_fabricacao'] = ano
                        peca['motorizacao'] = motorizacao
                        
                        self.register.send_message(Message('user', f'Registre essa peça: {peca}'))
                        print(self.register.run())
                        novas_pecas += 1


        
        # while curr_num_page <= mx_num_page:
        #     n_link = link.replace('<num_page>', str(curr_num_page))
        #     print(f'Link: {n_link}')
        #     page = requests.get(n_link, headers=HEADERS)
        #     page = page.text
        #     print(page)
        #     soup = BeautifulSoup(page, 'html.parser')
        #     for element in soup([
        #         'script', 'style', 'img', 'image', 'path', 'svg',
        #         'rect'
        #     ]):
        #         element.decompose()
        #     for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        #         comment.extract()

        #     links_tags = []
        #     for a in soup.find_all('a'):
        #         eh_filha_de_nav = a.find_parent('nav') is not None
        #         tem_filho_nav = a.find('nav') is not None
        #         if not eh_filha_de_nav and not tem_filho_nav:
        #             links_tags.append(str(a))
        #     nav_tags = [str(nav) for nav in soup.find_all('nav')]
            
        #     # Junta as tags em um bloco limpo para a LLM
        #     html_filtrado = "--- LINKS E CARDS DA PAGINA ---\n" + "\n".join(links_tags)
        #     html_filtrado += "\n\n--- COMPONENTES DE NAVEGACAO E PAGINACAO ---\n" + "\n".join(nav_tags)
        #     print(html_filtrado)
        #     messages = [
        #         Message('system', sys_prompt).to_dict(),
        #         Message('user', html_filtrado).to_dict()        
        #     ]  

        #     data = json.loads(self.client.chat.completions.create(
        #         model = self.model,
        #         messages = messages,
        #         response_format = json_format_return,
        #         temperature=0
        #     ).choices[0].message.content)            
        #     mx_num_page = data['max_pagina']
        #     curr_num_page += 1
        #     for peca in data['dados_peca']:
        #         peca['modelo'] = nm_modelo
        #         peca['ano_fabricacao'] = ano
        #         peca['motorizacao'] = motorizacao
        #         self.register.send_message(Message('user', f'Registre essa peça: {peca}'))
        #         print(self.register.run())
        

    def run(self):
        sys_message = self.get_answer(
            tools=self.tool_calls,
            temperature=0
        )

        while getattr(sys_message, 'tool_calls', None):
            self.send_message(sys_message)
            for tool in sys_message.tool_calls:
                func = self.tool_calls_links[tool.function.name]
                argumentos = json.loads(tool.function.arguments)
                sig = inspect.signature(func)
                if len(sig.parameters) == 0: result = func()
                else: result = func(**argumentos)
                # print(f"""
                #     --- ACIONANDO TOOL CALLS--- 
                #     - name: {tool.function.name}
                #     - argumentos: {tool.function.arguments}
                #     - retorno : {result}
                # """)

                self.send_message(Message(
                    role='tool',
                    tool_call_id=tool.id,
                    content=json.dumps(result)
                ))

            sys_message = self.get_answer(
                tools=self.tool_calls,
                temperature=0
            )

        self.send_message(Message('user', """
            Devolva uma lista contendo todos os dados extraídos via webscrapping.
            Utilize o padrão:
            =========================================
                Peça: xxxxx
                codigo_peca: xxxxxx
                carros_compativeis: [xxx, xxx, xxx]
            =========================================
        """))

        return self.get_answer(
            temperature=0
        ).content