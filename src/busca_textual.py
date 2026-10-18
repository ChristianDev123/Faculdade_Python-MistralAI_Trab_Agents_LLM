"""Busca textual (BM25) sobre os trechos do manual. Sem modelo, sem download, sem dependência além da biblioteca padrão.

Por que existe: as dúvidas de manual citam termos do próprio manual ("argola", "tanque", "bateria"), e nas medições
(docs/rag.md) a busca por termo achou o trecho certo bem mais cedo que a busca vetorial com embedding em inglês.

O texto extraído dos PDFs vem hifenizado ("veí- culo"); `tokenizar` junta as sílabas antes de indexar.
"""
import collections
import math
import re
import unicodedata

STOPWORDS = frozenset(
    'de da do das dos a o as os um uma uns umas para por com que em no na nos nas ao aos se ou e é são ser como qual '
    'quais quando onde meu minha seu sua pode posso devo à às pelo pela entre sobre sem mais muito isso este esta esse '
    'essa ele ela'.split())
SUFIXOS = ('coes', 'oes', 'ais', 'es', 's')  # plural simples; só corta se sobrarem 4 letras ou mais
K1, B = 1.5, 0.75  # valores clássicos do BM25; não foram ajustados ao corpus


def tokenizar(texto: str) -> list[str]:
    texto = re.sub(r'(\w)- (\w)', r'\1\2', texto)  # "veí- culo" -> "veículo"
    texto = ''.join(c for c in unicodedata.normalize('NFKD', texto.lower()) if not unicodedata.combining(c))
    saida = []
    for palavra in re.findall(r'[a-z0-9]+', texto):
        if palavra in STOPWORDS or len(palavra) < 3:
            continue
        for sufixo in SUFIXOS:
            if palavra.endswith(sufixo) and len(palavra) - len(sufixo) >= 4:
                palavra = palavra[:-len(sufixo)]
                break
        saida.append(palavra)
    return saida


class Bm25:
    def __init__(self, textos: list[str]):
        self.docs = [collections.Counter(tokenizar(t)) for t in textos]
        self.tamanhos = [sum(c.values()) for c in self.docs]
        self.media = (sum(self.tamanhos) / len(self.tamanhos)) if self.tamanhos else 1.0
        freq = collections.Counter(t for c in self.docs for t in c)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in freq.items()}

    def buscar(self, consulta: str, k: int, ignorar: str = '') -> list[tuple[int, float]]:
        """Os `k` trechos com maior pontuação, como (posição na lista original, pontuação). `ignorar` é um texto cujos
        termos saem da consulta (o veículo, que está em quase toda página e só atrapalha o ranking)."""
        fora = set(tokenizar(ignorar))
        termos = [t for t in tokenizar(consulta) if t not in fora]
        pontos = []
        for i, c in enumerate(self.docs):
            nota = 0.0
            for t in termos:
                if t in c:
                    nota += self.idf[t] * c[t] * (K1 + 1) / (c[t] + K1 * (1 - B + B * self.tamanhos[i] / self.media))
            if nota > 0:
                pontos.append((nota, i))
        pontos.sort(reverse=True)
        return [(i, nota) for nota, i in pontos[:k]]
