import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import os
import chromadb
from chromadb.utils import embedding_functions
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.contrato import LeituraManual
from src.util import ler_prompt, modelo_em_uso

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
K_TRECHOS = 15  # trechos (chunks de 800 caracteres) levados ao modelo; justificativa do valor em docs/rag.md

MAX_TOKENS_LEITURA = 600  # teto de saída da leitura: sem ele, uma geração presa num schema roda até o timeout


class LeitorManualPDF:
    """Recuperação no manual (Chroma) + leitura fundamentada pelo modelo. A escolha do PDF é regra em código."""

    def __init__(self, client):
        self.client = client
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
    
    def _verify_document_indexed(self, namefile: str) -> bool:
        colecao = self._chroma_collection(namefile)
        resultados = colecao.get(
            where={"fonte": namefile},
            limit=1
        )
        total_encontrado = len(resultados.get("ids", []))
        return total_encontrado > 0
        
    def ler(self, namefile: str, duvida: str) -> dict:
        """Busca os trechos mais próximos da dúvida e pede ao modelo uma resposta só com eles.
        Devolve {'leitura': LeituraManual, 'paginas': [...]} ou {'erro': ...}."""
        if not self._verify_document_indexed(namefile): self._pdf_indexer(namefile)
        collection = self._chroma_collection(namefile)
        result = collection.query(
            query_texts=[duvida],
            n_results=K_TRECHOS,
            where={"pagina": {"$gte": PRIMEIRA_PAGINA_CONTEUDO.get(namefile, PRIMEIRA_PAGINA_PADRAO)}}
        )
        if not result['documents'][0]:
            return {'erro': 'Nenhum trecho encontrado no manual'}

        trechos = [f"[trecho {i + 1} | página {meta['pagina']}]\n{doc}"
                   for i, (doc, meta) in enumerate(zip(result['documents'][0], result['metadatas'][0]))]
        paginas = sorted({meta['pagina'] for meta in result['metadatas'][0]})

        # Técnica: geração fundamentada nos trechos recuperados (RAG), com `pensamento` antes da resposta (cadeia de pensamento).
        # Contrato: LeituraManual {pensamento, trecho_original, resumo, sanada}; o limite de 100 palavras vale só pelo prompt.
        # Impede: usar índice ou glossário como resposta, e completar com conhecimento que não está nos trechos.
        resposta = self.client.chat.completions.create(
            model=modelo_em_uso(),
            messages=[
                {'role': 'system', 'content': ler_prompt('leitor_manual_pdf/tool_call_leitura_pdf.md')},
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
        return {'leitura': leitura, 'paginas': paginas}
