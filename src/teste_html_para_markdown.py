import re
from bs4 import BeautifulSoup, Comment
from markdownify import markdownify as md


import re
from bs4 import BeautifulSoup, Comment


def processar_html_generico_para_markdown(
    html_content: str, preservar_nav_html: bool = True
) -> str:
  soup = BeautifulSoup(html_content, "html.parser")

  # 1. Remover comentários
  for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
    comment.extract()

  # 2. Capturar as tags <nav> intactas (se solicitado) antes de limpar
  nav_tags = []
  if preservar_nav_html:
    for nav in soup.find_all("nav"):
      nav_tags.append(str(nav))
      nav.decompose()  # Remove do soup para não duplicar no processamento

  # 3. Eliminar tags que não agregam conteúdo textual
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

# --- LEITURA E ESCRITA ---

with open("html_teste.txt", "r", encoding="UTF-8") as arquivo:
  conteudo = arquivo.read()

# Alterado de 'as md' para 'as f_out' para evitar o conflito
with open("html_to_md_test.md", "w+", encoding="UTF-8") as f_out:
  md_content = processar_html_generico_para_markdown(conteudo)
  print(md_content)
  f_out.write(md_content)