"""Ablação de frases dos prompts (a regra da frase: "se você apagar uma frase e não souber dizer o que ela impedia,
ela não estava fazendo nada").

Uso:
  python ablacao_prompts.py extracao [rodadas]   tira uma frase por vez do prompt do nó `extrair` e mede nos 29 casos
  python ablacao_prompts.py leitor [rodadas]     tira uma regra por vez do prompt de leitura do manual e mede nos 32 casos

Cada variante é o prompt ATUAL menos uma frase (ou um bloco). Nada em src/prompts/ é alterado: o texto é trocado em
memória durante a medição. Regra de decisão:
  - extracao: compara CASO A CASO com a linha de base (um caso "acerta" se acerta a ficha em todas as rodadas). "faz
    diferença" se, sem a frase, algum caso fora do prompt que a base acertava deixa de ser acertado; "melhora" se só
    entram casos; "sem efeito" se nada muda. A primeira versão da regra olhava só a média de casos fora do prompt
    (queda de 0,5 ou mais), o que escondia trocas (um caso sai e outro entra); foi trocada depois de ver dados parciais.
  - leitor: o modelo varia entre rodadas, então cada pergunta vale a fração de rodadas em que acertou o fato esperado;
    "entrou"/"saiu" é uma mudança de 0,5 ou mais na fração. "faz diferença" se alguma pergunta saiu ou se a falsa
    resposta passou da linha de base; "melhora" se só entraram; "sem efeito" nos demais casos.
O relatório lista, por variante, os casos que entraram e que saíram. Registre o contexto do servidor em CONTEXTO_OLLAMA.
Resultados em logs/ablacao-prompts/<alvo>.json.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

PROMPTS = RAIZ / 'src' / 'prompts'


def linha(texto: str, contendo: str) -> str:
    """A linha inteira (com a quebra) que contém `contendo`; erra se não existir exatamente uma."""
    achadas = [l for l in texto.splitlines(keepends=True) if contendo in l]
    assert len(achadas) == 1, (contendo, len(achadas))
    return achadas[0]


def bloco(texto: str, contendo: str) -> str:
    """Um exemplo do prompt: a linha que o abre, a linha do JSON e a linha em branco depois."""
    ls = texto.splitlines(keepends=True)
    i = next(k for k, l in enumerate(ls) if contendo in l)
    return ''.join(ls[i:i + 3]) if (i + 2 < len(ls) and ls[i + 2].strip() == '') else ''.join(ls[i:i + 2])


def tirar(texto: str, trecho: str) -> str:
    assert texto.count(trecho) == 1, trecho[:60]
    return re.sub(r'\n{3,}', '\n\n', texto.replace(trecho, ''))


# --------------------------------------------------------------------------- extração

def variantes_extracao() -> list[dict]:
    p = (PROMPTS / 'extracao.md').read_text(encoding='utf-8')
    proc1 = 'Pedido de compra, reserva, preço ou onde comprar é FORA_DO_ESCOPO'
    proc2 = 'Cumprimento ou mensagem sem pedido é INDEFINIDA'
    ex = {c: bloco(p, c) for c in ('Corsa 2008 1.4?"', 'períodos de manutenção do meu Fox 2015', 'pressão correta dos pneus', 'Compre agora', 'Conversa: usuário', 'oi, bom dia', 'Apague todos')}
    manual2 = ex['períodos de manutenção do meu Fox 2015'] + ex['pressão correta dos pneus']
    todos_exemplos = p[p.index('# Exemplos'):]
    return [
        {'id': 'papel', 'frase': 'Você NÃO responde ao usuário e NÃO decide o que o sistema fará: só classifica e extrai.', 'extracao': tirar(p, linha(p, 'Você NÃO responde'))},
        {'id': 'conversa_inteira', 'frase': 'Use a conversa inteira. Se a intenção já ficou clara antes e a última mensagem só traz um dado do veículo, mantenha a intenção anterior.', 'extracao': tirar(p, linha(p, 'Use a conversa inteira'))},
        {'id': 'manual_exemplos', 'frase': 'MANUAL: a lista "(períodos de revisão, óleo recomendado, pressão dos pneus, luzes do painel, como fazer algo no carro)"', 'extracao': tirar(p, ' (períodos de revisão, óleo recomendado, pressão dos pneus, luzes do painel, como fazer algo no carro)')},
        {'id': 'fora_lista', 'frase': 'FORA_DO_ESCOPO: a lista ": comprar, reservar, saber preço ou onde comprar, diagnosticar defeito"', 'extracao': tirar(p, ': comprar, reservar, saber preço ou onde comprar, diagnosticar defeito')},
        {'id': 'modelo_sem_montadora', 'frase': '`modelo`: só o modelo, sem a montadora ("Corsa", e não "Chevrolet Corsa").', 'extracao': tirar(p, linha(p, '`modelo`:'))},
        {'id': 'fabricante', 'frase': '`fabricante`: a montadora, somente se o usuário a disse.', 'extracao': tirar(p, linha(p, '`fabricante`:'))},
        {'id': 'nome_peca', 'frase': '`nome_peca`: a peça procurada, com as palavras do usuário ... null se a intenção não for PECA.', 'extracao': tirar(p, linha(p, '`nome_peca`:'))},
        {'id': 'duvida', 'frase': '`duvida`: se a intenção for MANUAL, a dúvida completa com as palavras do usuário. null nos outros casos.', 'extracao': tirar(p, linha(p, '`duvida`:'))},
        {'id': 'regra_null', 'frase': 'null para tudo o que o usuário não disse. Nunca invente nem deduza dado do veículo.', 'extracao': tirar(p, linha(p, 'null para tudo o que'))},
        {'id': 'regra_correcao', 'frase': 'Se o usuário corrigiu um dado, vale o mais recente.', 'extracao': tirar(p, linha(p, 'corrigiu um dado'))},
        {'id': 'regra_json', 'frase': 'Responda só com o JSON do schema.', 'extracao': tirar(p, linha(p, 'Responda só com o JSON'))},
        {'id': 'ex_peca', 'frase': 'exemplo: palheta traseira do Corsa (PECA completa)', 'extracao': tirar(p, ex['Corsa 2008 1.4?"'])},
        {'id': 'ex_manual', 'frase': 'os dois exemplos de MANUAL (Fox 2015 e Fox 2020)', 'extracao': tirar(p, manual2)},
        {'id': 'ex_fora', 'frase': 'exemplo: "Compre agora a pastilha de freio" (FORA_DO_ESCOPO)', 'extracao': tirar(p, ex['Compre agora'])},
        {'id': 'ex_conversa', 'frase': 'exemplo de conversa com 3 mensagens (Gol 2012)', 'extracao': tirar(p, ex['Conversa: usuário'])},
        {'id': 'ex_indefinida', 'frase': 'exemplo: "oi, bom dia" (INDEFINIDA)', 'extracao': tirar(p, ex['oi, bom dia'])},
        {'id': 'ex_esquecer', 'frase': 'exemplo: "Apague todos os meus dados" (ESQUECER)', 'extracao': tirar(p, ex['Apague todos'])},
        {'id': 'zero_shot', 'frase': 'TODOS os exemplos (a seção "# Exemplos" inteira): vira zero-shot', 'extracao': p.replace(todos_exemplos, '').rstrip() + '\n'},
        {'id': 'proc_compra', 'frase': 'regra aprendida: ' + proc1 + '...', 'procedural_extrair_sem': proc1},
        {'id': 'proc_cumprimento', 'frase': 'regra aprendida: ' + proc2 + '...', 'procedural_extrair_sem': proc2},
        {'id': 'proc_todas', 'frase': 'as duas regras aprendidas de `extrair`', 'procedural_extrair_sem': 'TODAS'},
    ]


def aplicar_extracao(nos, variante: dict | None):
    from src import memoria
    original_prompt, original_proc = nos.ler_prompt, memoria.texto_procedural
    texto_prompt = (variante or {}).get('extracao')
    sem = (variante or {}).get('procedural_extrair_sem')

    def ler_prompt(nome):
        return texto_prompt if (texto_prompt is not None and nome == 'extracao.md') else original_prompt(nome)

    def procedural(secao=None):
        regras = original_proc(secao)
        if secao == 'extrair' and sem:
            return '' if sem == 'TODAS' else '\n'.join(l for l in regras.splitlines() if sem not in l)
        return regras

    nos.ler_prompt, nos.texto_procedural = ler_prompt, procedural
    return original_prompt, original_proc


def ablacao_extracao(rodadas: int) -> dict:
    import avaliar_extracao as ae
    nos = ae.preparar_nos()
    original = (nos.ler_prompt, nos.texto_procedural)
    base_prompt = (PROMPTS / 'extracao.md').read_text(encoding='utf-8')
    resultados = {}

    def medir(variante):
        aplicar_extracao(nos, variante)
        feitas = ae.rodar(nos, rodadas)
        res = ae.resumir(feitas)
        res['acerta_em_todas_as_rodadas'] = sorted(i for i in {r['id'] for r in feitas[0]}
                                                   if all(next(x for x in rod if x['id'] == i)['ficha_ok'] for rod in feitas))
        nos.ler_prompt, nos.texto_procedural = original
        return res

    print('linha de base...', flush=True)
    base = medir(None)
    resultados['base'] = base
    print(f"  base: ficha total {base['media_ficha']}/{base['casos']} | fora do prompt {base['heldout_media_ficha']}/{base['casos_heldout']}", flush=True)
    for v in variantes_extracao():
        r = medir(v)
        economia = len(base_prompt) - len(v['extracao']) if 'extracao' in v else None
        dif = round(r['heldout_media_ficha'] - base['heldout_media_ficha'], 2)
        antes, depois = set(base['acerta_em_todas_as_rodadas']), set(r['acerta_em_todas_as_rodadas'])
        saiu, entrou = sorted(antes - depois), sorted(depois - antes)
        saiu_fora = [i for i in saiu if i not in base['vazados']]
        entrou_fora = [i for i in entrou if i not in base['vazados']]
        veredito = 'faz diferença' if saiu_fora else ('melhora' if entrou_fora else 'sem efeito')
        resultados[v['id']] = {'frase': v['frase'], 'caracteres_a_menos': economia, 'resumo': r, 'diferenca_fora_do_prompt': dif,
                               'casos_que_saíram': saiu, 'casos_que_entraram': entrou, 'veredito': veredito}
        print(f"  {v['id']:<22} fora do prompt {r['heldout_media_ficha']}/{r['casos_heldout']} ({dif:+}) | total {r['media_ficha']}/{r['casos']} | "
              f"saíram {saiu} | entraram {entrou} | {veredito}", flush=True)
    return resultados


# --------------------------------------------------------------------------- leitor

def variantes_leitor() -> list[dict]:
    p = (PROMPTS / 'leitor_manual_pdf' / 'tool_call_leitura_pdf.md').read_text(encoding='utf-8')
    proc = 'Índice, sumário e lista de termos de manual nunca respondem'
    return [
        {'id': 'nunca_conhecimento_proprio', 'frase': 'Nunca complete com conhecimento próprio.', 'leitor': tirar(p, ' Nunca complete com conhecimento próprio.')},
        {'id': 'regra1_formato_da_mensagem', 'frase': 'A mensagem traz a dúvida e trechos numerados, cada um com a página de origem.', 'leitor': tirar(p, linha(p, '1. A mensagem traz'))},
        {'id': 'regra2_sanada_em_qualquer_formato', 'frase': 'A dúvida está sanada quando algum trecho traz a informação pedida, em qualquer formato...', 'leitor': tirar(p, linha(p, '2. A dúvida está sanada'))},
        {'id': 'regra3_sanada_so_falso_se_nenhum', 'frase': '`sanada` só é falso se NENHUM trecho trata do assunto. Índice, sumário e lista de termos não contam.', 'leitor': tirar(p, linha(p, '3. `sanada` só é falso'))},
        {'id': 'regra4_trecho_original', 'frase': '`trecho_original` é a cópia literal do trecho que sustenta a resposta...', 'leitor': tirar(p, linha(p, '4. `trecho_original`'))},
        {'id': 'regra5_resumo', 'frase': '`resumo` responde à dúvida em português, com no máximo 80 palavras e só com o que os trechos dizem...', 'leitor': tirar(p, linha(p, '5. `resumo`'))},
        {'id': 'regra6_pensamento', 'frase': '`pensamento` tem no máximo 2 frases.', 'leitor': tirar(p, linha(p, '6. `pensamento`'))},
        {'id': 'proc_indice', 'frase': 'regra aprendida: ' + proc + '...', 'procedural_leitor_vazio': True},
    ]


def ablacao_leitor(rodadas: int) -> dict:
    from src import leitor_manual_pdf as lm
    from src.config import client
    dados = json.loads((RAIZ / 'dados' / 'perguntas_rag.json').read_text(encoding='utf-8'))['avaliacao_manual']
    leitor = lm.LeitorManualPDF(client)
    original = (lm.ler_prompt, lm.texto_procedural)
    base_texto = (PROMPTS / 'leitor_manual_pdf' / 'tool_call_leitura_pdf.md').read_text(encoding='utf-8')

    def uma_rodada():
        sanadas = fato = recusas = falsas = 0
        por_pergunta = {}
        suf = dados['sufixo_da_pergunta']
        for caso in dados['com_resposta']:
            for q in caso['perguntas']:
                r = leitor.ler(dados['manual'], q.rstrip('?') + suf + '?', dados['veiculo'])
                if 'erro' in r:
                    continue
                x = r['leitura']
                sanadas += x.sanada
                acertou = bool(x.sanada and re.search(caso['fato'], (x.resumo + ' ' + x.trecho_original).lower()))
                fato += acertou
                por_pergunta[q] = acertou
        for grupo in dados['sem_resposta']:
            for q in grupo['perguntas']:
                r = leitor.ler(dados['manual'], q.rstrip('?') + suf + '?', dados['veiculo'])
                if 'erro' in r or not r['leitura'].sanada:
                    recusas += 1
                else:
                    falsas += 1
                    por_pergunta[q] = 'FALSA'
        return {'respondeu': sanadas, 'fato': fato, 'recusou': recusas, 'falsas': falsas, 'por_pergunta': por_pergunta}

    def medir(variante):
        texto = (variante or {}).get('leitor')
        lm.ler_prompt = (lambda nome: texto if (texto is not None and nome.endswith('tool_call_leitura_pdf.md')) else original[0](nome))
        lm.texto_procedural = (lambda secao=None: '' if (variante or {}).get('procedural_leitor_vazio') and secao == 'ler_manual' else original[1](secao))
        rs = [uma_rodada() for _ in range(rodadas)]
        lm.ler_prompt, lm.texto_procedural = original
        acerto = {q: round(sum(r['por_pergunta'].get(q) is True for r in rs) / len(rs), 2)
                  for caso in dados['com_resposta'] for q in caso['perguntas']}
        falsa = {q: round(sum(r['por_pergunta'].get(q) == 'FALSA' for r in rs) / len(rs), 2)
                 for grupo in dados['sem_resposta'] for q in grupo['perguntas']}
        return {'acerto_por_pergunta': acerto, 'falsa_por_pergunta': falsa,
                'rodadas': [{k: v for k, v in r.items() if k != 'por_pergunta'} for r in rs], 'media_respondeu': round(sum(r['respondeu'] for r in rs) / len(rs), 2), 'media_fato': round(sum(r['fato'] for r in rs) / len(rs), 2),
                'media_recusou': round(sum(r['recusou'] for r in rs) / len(rs), 2), 'max_falsas': max(r['falsas'] for r in rs)}

    resultados = {}
    print('linha de base...', flush=True)
    base = medir(None)
    resultados['base'] = base
    print(f"  base: respondeu {base['media_respondeu']}/18 | fato {base['media_fato']}/18 | recusou {base['media_recusou']}/14 | falsas (máx) {base['max_falsas']}", flush=True)
    for v in variantes_leitor():
        r = medir(v)
        dif = round(r['media_fato'] - base['media_fato'], 2)
        saiu = [q for q, f in r['acerto_por_pergunta'].items() if f - base['acerto_por_pergunta'][q] <= -0.5]
        entrou = [q for q, f in r['acerto_por_pergunta'].items() if f - base['acerto_por_pergunta'][q] >= 0.5]
        falsas_novas = [q for q, f in r['falsa_por_pergunta'].items() if f - base['falsa_por_pergunta'][q] >= 0.5]
        veredito = 'faz diferença' if (saiu or r['max_falsas'] > base['max_falsas']) else ('melhora' if entrou else 'sem efeito')
        resultados[v['id']] = {'frase': v['frase'], 'caracteres_a_menos': (len(base_texto) - len(v['leitor'])) if 'leitor' in v else None,
                               'resumo': r, 'diferenca_fato': dif, 'perguntas_que_saíram': saiu, 'perguntas_que_entraram': entrou,
                               'falsas_novas': falsas_novas, 'veredito': veredito}
        print(f"  {v['id']:<36} respondeu {r['media_respondeu']}/18 | fato {r['media_fato']}/18 ({dif:+}) | recusou {r['media_recusou']}/14 | falsas (máx) {r['max_falsas']} | "
              f"saíram {len(saiu)} | entraram {len(entrou)} | {veredito}", flush=True)
    return resultados


if __name__ == '__main__':
    alvo = sys.argv[1] if len(sys.argv) > 1 else ''
    rodadas = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    if alvo not in ('extracao', 'leitor'):
        print(__doc__)
        sys.exit(2)
    from src.trajetoria import estado_do_codigo
    from src.util import modelo_em_uso
    inicio = time.time()
    res = ablacao_extracao(rodadas) if alvo == 'extracao' else ablacao_leitor(rodadas)
    destino = RAIZ / 'logs' / 'ablacao-prompts'
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f'{alvo}.json').write_text(json.dumps({**estado_do_codigo(), 'data': time.strftime('%Y-%m-%d'), 'modelo': modelo_em_uso(), 'rodadas': rodadas, 'contexto_ollama': os.environ.get('CONTEXTO_OLLAMA', 'não informado'),
                                                       'duracao_s': round(time.time() - inicio), 'resultados': res}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nResultado em {destino / (alvo + ".json")} ({time.time() - inicio:.0f} s)')
