import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.tool_call import ToolCall
from interfaces.json_format import createJsonFormat
import os
from openai import OpenAI
import json
import inspect
import chromadb
from chromadb.utils import embedding_functions
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

class LeitorManualPDF(Agent):
    def __init__(self, client:OpenAI):
        f_entrada = createJsonFormat('entrada_leitura_pdf',[
            {'name':'duvida_usuario', 'type':'string'},
            {'name':'modelo', 'type':'string'},
            {'name':'ano', 'type':'integer'},
            {'name':'motorizacao', 'type':'string'},
        ])
        f_saida = createJsonFormat('retorno_leitura_pdf', [
            {'name': 'duvida_usuario', 'type': 'string'},
            {'name': 'kws_duvida_usuario', 'type': 'array', 'items': {'type': 'string'}},
            {'name': 'resolucao', 'type': 'string'},
        ])
        super().__init__('leitor_manual_pdf', client, f_entrada=f_entrada, f_saida=f_saida)
        self.tool_calls = []
        self.tool_calls_func_link = {}
        self._create_tool_calls()
        self.send_message(Message('system', self.read_system_prompts('leitor_manual_pdf/leitor_manual_pdf_prompt.md')))
        self.PROJECT_PATH = Path(__file__).resolve().parent.parent
        self.chroma_client = chromadb.PersistentClient(f"{self.PROJECT_PATH}/databases/chroma_db")

    def _create_tool_calls(self):
        get_pdf_filename = ToolCall('get_pdf_filename', """
            Utilize para receber uma lista de nomes de arquivos
            de manuais de automóveis disponíveis para leitura.
        """)
        self.tool_calls.append(get_pdf_filename.to_dict())
        self.tool_calls_func_link['get_pdf_filename'] = self._get_pdf_filenames

        exec_read = ToolCall('exec_read',"""
            Resposabilidade: ler arquivos de manuais arquivados em formato pdf.
            Utilize assim que tiver o nome do arquivo à ser lido.
        """)
        exec_read.insert_prop('namefile', {'type':'string','description':'Nome do arquivo pdf à ser lido'})
        exec_read.insert_prop('duvida_usuario', {'type':'string', 'description':'Duvida do Usuário'})
        self.tool_calls.append(exec_read.to_dict())
        self.tool_calls_func_link['exec_read'] = self._exec_read

    def _get_pdf_filenames(self):
        path_project = f'{self.PROJECT_PATH}/databases/manuais/'
        return list(filter(lambda x: str(x).endswith('.pdf'), os.listdir(path_project)))

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
        
    def _exec_read(self, namefile, duvida_usuario):
        if(not self._verify_document_indexed(namefile)): self._pdf_indexer(namefile)
        collection = self._chroma_collection(namefile)
        result = collection.query(
            query_texts=[duvida_usuario],
            n_results = 15, # maximo 5 páginas recuperadas
            where={"pagina": {"$gt": 5}}
        )
        if not result['documents'][0]:
            return {'erro':'Nenhum resultado encontrado'}

        jf_read_pages_return = createJsonFormat('read_pdf_pages_return', [
            {'name':'pensamento', 'type':'string'},
            {'name':'trecho_original', 'type':'string'},
            {'name':'resumo', 'type':'string'},
        ])

        pdf_pages = [Message('user', page).to_dict() for page in result['documents'][0]]
        sys_prompt = Message('system',self.read_system_prompts('leitor_manual_pdf/tool_call_leitura_pdf.md')).to_dict()
        messages = [sys_prompt] + pdf_pages

        response_completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            response_format=jf_read_pages_return
        )
        resultado = json.loads(response_completion.choices[0].message.content)
        print(messages)
        return resultado                        

    def run(self):
        sys_message = self.get_answer(
            tools=self.tool_calls,
            temperature=0
        )
        while getattr(sys_message, 'tool_calls', None):
            self.send_message(sys_message)
            for tool in sys_message.tool_calls:
                func = self.tool_calls_func_link[tool.function.name]
                argumentos = json.loads(tool.function.arguments)
                sig = inspect.signature(func)
                
                if len(sig.parameters) == 0: result = func()
                else: result = func(**argumentos)

                print(f"""
                    --- Acionando TOOL CALL -- 
                    nome: {tool.function.name}
                    argumentos: {argumentos}
                """)

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
            Com base no histórico da conversa, devolva as seguintes informações no formato JSON especificado:
            - Dúvida do usuário (duvida_usuario)
            - Palavras-chave da dúvida do usuário (kws_duvida_usuario)
            - Resumo elaborado a partir da leitura do manual (resolucao)
        """))

        return self.get_answer(
            response_format=self.f_saida,
            temperature=0
        ).content