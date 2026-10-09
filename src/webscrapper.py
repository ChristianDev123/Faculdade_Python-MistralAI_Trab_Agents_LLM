from pathlib import Path
import sys
sys.path.append(Path(__file__).resolve().parent.parent)
from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.json_format import createJsonFormat
from interfaces.tool_call import ToolCall
import json
import inspect
import re
from openai import Client
from bs4 import BeautifulSoup, Comment
from playwright.sync_api import sync_playwright

class WebScrapper(Agent):
    def __init__(self, client:Client, register:Agent):
        f_entrada = createJsonFormat('entrada_webscrapper', [
            {'name':'modelo', 'type':'string'},
            {'name':'ano', 'type':'integer'},
            {'name':'motorizacao', 'type':'string'},
            {'name':'fabricante', 'type':'string'}
        ])
        super().__init__('webscrapper', client, f_entrada=f_entrada, f_saida="")
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
        get_data.insert_prop('link', {'type':'string', 'description':'Endereço do webcatalogo à ser consultado, resgatado em banco de dados'})
        get_data.insert_prop('regra', {'type':'string', 'description':'Regras de consulta do webcatálogo, resgatado em banco de dados'})
        get_data.insert_prop('nm_modelo', {'type':'string', 'description':'Modelo do veículo à ser consultado, informado pelo usuário'})
        get_data.insert_prop('ano', {'type':'string', 'description':'Ano do veículo à ser consultado, informado pelo usuário'})
        get_data.insert_prop('motorizacao', {'type':'string', 'description':'Motorizacao do veículo à ser consultado, informado pelo usuário'})
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

    def processar_html_generico_para_markdown(self, html_content: str, preservar_nav_html: bool = True) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        nav_tags = []
        if preservar_nav_html:
            for nav in soup.find_all("nav"):
                nav_tags.append(str(nav))
                nav.decompose()  
        tags_inuteis = [
            "script",
            "style",
            "svg",
            "path",
            "img",
            "picture",
            "iframe",
            "canvas",
            "head",
            "footer",
            "header",
            "noscript",
            "form",
            "input",
            "button",
        ]
        for tag in soup(tags_inuteis):
            tag.decompose()

        markdown_linhas = []

        # 4. Tratar elementos estruturais e links no corpo do HTML
        # Se o corpo tiver links envelopando múltiplos blocos (cards)
        anchors = soup.find_all("a", href=True)

        if anchors:
            for a in anchors:
                href = a["href"].strip()

                # Extrai todos os blocos de texto/sub-elementos contidos no link
                linhas_texto = []
                for element in a.stripped_strings:
                    texto = element.strip()
                    # Evita duplicar fragmentos repetidos
                    if texto and texto not in linhas_texto:
                        linhas_texto.append(texto)

                if not linhas_texto:
                    continue

                # Se for um card com múltiplos campos (ex: Título, Atributos, Preço)
                if len(linhas_texto) > 1:
                    titulo = linhas_texto[0]
                    detalhes = linhas_texto[1:]

                    block_md = f"### [{titulo}]({href})\n"
                    for det in detalhes:
                        block_md += f"- {det}\n"
                    markdown_linhas.append(block_md)
                else:
                    # Se for um link simples de linha única
                    markdown_linhas.append(f"-[{linhas_texto[0]}]({href})")

            # Remove o link já processado para não duplicar no texto geral
            a.decompose()

        # 5. Processar o texto restante do HTML (textos fora de <a>)
        texto_restante = soup.get_text(separator="\n")
        for linha in texto_restante.splitlines():
            linha_limpa = linha.strip()
            if linha_limpa:
                markdown_linhas.append(linha_limpa)

        # 6. Reanexar os componentes de navegação em HTML (se houver)
        if nav_tags:
            markdown_linhas.append(
                "\n--- COMPONENTES DE NAVEGACAO E PAGINACAO (HTML) ---"
            )
            markdown_linhas.extend(nav_tags)

        # 7. Pós-processamento e compressão drástica de whitespace/quebras
        resultado = "\n".join(markdown_linhas)

        # Substitui múltiplos espaços/tabs por 1 espaço
        resultado = re.sub(r"[ \t]+", " ", resultado)

        # Reduz 3 ou mais quebras de linha para no máximo 2 (\n\n)
        resultado = re.sub(r"\n\s*\n", "\n\n", resultado)

        return resultado.strip()

    def _get_data(self, link:str, regra:str ,nm_modelo:str, ano:int, motorizacao:str):
        curr_num_page = 1
        mx_num_page = 1        
        
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
                'description': 'Lista de peças encontradas no HTML',
                "items": {
                    "type": "object",
                    "properties": {
                    "nome_peca": {
                        "type": "string",
                        "description": "Nome da peça automotiva"
                    },
                    "carros_compativeis": {
                        "type": "array",
                        "items": {
                        "type": "string"
                        },
                        "description": "Lista de carros compatíveis com a peça"
                    },
                    "codigo_peca": {
                        "type": "string",
                        "description": "Código da peça (ex: VW 373201238A)"
                    }
                    },
                    "required": ["nome_peca","carros_compativeis","codigo_peca"],
                    "additionalProperties": False
                }
            }, 
            {
                'name':'max_pagina',
                'type':'integer',
                'description':'página final do site'
            }
        ])
        sys_prompt = self.read_system_prompts('webscrapper/tool_scrapping.md')
        pecas_processadas = set()
        selector_proximo = (
        "//button[contains(text(), '>') or text()='>' or contains(text(), '»') or contains(@aria-label, 'Next') or contains(@class, 'next') or contains(text(), 'Próximo') or contains(text(), 'Proximo')]"
        " | "
        "//a[contains(text(), '>') or text()='>' or contains(text(), '»') or contains(@aria-label, 'Next') or contains(@class, 'next') or contains(text(), 'Próximo') or contains(text(), 'Proximo')]"
        )

        with sync_playwright() as p:
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
                print(f'Processando Página {curr_num_page}/{mx_num_page} (URL Atual: {page.url or link})')
                try:
                    if curr_num_page == 1:
                        page.goto(link, wait_until="networkidle", timeout=30000)
                    else:
                        botao_proximo = page.locator(selector_proximo).first
                        if botao_proximo.is_visible():
                            print("Botão de navegação '>' encontrado. Clicando...")
                            botao_proximo.click()
                            page.wait_for_load_state("networkidle", timeout=15000)
                        else:
                            print("Botão '>' não encontrado ou não está visível. Encerrando paginação.")
                            return {'sucesso':'Botão não encontrado, todos os dados coletados'}
                except Exception as e:
                    print(f"Erro ao carregar ou navegar na página {curr_num_page} via Playwright: {e}")
                    return {'erro', 'Página não encontrada'}

                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                
                for element in soup(['script', 'style', 'img', 'image', 'path', 'svg', 'rect', 'head', 'footer', 'header']):
                    element.decompose()
                    
                for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                    comment.extract()

                links_tags = []
                for a in soup.find_all('a'):
                    if not a.find_parent('nav') and not a.find('nav'):
                        for attr in list(a.attrs):
                            if attr not in ['href']:
                                del a[attr]
                        
                        texto_a = " ".join(str(a).split())
                        if len(texto_a) > 0:
                            links_tags.append(texto_a)

                nav_tags = [" ".join(str(nav).split()) for nav in soup.find_all('nav')]
                
                html_filtrado = "--- LINKS E CARDS DA PAGINA ---\n" + "\n".join(links_tags)
                if nav_tags:
                    html_filtrado += "\n\n--- COMPONENTES DE NAVEGACAO E PAGINACAO ---\n" + "\n".join(nav_tags)

                messages = [
                    Message('system', sys_prompt).to_dict(),
                    Message('user', self.processar_html_generico_para_markdown(html_filtrado)).to_dict()        
                ]   
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=json_format_return,
                    temperature=0,
                    max_completion_tokens=4096
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
                        if(peca.get('carros_compativeis')):
                            arr_carros_comp = peca.get('carros_compativeis')
                            del peca['carros_compativeis']
                            peca['carros_compativeis'] = ','.join(arr_carros_comp)

                        self.register.send_message(Message('user', f'Registre essa peça: {peca}'))
                        self.register.run()
                        novas_pecas += 1

                print(f'{novas_pecas} novas peças inseridas!')
                
                curr_num_page += 1
        return {'sucesso':'Webcatálogo acessado!'}
        
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