import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import os
import chromadb
from chromadb.utils import embedding_functions
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.busca_textual import Bm25
from src.contrato import LeituraManual
from src.memoria import texto_procedural
from src.util import JANELA_TOKENS, ler_prompt, modelo_em_uso, tokens_estimados

# Primeira página com conteúdo real de cada manual. As anteriores são capa, sumário e índice,
# que respondem "onde está" e não "o que fazer". Medido nos PDFs do repositório:
#   Fox 2015: índice nas páginas 4-5, conteúdo a partir da 6
#   Fox 2020: índice nas páginas 6-8, conteúdo a partir da 9
# Manual novo sem entrada aqui usa o padrão abaixo: confira a página do índice antes de indexá-lo.
PRIMEIRA_PAGINA_CONTEUDO = {
    'Volkswagen_Fox_2015.pdf': 6,
    'Volkswagen_Fox_2020.pdf': 9,
}
PRIMEIRA_PAGINA_PADRAO = 6
# Trechos (chunks de 800 caracteres) levados ao modelo. 6 e não 15: com a busca textual, o 7B respondeu 14 de 18 dúvidas
# com k=6 e menos com mais trechos, porque o ruído extra atrapalha a leitura. Medição em docs/rag.md.
K_TRECHOS = 6

MAX_TOKENS_LEITURA = 600  # teto de saída da leitura: sem ele, uma geração presa num schema roda até o timeout


class LeitorManualPDF:
    """Recuperação textual (BM25) no manual + leitura fundamentada pelo modelo. A escolha do PDF é regra em código.
    O Chroma guarda os trechos já cortados (e os vetores, que o manual não usa); a busca é por termo, em memória."""

    def __init__(self, client):
        self.client = client
        self._indices: dict[str, tuple[Bm25, list]] = {}
        self.PROJECT_PATH = Path(__file__).resolve().parent.parent
        self.chroma_client = chromadb.PersistentClient(f"{self.PROJECT_PATH}/databases/chroma_db")

    def manuais(self) -> list[str]:
        return sorted(f for f in os.listdir(f'{self.PROJECT_PATH}/databases/manuais/') if f.endswith('.pdf'))

    def escolher_manual(self, modelo: str, ano: int) -> str | None:
        """Manual cujo nome contém o modelo e o ano. Sem correspondência exata, não há manual: não se aproxima."""
        alvo = modelo.lower().replace(' ', '_')
        for nome in self.manuais():
            if alvo in nome.lower() and str(ano) in nome:
                return nome
        return None

    def _chroma_collection(self, namefile):
        ef_default = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='all-MiniLM-L6-v2')
        return self.chroma_client.get_or_create_collection(
            name=namefile,
            embedding_function=ef_default
        )

    def _pdf_indexer(self, namefile):
        path_document = f"{self.PROJECT_PATH}/databases/manuais/{namefile}"
        loader = PyPDFLoader(path_document)
        paginas_pdf = loader.load()
        divisor_por_paragrafo = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", " ", ""],
            chunk_size=800,      # Tamanho limite flexível caso um parágrafo seja enorme
            chunk_overlap=0      # Sem sobreposição excessiva para preservar limites de blocos
        )
        chunks = divisor_por_paragrafo.split_documents(paginas_pdf)
        documentos = []
        metadados = []
        ids = []
        for idx, chunk in enumerate(chunks):
            documentos.append(chunk.page_content)
            num_pagina = chunk.metadata.get("page", 0) + 1
            tipo_conteudo = "tabela" if "|" in chunk.page_content else "paragrafo"
            metadados.append({
                "fonte": os.path.basename(path_document),
                "pagina": num_pagina,
                "tipo": tipo_conteudo,
                "chunk_id": idx
            })
            ids.append(f"bloco_{idx}")
        collection = self._chroma_collection(namefile)
        if documentos:
            collection.upsert(
                documents = documentos,
                metadatas = metadados,
                ids = ids
            )
    
    def _colecao_de_leitura(self, namefile: str):
        """Coleção sem função de embedding: ler os trechos não precisa do modelo (que leva ~7 s para carregar).
        Só a indexação, que gera vetores, usa `_chroma_collection`."""
        try:
            return self.chroma_client.get_collection(namefile)
        except Exception:  # NotFoundError: o manual ainda não foi indexado
            return None

    def _verify_document_indexed(self, namefile: str) -> bool:
        colecao = self._colecao_de_leitura(namefile)
        if colecao is None:
            return False
        return len(colecao.get(where={"fonte": namefile}, limit=1).get("ids", [])) > 0
        
    def _indice(self, namefile: str) -> tuple[Bm25, list]:
        """BM25 sobre os trechos de conteúdo (do início do corpo em diante). Monta uma vez por processo, em memória."""
        if namefile not in self._indices:
            if not self._verify_document_indexed(namefile): self._pdf_indexer(namefile)
            primeira = PRIMEIRA_PAGINA_CONTEUDO.get(namefile, PRIMEIRA_PAGINA_PADRAO)
            dados = self._colecao_de_leitura(namefile).get(include=['documents', 'metadatas'])
            trechos = sorted(((m['pagina'], m['chunk_id'], d) for d, m in zip(dados['documents'], dados['metadatas'])
                              if m['pagina'] >= primeira))
            lista = [(d, {'pagina': p, 'chunk_id': c}) for p, c, d in trechos]
            self._indices[namefile] = (Bm25([d for d, _ in lista]), lista)
        return self._indices[namefile]

    def ler(self, namefile: str, duvida: str, veiculo: dict | None = None) -> dict:
        """Busca por termo os trechos que tratam da dúvida e pede ao modelo uma resposta só com eles.
        O veículo sai da consulta: o manual inteiro é dele, então modelo e ano só puxam páginas genéricas.
        Devolve {'leitura': LeituraManual, 'paginas': [...]} ou {'erro': ...}."""
        indice, trechos_manual = self._indice(namefile)
        ignorar = ' '.join(str(v) for v in (veiculo or {}).values() if v)
        achados = indice.buscar(duvida, K_TRECHOS, ignorar=ignorar)
        if not achados:
            return {'erro': 'Nenhum trecho do manual contém os termos da dúvida'}
        result = {'documents': [[trechos_manual[i][0] for i, _ in achados]],
                  'metadatas': [[trechos_manual[i][1] for i, _ in achados]]}

        sistema = ler_prompt('leitor_manual_pdf/tool_call_leitura_pdf.md') + '\n\n# Regras aprendidas (escritas por uma pessoa)\n' + texto_procedural('ler_manual')
        # Orçamento de contexto. Ordem de descarte: o trecho de menor pontuação sai primeiro (a lista vem do mais
        # relevante ao menos relevante); o prompt, a dúvida e o trecho mais próximo nunca saem.
        orcamento = JANELA_TOKENS - tokens_estimados(sistema) - tokens_estimados(duvida)
        trechos, metas, gasto = [], [], 0
        for i, (doc, meta) in enumerate(zip(result['documents'][0], result['metadatas'][0])):
            trecho = f"[trecho {i + 1} | página {meta['pagina']}]\n{doc}"
            if trechos and gasto + tokens_estimados(trecho) > orcamento:
                break
            trechos.append(trecho)
            metas.append(meta)
            gasto += tokens_estimados(trecho)
        descartados = len(result['documents'][0]) - len(trechos)
        paginas = sorted({meta['pagina'] for meta in metas})

        # Técnica: geração fundamentada nos trechos recuperados (RAG), com `pensamento` curto antes da resposta (cadeia de pensamento).
        # Contrato: LeituraManual {pensamento, trecho_original, resumo, sanada}; o limite de 80 palavras vale só pelo prompt.
        # Impede: completar com conhecimento que não está nos trechos, e dar por sanada uma dúvida que só aparece em índice.
        resposta = self.client.chat.completions.create(
            model=modelo_em_uso(),
            messages=[
                {'role': 'system', 'content': sistema},
                {'role': 'user', 'content': f"Dúvida: {duvida}\n\nTrechos do manual:\n\n" + "\n\n".join(trechos)},
            ],
            temperature=0,
            max_tokens=MAX_TOKENS_LEITURA,
            response_format={'type': 'json_schema', 'json_schema': {
                'name': 'leitura_manual', 'strict': True, 'schema': LeituraManual.model_json_schema()}},
        )
        try:
            leitura = LeituraManual.model_validate_json(resposta.choices[0].message.content)
        except ValueError as err:
            return {'erro': f'Resposta do modelo fora do contrato LeituraManual: {err}'}
        return {'leitura': leitura, 'paginas': paginas, 'trechos_descartados': descartados}
