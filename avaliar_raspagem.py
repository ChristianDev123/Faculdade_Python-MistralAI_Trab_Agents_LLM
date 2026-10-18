"""Avalia a extração de peças da página do catálogo (etapa `raspar`): o que o modelo devolveu está mesmo na página?

Uso:
  python avaliar_raspagem.py [rodadas]     raspa o catálogo da Chevrolet ao vivo (Onix 2018 1.0, "palheta traseira")

Para cada peça extraída confere, no texto exato que o modelo recebeu (o markdown montado da página):
  - o nome da peça aparece?            (se não, o modelo inventou ou reescreveu o nome)
  - o código aparece?                  (se não, o modelo inventou o código)
  - o código TEM FORMA de código?      (letras e números, 3 a 20 caracteres; pega o aviso "Ooops, o estoque acabou")
  - os carros compatíveis aparecem?    (todos, parte ou nenhum)
  - quando o código NÃO está na página: ele é um PREÇO da página reformatado? ("2.097,65" virando "2097.65")
Também conta quantos cartões de peça a página tem e quanto da página o modelo recebe de fato (o servidor local corta a
entrada que passa do contexto; ver docs/prompts.md).
Não grava nada na base. Precisa do Chromium do sistema, de internet e do modelo no ar. A página muda: os números são de
uma data (veja o carimbo no resultado), não de uma verdade fixa.
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

FORMA_DE_CODIGO = re.compile(r'[A-Za-z0-9][A-Za-z0-9\-\. ]{1,18}[A-Za-z0-9]')
CONSULTA = {'modelo': 'Onix', 'ano': 2018, 'motorizacao': '1.0', 'nome_peca': 'palheta traseira', 'fabricante': 'chevrolet'}


def _fold(t: str) -> str:
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', t.lower()) if not unicodedata.combining(c)))


def eh_preco_reformatado(codigo: str, pagina: str) -> bool:
    """"2097.65" é o preço "2.097,65" da página escrito como número?"""
    m = re.fullmatch(r'(\d+)\.(\d{2})', codigo.strip())
    if not m:
        return False
    inteiro, centavos = m.groups()
    return f"{int(inteiro):,}".replace(',', '.') + ',' + centavos in pagina


def avaliar_uma_vez() -> dict:
    from src.config import client
    from src.registrador import Registrador
    from src.webscrapper import WebScrapper

    reg, scraper = Registrador(), WebScrapper(client)
    catalogo = reg.resgatar('webcatalogos', {'fabricante': CONSULTA['fabricante']})[0]
    paginas = []
    original = scraper.processar_html_generico_para_markdown

    def capturar(html, *a, **k):
        texto = original(html, *a, **k)
        paginas.append(texto)
        return texto

    scraper.processar_html_generico_para_markdown = capturar
    inicio = time.time()
    achado = scraper.buscar_candidatas(catalogo['link'], catalogo['regra'], CONSULTA['modelo'], CONSULTA['ano'],
                                       CONSULTA['motorizacao'], CONSULTA['nome_peca'])
    pagina = _fold(' '.join(paginas))
    pecas = achado['pecas']
    linhas, contagem = [], {'nome_na_pagina': 0, 'codigo_na_pagina': 0, 'codigo_com_forma': 0, 'codigo_e_preco_da_pagina': 0, 'compat_todos': 0, 'compat_parte': 0, 'compat_nenhum': 0}
    for p in pecas:
        nome_ok = _fold(p['nome_peca']) in pagina
        cod_ok = _fold(p['codigo_peca']) in pagina
        forma_ok = bool(FORMA_DE_CODIGO.fullmatch(p['codigo_peca'].strip()))
        preco_ok = (not cod_ok) and eh_preco_reformatado(p['codigo_peca'], pagina)
        contagem['codigo_e_preco_da_pagina'] += preco_ok
        compat = p.get('carros_compativeis') or []
        achados = sum(1 for c in compat if _fold(c) in pagina)
        contagem['nome_na_pagina'] += nome_ok
        contagem['codigo_na_pagina'] += cod_ok
        contagem['codigo_com_forma'] += forma_ok
        if compat:
            contagem['compat_todos' if achados == len(compat) else ('compat_parte' if achados else 'compat_nenhum')] += 1
        linhas.append({'nome': p['nome_peca'], 'codigo': p['codigo_peca'], 'nome_na_pagina': nome_ok, 'codigo_na_pagina': cod_ok, 'codigo_com_forma': forma_ok, 'codigo_e_preco_da_pagina': preco_ok,
                       'compativeis': len(compat), 'compativeis_na_pagina': achados})
    codigos = [p['codigo_peca'] for p in pecas]
    repetidos = sorted({c for c in codigos if codigos.count(c) > 1})
    bruto = ' '.join(paginas)
    return {'consulta': achado['consulta'], 'erro': achado['erro'], 'paginas_lidas': len(paginas), 'segundos': round(time.time() - inicio),
            'caracteres_da_pagina': len(bruto), 'cartoes_na_pagina': len(re.findall(r'### \[', bruto)),
            'pecas': len(pecas), **contagem, 'codigos_repetidos': repetidos, 'detalhe': linhas}


def main(rodadas: int) -> int:
    from src.trajetoria import estado_do_codigo
    from src.util import modelo_em_uso
    resultados = []
    for i in range(1, rodadas + 1):
        r = avaliar_uma_vez()
        resultados.append(r)
        n = r['pecas'] or 1
        print(f"rodada {i}: página de {r['caracteres_da_pagina']} caracteres com {r['cartoes_na_pagina']} cartões; o modelo devolveu {r['pecas']} peças, {r['segundos']} s | nome na página {r['nome_na_pagina']}/{r['pecas']} | "
              f"código na página {r['codigo_na_pagina']}/{r['pecas']} | dos que faltam, são preço da página {r['codigo_e_preco_da_pagina']} | código com forma de código {r['codigo_com_forma']}/{r['pecas']} | "
              f"compatíveis: todos {r['compat_todos']}, parte {r['compat_parte']}, nenhum {r['compat_nenhum']} | códigos repetidos: {r['codigos_repetidos']}", flush=True)
        for d in r['detalhe']:
            if not (d['nome_na_pagina'] and d['codigo_na_pagina'] and d['codigo_com_forma']) and not d['codigo_e_preco_da_pagina']:
                print(f"    atenção: {d['nome']!r} código {d['codigo']!r} | nome na página: {d['nome_na_pagina']} | código na página: {d['codigo_na_pagina']} | forma de código: {d['codigo_com_forma']}")
    destino = RAIZ / 'logs' / 'avaliacao-raspagem'
    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'resultado.json').write_text(json.dumps({**estado_do_codigo(), 'data': time.strftime('%Y-%m-%d'), 'modelo': modelo_em_uso(),
                                                         'consulta': CONSULTA, 'rodadas': resultados}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Resultado em {destino / "resultado.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2))
