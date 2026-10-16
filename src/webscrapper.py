from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
import json
import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup, Comment
from playwright.sync_api import sync_playwright
from src.util import ler_prompt, modelo_em_uso

MAX_TOKENS_EXTRACAO = 4096  # teto de saída da extração por página
CHROMIUM = '/usr/bin/chromium'


class WebScrapper:
    """Busca peças no catálogo web de uma montadora. Só lê: gravar é decisão do grafo, depois da aprovação humana."""

    def __init__(self, client):
        self.client = client

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

    def buscar_candidatas(self, link: str, regra: str, modelo: str, ano: int, motorizacao: str, nome_peca: str) -> dict:
        """Abre o catálogo, percorre as páginas e devolve {'consulta', 'pecas': [...], 'erro'}. Não grava nada."""
        curr_num_page = 1
        mx_num_page = 1

        if(link.endswith('/') or link.endswith('?')): link = link[:-1]

        consulta = regra
        for lacuna, valor in {'<modelo>': modelo, '<ano>': ano, '<motorizacao>': motorizacao, '<nome_peca>': nome_peca}.items():
            consulta = consulta.replace(lacuna, quote_plus(str(valor)))
        link += f'?{consulta}'
        print("--- EXTRAINDO DADOS VIA WEBSCRAPPING ---")

        json_format_return = {'type': 'json_schema', 'json_schema': {'name': 'retorno_webscrapping', 'strict': True, 'schema': {
            'type': 'object',
            'properties': {
                'dados_peca': {
                    'type': 'array',
                    'description': 'Lista de peças encontradas no HTML',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'nome_peca': {'type': 'string', 'description': 'Nome da peça automotiva'},
                            'carros_compativeis': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Lista de carros compatíveis com a peça'},
                            'codigo_peca': {'type': 'string', 'description': 'Código da peça (ex: VW 373201238A)'},
                        },
                        'required': ['nome_peca', 'carros_compativeis', 'codigo_peca'],
                        'additionalProperties': False,
                    },
                },
                'max_pagina': {'type': 'integer', 'description': 'página final do site'},
            },
            'required': ['dados_peca', 'max_pagina'],
            'additionalProperties': False,
        }}}
        sys_prompt = ler_prompt('webscrapper/tool_scrapping.md')
        vistas = set()
        pecas = []
        selector_proximo = (
        "//button[contains(text(), '>') or text()='>' or contains(text(), '»') or contains(@aria-label, 'Next') or contains(@class, 'next') or contains(text(), 'Próximo') or contains(text(), 'Proximo')]"
        " | "
        "//a[contains(text(), '>') or text()='>' or contains(text(), '»') or contains(@aria-label, 'Next') or contains(@class, 'next') or contains(text(), 'Próximo') or contains(text(), 'Proximo')]"
        )

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()

                while curr_num_page <= mx_num_page:
                    print(f'Processando Página {curr_num_page}/{mx_num_page} (URL Atual: {page.url or link})')
                    if curr_num_page == 1:
                        page.goto(link, wait_until="networkidle", timeout=30000)
                    else:
                        botao_proximo = page.locator(selector_proximo).first
                        if not botao_proximo.is_visible():
                            print("Botão '>' não encontrado ou não está visível. Encerrando paginação.")
                            break
                        botao_proximo.click()
                        page.wait_for_load_state("networkidle", timeout=15000)

                    soup = BeautifulSoup(page.content(), 'html.parser')
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

                    # Técnica: extração estruturada com 1 exemplo (one-shot) de card em markdown, no prompt.
                    # Contrato: schema estrito {dados_peca: [{nome_peca, carros_compativeis[], codigo_peca}], max_pagina}.
                    # Impede: tratar links de menu como peça e esquecer a paginação (sem `nav`, max_pagina = 1).
                    response = self.client.chat.completions.create(
                        model=modelo_em_uso(),
                        messages=[
                            {'role': 'system', 'content': sys_prompt},
                            {'role': 'user', 'content': self.processar_html_generico_para_markdown(html_filtrado)},
                        ],
                        response_format=json_format_return,
                        temperature=0,
                        max_tokens=MAX_TOKENS_EXTRACAO
                    )
                    data = json.loads(response.choices[0].message.content)
                    mx_num_page = data.get('max_pagina', mx_num_page)
                    for peca in data.get('dados_peca', []):
                        chave = f"{peca.get('codigo_peca')}_{peca.get('nome_peca')}"
                        if chave not in vistas:
                            vistas.add(chave)
                            pecas.append(peca)
                    curr_num_page += 1
        except Exception as err:
            return {'consulta': link, 'pecas': pecas, 'erro': f'{type(err).__name__}: {err}'}
        return {'consulta': link, 'pecas': pecas, 'erro': None}
