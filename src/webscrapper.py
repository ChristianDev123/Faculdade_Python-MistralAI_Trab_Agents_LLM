from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
import json
import re
import time
import unicodedata
from urllib.parse import quote_plus
from bs4 import BeautifulSoup, Comment
from playwright.sync_api import sync_playwright
from src.util import ler_prompt, modelo_em_uso

MAX_TOKENS_EXTRACAO = 4096  # teto de saída da extração por lote (só na reserva com modelo)
CHROMIUM = '/usr/bin/chromium'

# Tetos da raspagem: sem eles, a quantidade de páginas era a que o modelo dissesse (chegou a dizer 43) e o tempo não tinha limite.
# O de tempo é conferido entre páginas e entre lotes; uma única chamada ao modelo já tem o seu (LLM_TIMEOUT).
MAX_PAGINAS = 3
MAX_SEGUNDOS = 120
# Tamanho de cada lote enviado ao modelo na reserva. O Ollama corta, em silêncio e pelo começo, o que passa do contexto (4096 por padrão);
# 5.000 caracteres da página (~2.400 tokens) mais o prompt (~900) cabem com folga, e nenhum lote perde o prompt de sistema.
LOTE_CARACTERES = 5000
# Cartão de peça no markdown: "### [Nome](/peca/<código>/<slug>)". O código vem do endereço do link, não de um modelo.
CABECALHO_CARTAO = re.compile(r'### \[(?P<nome>[^\]]+)\]\(/peca/(?P<codigo>[^/\s)]+)/[^)\s]*\)')
SELETOR_PROXIMO = (
    "//button[contains(text(), '>') or text()='>' or contains(text(), '»') or contains(@aria-label, 'Next') or contains(@class, 'next') or contains(text(), 'Próximo') or contains(text(), 'Proximo')]"
    " | "
    "//a[contains(text(), '>') or text()='>' or contains(text(), '»') or contains(@aria-label, 'Next') or contains(@class, 'next') or contains(text(), 'Próximo') or contains(text(), 'Proximo')]"
)

FORMATO_RETORNO = {'type': 'json_schema', 'json_schema': {'name': 'retorno_webscrapping', 'strict': True, 'schema': {
    'type': 'object',
    'properties': {
        'dados_peca': {
            'type': 'array',
            'description': 'Lista de peças encontradas no texto',
            'items': {
                'type': 'object',
                'properties': {
                    'nome_peca': {'type': 'string', 'description': 'Nome da peça automotiva'},
                    'carros_compativeis': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Lista de carros compatíveis com a peça'},
                    'codigo_peca': {'type': 'string', 'description': 'Código da peça, copiado do texto (ex: VW 373201238A)'},
                },
                'required': ['nome_peca', 'carros_compativeis', 'codigo_peca'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['dados_peca'],
    'additionalProperties': False,
}}}


def _dobrar(texto: str) -> str:
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', str(texto).lower()) if not unicodedata.combining(c)))


def codigo_esta_no_texto(codigo: str, texto: str) -> bool:
    """O código tem forma de código (5 ou mais caracteres, com algum dígito) e aparece no texto como item próprio, sem ser pedaço de outro número?
    É a verificação que pega o código inventado e o preço reformatado ("2097.65" a partir de "2.097,65")."""
    codigo = str(codigo).strip()
    if len(codigo) < 5 or not any(c.isdigit() for c in codigo):
        return False
    return re.search(r'(?<![\w.,])' + re.escape(_dobrar(codigo)) + r'(?![\w])', _dobrar(texto)) is not None


def ler_cartoes(markdown: str) -> list[dict]:
    """Lê em código os cartões `### [nome](/peca/<código>/<slug>)` do markdown. Devolve [] se a página não tem esse formato."""
    pecas = []
    for bloco in re.split(r'(?m)^(?=### \[)', markdown):
        m = CABECALHO_CARTAO.match(bloco)
        if not m:
            continue
        detalhes = [l[2:].strip() for l in bloco.splitlines()[1:] if l.startswith('- ')]
        aplicacoes = []
        descritores = detalhes  # sem "Aplicações:", tudo o que o cartão diz da peça é descritor
        if 'Aplicações:' in detalhes:
            i = detalhes.index('Aplicações:')
            descritores = detalhes[:i]
            if i + 1 < len(detalhes) and not detalhes[i + 1].endswith(':'):
                aplicacoes = [a.strip() for a in detalhes[i + 1].split(',') if a.strip()]
        # O que vem antes de "Aplicações:" distingue peças de mesmo título e código diferente: o lado ("Lado esquerdo", em 107 de 202 cartões),
        # a medida ("M12x1.5x44mm"), a versão. Sem isso, duas peças de lados opostos aparecem repetidas na lista de aprovação.
        nome = m['nome'].strip() + (f" ({', '.join(descritores)})" if descritores else '')
        pecas.append({'nome_peca': nome, 'carros_compativeis': aplicacoes, 'codigo_peca': m['codigo']})
    return pecas


PALAVRAS_VAZIAS = {'de', 'da', 'do', 'das', 'dos', 'para', 'pra', 'o', 'a', 'os', 'as', 'e', 'em', 'no', 'na', 'com', 'um', 'uma'}


def _radicais(texto: str) -> list[str]:
    """Palavras do pedido sem artigo e preposição, reduzidas ao radical (plural e final de gênero saem): "palhetas traseiras" -> palhet, traseir."""
    radicais = []
    for palavra in re.findall(r'[a-z0-9]+', _dobrar(texto)):
        if palavra in PALAVRAS_VAZIAS:
            continue
        if len(palavra) > 3 and palavra.endswith('s'):
            palavra = palavra[:-1]
        if len(palavra) > 4 and palavra[-1] in 'aoe':
            palavra = palavra[:-1]
        radicais.append(palavra)
    return radicais


def filtrar_por_nome(pecas: list[dict], nome_peca: str) -> list[dict]:
    """Fica só com a peça cujo nome tem todas as palavras do pedido. O catálogo devolve tudo o que casa com o carro (202 cartões para "palheta
    traseira"), e a lista que uma pessoa aprova não pode ser o catálogo inteiro. Pedido sem palavra útil não filtra."""
    radicais = _radicais(nome_peca)
    if not radicais:
        return pecas
    return [p for p in pecas if all(r in _dobrar(p['nome_peca']) for r in radicais)]


def em_lotes(markdown: str, limite: int = LOTE_CARACTERES) -> list[str]:
    """Parte o markdown em lotes de até `limite` caracteres, sem cortar um cartão ao meio (um cartão maior que o limite vai sozinho)."""
    blocos = [b for b in re.split(r'(?m)^(?=### \[)', markdown) if b.strip()]
    lotes, atual = [], ''
    for b in blocos:
        if atual and len(atual) + len(b) > limite:
            lotes.append(atual)
            atual = ''
        atual += b
    if atual:
        lotes.append(atual)
    return lotes


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

    def _extrair_com_modelo(self, markdown: str, prazo: float) -> tuple[list[dict], int, bool]:
        """Reserva, para página sem cartões no formato conhecido: o modelo propõe as peças, lote a lote, e o código confere.
        Devolve (peças cujo código está no lote, quantas foram descartadas, se o prazo acabou antes do último lote)."""
        sys_prompt = ler_prompt('webscrapper/tool_scrapping.md')
        pecas, descartadas = [], 0
        for lote in em_lotes(markdown):
            if time.monotonic() > prazo:
                return pecas, descartadas, True
            # Técnica: extração estruturada com 1 exemplo (one-shot) de card em markdown, no prompt.
            # Contrato: schema estrito {dados_peca: [{nome_peca, carros_compativeis[], codigo_peca}]}.
            # Impede: tratar links de menu como peça. O que o modelo devolve é proposta: só vale o código que está no lote.
            response = self.client.chat.completions.create(
                model=modelo_em_uso(),
                messages=[{'role': 'system', 'content': sys_prompt}, {'role': 'user', 'content': lote}],
                response_format=FORMATO_RETORNO, temperature=0, max_tokens=MAX_TOKENS_EXTRACAO)
            for peca in json.loads(response.choices[0].message.content).get('dados_peca', []):
                if codigo_esta_no_texto(peca.get('codigo_peca', ''), lote):
                    pecas.append(peca)
                else:
                    descartadas += 1
        return pecas, descartadas, False

    def buscar_candidatas(self, link: str, regra: str, modelo: str, ano: int, motorizacao: str, nome_peca: str, forcar_modelo: bool = False) -> dict:
        """Abre o catálogo, percorre até MAX_PAGINAS páginas em até MAX_SEGUNDOS e devolve
        {'consulta', 'pecas', 'erro', 'avisos', 'paginas_lidas', 'modo'}. Não grava nada.
        Cartões no formato `/peca/<código>/<slug>` são lidos em código; só a página sem esse formato vai ao modelo (e `forcar_modelo` obriga o modelo, para medi-lo)."""
        inicio = time.monotonic()
        prazo = inicio + MAX_SEGUNDOS
        if link.endswith('/') or link.endswith('?'):
            link = link[:-1]

        consulta = regra
        for lacuna, valor in {'<modelo>': modelo, '<ano>': ano, '<motorizacao>': motorizacao, '<nome_peca>': nome_peca}.items():
            consulta = consulta.replace(lacuna, quote_plus(str(valor)))
        link += f'?{consulta}'
        print("--- EXTRAINDO DADOS VIA WEBSCRAPPING ---")

        vistas, pecas, avisos, modos = set(), [], [], []
        paginas_lidas = 0
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=CHROMIUM, headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()
                while True:
                    print(f'Processando página {paginas_lidas + 1} de no máximo {MAX_PAGINAS} (URL atual: {page.url or link})')
                    if paginas_lidas == 0:
                        page.goto(link, wait_until="networkidle", timeout=30000)
                    else:
                        page.locator(SELETOR_PROXIMO).first.click()
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
                    markdown = self.processar_html_generico_para_markdown(html_filtrado)

                    da_pagina = [] if forcar_modelo else ler_cartoes(markdown)
                    if da_pagina:
                        modos.append('codigo')
                    else:
                        modos.append('modelo')
                        da_pagina, descartadas, sem_prazo = self._extrair_com_modelo(markdown, prazo)
                        if descartadas:
                            avisos.append(f"Descartei {descartadas} peça(s) da página {paginas_lidas + 1}: o código que o modelo leu não estava no texto da página.")
                        if sem_prazo:
                            avisos.append(f"O tempo máximo da raspagem ({MAX_SEGUNDOS} s) acabou no meio da página {paginas_lidas + 1}; a leitura dela ficou incompleta.")
                    for peca in da_pagina:
                        if peca['codigo_peca'] not in vistas:
                            vistas.add(peca['codigo_peca'])
                            pecas.append(peca)
                    paginas_lidas += 1

                    if not page.locator(SELETOR_PROXIMO).first.is_visible():
                        break
                    if paginas_lidas >= MAX_PAGINAS:
                        avisos.append(f"Li {paginas_lidas} páginas e o catálogo tem mais (teto de {MAX_PAGINAS}); podem faltar peças.")
                        break
                    if time.monotonic() > prazo:
                        avisos.append(f"O tempo máximo da raspagem ({MAX_SEGUNDOS} s) acabou depois de {paginas_lidas} página(s); podem faltar peças.")
                        break
        except Exception as err:
            erro = f'{type(err).__name__}: {err}'
        else:
            erro = None
        lidas = len(pecas)
        pecas = filtrar_por_nome(pecas, nome_peca)
        if lidas and len(pecas) < lidas:
            avisos.append(f"O catálogo trouxe {lidas} peça(s) para esse carro; mostro as {len(pecas)} com \"{nome_peca}\" no nome." if pecas else
                          f"O catálogo trouxe {lidas} peça(s) para esse carro, nenhuma com \"{nome_peca}\" no nome; não mostro nenhuma.")
        return {'consulta': link, 'pecas': pecas, 'erro': erro, 'avisos': avisos, 'paginas_lidas': paginas_lidas, 'modo': modos, 'pecas_lidas': lidas}
