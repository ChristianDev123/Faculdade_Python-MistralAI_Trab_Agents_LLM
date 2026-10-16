"""Memória de longo prazo e esquecimento (ver docs/memoria.md).

Três memórias, cada uma na estrutura adequada:
  semântica  chave-valor     tabela `memoria_semantica` (SQLite): o veículo de cada usuário
  episódica  índice          tabela `log_interacoes` (dado) + coleção `memoria_episodica` no Chroma (índice derivado:
                             só vetor, id da linha e modelo/ano; sem texto e sem user_id)
  procedural texto           src/prompts/procedural.md, injetado nos prompts; só uma pessoa escreve

Quem escreve é sempre código, por regra, e só depois de um turno `respondido`. Nenhum agente decide o que guardar.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from src.util import JANELA_TOKENS, tokens_estimados  # noqa: F401  (JANELA_TOKENS é reexportado para os nós)

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_PATH = ROOT / 'databases' / 'checkpoints.sqlite'
LOGS_PATH = ROOT / 'logs'
PROMPTS_PATH = ROOT / 'src' / 'prompts'

ULTIMAS_MENSAGENS = 6
COLECAO_EPISODICA = 'memoria_episodica'
CAMPOS_VEICULO = ('modelo', 'ano', 'motorizacao', 'fabricante')
USER_ID_VALIDO = re.compile(r'^[A-Za-z0-9_.-]{1,100}$')

# Distância de cosseno máxima para uma pergunta anterior valer como "a mesma". Medido com o modelo de embedding real
# (all-MiniLM-L6-v2, centrado em inglês) sobre perguntas em português: variações de grafia da mesma pergunta ficaram
# entre 0,000 e 0,088; outras dúvidas do mesmo carro entre 0,238 e 0,383; paráfrases entre 0,194 e 0,443, misturadas com
# as outras dúvidas. O corte fica acima de toda grafia e abaixo da dúvida diferente mais próxima (0,12): prefere-se reler
# o manual a servir a resposta de outra pergunta. Medição completa em docs/memoria.md.
LIMIAR_EPISODIO = float(os.environ.get('LIMIAR_EPISODIO') or 0.12)


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def janela_historico(mensagens: list[dict], orcamento_tokens: int, ultimas: int = ULTIMAS_MENSAGENS) -> list[dict]:
    """Ordem de descarte: as mensagens mais antigas saem primeiro (o atendente e o usuário, juntos); a última sempre fica.
    O que saiu já está no estado explícito (veículo, intenção), então não se perde dado, só a redação antiga."""
    mantidas, gasto = [], 0
    for m in reversed(mensagens[-ultimas:]):
        custo = tokens_estimados(m['content'])
        if mantidas and gasto + custo > orcamento_tokens:
            break
        mantidas.append(m)
        gasto += custo
    return list(reversed(mantidas))


def texto_procedural(secao: str | None = None) -> str:
    """O texto de procedural.md. Com `secao` ("## extrair", "## ler_manual"), só as regras daquela seção."""
    texto = (PROMPTS_PATH / 'procedural.md').read_text(encoding='utf-8')
    if secao is None:
        return texto
    partes = re.split(r'^## ', texto, flags=re.MULTILINE)[1:]
    for parte in partes:
        nome, _, regras = parte.partition('\n')
        if nome.strip() == secao:
            return regras.strip()
    return ''


def _canonico(valor: dict) -> str:
    return json.dumps({k: str(v).strip().casefold() for k, v in valor.items()}, sort_keys=True, ensure_ascii=False)


class Memoria:
    def __init__(self, registrador, chroma_client):
        self.reg = registrador
        self.chroma = chroma_client
        self._ef = None

    def _colecao(self):
        if self._ef is None:
            from chromadb.utils import embedding_functions
            self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='all-MiniLM-L6-v2')
        return self.chroma.get_or_create_collection(
            name=COLECAO_EPISODICA, embedding_function=self._ef, metadata={'hnsw:space': 'cosine'})

    # ------------------------- semântica: o veículo do usuário -------------------------

    def lembrar_veiculo(self, user_id: str) -> dict | None:
        """Contradição se resolve aqui, na leitura: de todas as declarações do usuário vale a de maior `created_at`."""
        linhas = self.reg.buscar_exato('memoria_semantica', {'user_id': user_id, 'entidade': 'veiculo'})
        if not linhas:
            return None
        ultima = max(linhas, key=lambda l: l['created_at'])
        return {'valor': json.loads(ultima['valor']), 'created_at': ultima['created_at'], 'declaracoes': len(linhas)}

    def memorizar_veiculo(self, user_id: str, veiculo: dict) -> dict:
        valor = {k: veiculo[k] for k in CAMPOS_VEICULO if veiculo.get(k) not in (None, '')}
        if not valor.get('modelo') or not valor.get('ano'):
            return {'pulou': 'veículo incompleto (faltam modelo e ano)'}
        atual = self.lembrar_veiculo(user_id)
        if atual and _canonico(atual['valor']) == _canonico(valor):
            return {'ja_existia': True}
        resultado = self.reg.inserir('memoria_semantica', {
            'user_id': user_id, 'entidade': 'veiculo',
            'valor': json.dumps(valor, ensure_ascii=False, sort_keys=True), 'created_at': agora()})
        if atual and 'erro' not in resultado:
            resultado['contradicao'] = {'antes': atual['valor'], 'agora': valor}
        return resultado

    # ------------------------- episódica: dúvidas de manual já respondidas -------------------------

    def registrar_episodio(self, user_id: str, veiculo: dict, duvida: str, resolucao: str) -> dict:
        palavras = ', '.join(sorted({w.lower().strip('?,.') for w in duvida.split() if len(w) > 4}))
        resultado = self.reg.inserir('log_interacoes', {
            'modelo': veiculo['modelo'], 'ano_fabricacao': veiculo['ano'], 'motorizacao': veiculo.get('motorizacao') or '',
            'duvida_usuario': duvida, 'kws_duvida_usuario': palavras, 'resolucao': resolucao,
            'user_id': user_id, 'created_at': agora()})
        if 'erro' in resultado:
            return resultado
        # Índice derivado, sem dado pessoal: só o vetor, o id da linha e modelo/ano. Nem o texto da pergunta nem o user_id
        # vão para o Chroma (o log interno dele guarda tudo o que entra e não dá para limpá-lo por fora). Quem é dono de
        # qual vetor está na tabela. Repetir a chamada atualiza o mesmo vetor e repara um vetor que faltasse.
        colecao = self._colecao()
        vetor = [float(x) for x in self._ef([duvida])[0]]
        colecao.upsert(ids=[str(resultado['id'])], embeddings=[vetor],
                       metadatas=[{'modelo': veiculo['modelo'].lower(), 'ano': int(veiculo['ano'])}])
        return resultado

    def buscar_episodio(self, duvida: str, veiculo: dict, limiar: float = LIMIAR_EPISODIO) -> dict:
        """Pergunta parecida, do mesmo modelo e ano, com distância até o limiar. Entre as que passam, a mais recente vence."""
        colecao = self._colecao()
        if colecao.count() == 0:
            return {'hit': None, 'melhor_distancia': None}
        achados = colecao.query(
            query_texts=[duvida], n_results=min(5, colecao.count()),
            where={'$and': [{'modelo': veiculo['modelo'].lower()}, {'ano': int(veiculo['ano'])}]})
        ids, distancias = achados['ids'][0], achados['distances'][0]
        if not ids:
            return {'hit': None, 'melhor_distancia': None}
        proximos = [(int(i), d) for i, d in zip(ids, distancias) if d <= limiar]
        if not proximos:
            return {'hit': None, 'melhor_distancia': round(min(distancias), 3)}
        linhas = [(self.reg.buscar_exato('log_interacoes', {'id': i}), d) for i, d in proximos]
        linhas = [(l[0], d) for l, d in linhas if l]
        if not linhas:
            return {'hit': None, 'melhor_distancia': round(min(distancias), 3)}
        linha, distancia = max(linhas, key=lambda x: x[0]['created_at'])
        return {'hit': {**linha, 'similaridade': round(1 - distancia, 3)}, 'melhor_distancia': round(distancia, 3)}

    # ------------------------- esquecimento -------------------------

    @staticmethod
    def _validar_usuario(user_id: str) -> None:
        if not USER_ID_VALIDO.match(user_id or ''):
            raise ValueError(f'user_id inválido para remoção: {user_id!r}')

    def threads_do_usuario(self, user_id: str) -> list[str]:
        if not CHECKPOINT_PATH.exists():
            return []
        prefixo = f'{user_id}:'
        with sqlite3.connect(CHECKPOINT_PATH) as conn:
            try:
                linhas = conn.execute('SELECT DISTINCT thread_id FROM checkpoints WHERE substr(thread_id, 1, ?) = ?',
                                      (len(prefixo), prefixo)).fetchall()
            except sqlite3.OperationalError:  # arquivo ainda sem as tabelas do checkpoint
                return []
        return [l[0] for l in linhas]

    def procedural_cita(self, user_id: str) -> list[str]:
        return [l for l in texto_procedural().splitlines() if user_id in l]

    def contar_usuario(self, user_id: str) -> dict:
        """O que seria apagado. Só leitura: serve ao texto da confirmação."""
        self._validar_usuario(user_id)
        pasta = LOGS_PATH / user_id
        colecao = self._colecao()
        ids = [str(l['id']) for l in self.reg.buscar_exato('log_interacoes', {'user_id': user_id})]
        return {
            'fatos_veiculo': len(self.reg.buscar_exato('memoria_semantica', {'user_id': user_id})),
            'duvidas_registradas': len(ids),
            'vetores_episodicos': len(colecao.get(ids=ids)['ids']) if ids and colecao.count() else 0,
            'conversas_salvas': len(self.threads_do_usuario(user_id)),
            'arquivos_de_log': sum(1 for f in pasta.rglob('*') if f.is_file()) if pasta.exists() else 0,
            'regras_que_citam': len(self.procedural_cita(user_id)),
        }

    def esquecer_usuario(self, user_id: str, manter_thread: str | None = None) -> dict:
        """Apaga tudo do titular nas estruturas em que foi gravado. `manter_thread` é a conversa que está executando
        a remoção: ela é apagada depois, fora do grafo, senão o framework a recriaria no passo seguinte."""
        self._validar_usuario(user_id)
        # Os vetores do usuário são os das linhas dele: lê os ids antes de apagar as linhas.
        colecao = self._colecao()
        ids = [str(l['id']) for l in self.reg.buscar_exato('log_interacoes', {'user_id': user_id})]
        vetores = colecao.get(ids=ids)['ids'] if ids and colecao.count() else []
        if vetores:
            colecao.delete(ids=vetores)  # por id, sem reconstruir o índice
        contagens = {
            'fatos_veiculo': self.reg.apagar_exato('memoria_semantica', {'user_id': user_id}),
            'duvidas_registradas': self.reg.apagar_exato('log_interacoes', {'user_id': user_id}),
            'vetores_episodicos': len(vetores),
        }
        self.reg.compactar()

        from langgraph.checkpoint.sqlite import SqliteSaver
        apagadas = 0
        if CHECKPOINT_PATH.exists():
            conexao = sqlite3.connect(CHECKPOINT_PATH)
            saver = SqliteSaver(conexao)
            for thread in self.threads_do_usuario(user_id):
                if thread != manter_thread:
                    saver.delete_thread(thread)
                    apagadas += 1
            conexao.commit()
            conexao.execute('VACUUM')
            conexao.close()
        contagens['conversas_salvas'] = apagadas

        pasta = LOGS_PATH / user_id
        arquivos = sum(1 for f in pasta.rglob('*') if f.is_file()) if pasta.exists() else 0
        shutil.rmtree(pasta, ignore_errors=True)
        contagens['arquivos_de_log'] = arquivos
        contagens['regras_que_citam'] = len(self.procedural_cita(user_id))  # não se apaga sozinho: exige edição humana

        self._auditar(user_id, contagens, manteve_thread=manter_thread is not None)
        return contagens

    def apagar_thread(self, thread_id: str) -> None:
        """Apaga o checkpoint de uma conversa. A CLI chama depois que o grafo terminou de executar."""
        if not CHECKPOINT_PATH.exists():
            return
        from langgraph.checkpoint.sqlite import SqliteSaver
        conexao = sqlite3.connect(CHECKPOINT_PATH)
        SqliteSaver(conexao).delete_thread(thread_id)
        conexao.commit()
        conexao.execute('VACUUM')
        conexao.close()

    def esquecer_episodio(self, linha_id: int) -> dict:
        """Recuperação de incidente: remove um episódio pelo id (a linha e o vetor), sem mexer no resto do índice."""
        linhas = self.reg.apagar_exato('log_interacoes', {'id': linha_id})
        colecao = self._colecao()
        existia = bool(colecao.get(ids=[str(linha_id)])['ids']) if colecao.count() else False
        if existia:
            colecao.delete(ids=[str(linha_id)])
        self.reg.compactar()
        self._auditar(f'episodio:{linha_id}', {'linhas': linhas, 'vetores': int(existia)}, manteve_thread=False)
        return {'linhas': linhas, 'vetores': int(existia)}

    @staticmethod
    def _auditar(quem: str, contagens: dict, manteve_thread: bool) -> None:
        """Registro da remoção sem dado pessoal: só o hash do identificador."""
        LOGS_PATH.mkdir(exist_ok=True)
        linha = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'alvo_hash': hashlib.sha256(quem.encode()).hexdigest()[:12],
                 'contagens': contagens, 'manteve_thread_atual': manteve_thread}
        with open(LOGS_PATH / '_remocoes.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(linha, ensure_ascii=False) + '\n')
