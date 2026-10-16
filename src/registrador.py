import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.json_format import createJsonFormat
from openai import OpenAI
import hashlib
import sqlite3
import json

# Coluna interna: hash do conteúdo da linha. Não aparece para o modelo, só impede gravar a mesma linha duas vezes.
CHAVE = 'chave_idempotencia'


class Registrador(Agent):
    
    def __init__(self, client:OpenAI):
        super().__init__('registrador',client, f_entrada="", f_saida="")
        self.send_message(Message('system',self.read_system_prompts('registrador_system_prompt.md')))
        self.PATH_DATABASE = Path(__file__).resolve().parent.parent / 'databases'
        self.tabelas_criadas = []
        self._cria_tabela('log_interacoes', [
            'id INTEGER PRIMARY KEY AUTOINCREMENT',
            'modelo VARCHAR(150)',
            'ano_fabricacao INTEGER',
            'motorizacao VARCHAR(150)',
            'duvida_usuario TEXT',
            'kws_duvida_usuario TEXT',
            'resolucao TEXT'
        ])
        self._cria_tabela('webcatalogos', [
            'id INTEGER PRIMARY KEY AUTOINCREMENT',
            'fabricante VARCHAR(100)',
            'link VARCHAR(150)',
            'regra VARCHAR(150)'
        ])
        self._cria_tabela('pecas_automoveis',[
            'id INTEGER PRIMARY KEY AUTOINCREMENT',
            'nm_peca VARCHAR(100) NOT NULL',
            'codigo_peca VARCHAR(50) NOT NULL',
            'modelo VARCHAR(150)',
            'ano_fabricacao INTEGER',
            'motorizacao VARCHAR(150)',           
            'carros_compatíveis TEXT',           
        ])
        self._default_data()
        self.send_message(Message('system', f"Ao Realizar uma operação, você estritamente só poderá escolher entre as tabelas :[{','.join(self.tabelas_criadas)}]"))
        self.tool_calls = []
        self.tool_calls_func = {}

    def _default_data(self):
        # Esta lista é a fonte da verdade dos catálogos: o ausente é criado e o gravado com link ou regra
        # diferentes é corrigido. As lacunas <...> da regra são preenchidas por WebScrapper._get_data.
        catalogos = [
            {
                "fabricante":'Volkswagen',
                'link':'https://pecas.vw.com.br/todas-categorias',
                'regra':'q=<modelo> + <ano> + <motorizacao>&page=<num_page>'
            },
            {
                'fabricante': 'chevrolet',
                'link':'https://www.pecachevrolet.com.br/pesquisa',
                'regra':'nomepeca=<nome_peca>&nomeveiculo=<modelo>&ano=<ano>'
            }
        ]
        for data in catalogos:
            existentes = self._get_data('webcatalogos', {'fabricante': data['fabricante']})
            if not existentes:
                self.inserir('webcatalogos', data)
            elif any(existentes[0][campo] != valor for campo, valor in data.items()):
                self._atualizar_catalogo(existentes[0]['id'], data)

    def _atualizar_catalogo(self, id_linha:int, data:dict) -> None:
        print(f"--- CORRIGINDO CATÁLOGO GRAVADO: {data['fabricante']} ---")
        chave = self._chave('webcatalogos', data)
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            conn.execute(
                f"UPDATE webcatalogos SET fabricante=?, link=?, regra=?, {CHAVE}=? WHERE id=?",
                (data['fabricante'], data['link'], data['regra'], chave, id_linha)
            )

    def _validar_tabela(self, tablename:str) -> None:
        # Nome de tabela não pode ser parametrizado em SQL: só entra na query se estiver na lista fixa.
        if tablename not in self.tabelas_criadas:
            raise ValueError(f"Tabela '{tablename}' não existe. Tabelas disponíveis: {self.tabelas_criadas}")

    def _colunas(self, tablename:str) -> list[tuple[str, str]]:
        """(nome, tipo) de cada coluna visível da tabela, na ordem em que foram criadas."""
        self._validar_tabela(tablename)
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            return [(col[1], str(col[2]).upper()) for col in conn.execute(f"PRAGMA table_info({tablename})") if col[1] != CHAVE]

    def esquema(self) -> dict[str, list[str]]:
        """{tabela: [colunas]}: o que o modelo precisa saber para montar filtros válidos."""
        return {t: [nome for nome, _ in self._colunas(t)] for t in self.tabelas_criadas}

    def _get_data(self, tablename:str, filter:dict|None = None):
        colunas = dict(self._colunas(tablename))
        where, params = [], []
        for coluna, valor in (filter or {}).items():
            if coluna not in colunas:
                raise ValueError(f"Coluna '{coluna}' não existe em '{tablename}'. Colunas disponíveis: {list(colunas)}")
            if any(t in colunas[coluna] for t in ('CHAR', 'TEXT')):
                where.append(f"{coluna} LIKE ? COLLATE NOCASE")
                params.append(f"%{valor}%")
            else:
                where.append(f"{coluna} = ?")
                params.append(valor)
        sql = f"SELECT {','.join(colunas)} FROM {tablename}" + (f" WHERE {' AND '.join(where)}" if where else "")
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            conn.row_factory = sqlite3.Row
            return [dict(line) for line in conn.execute(sql, params).fetchall()]

    def resgatar(self, tablename:str, filtros:dict|None = None):
        """Leitura com erro como dado: tabela ou coluna inválida volta como {'erro': ...} listando o que existe."""
        if filtros is not None and not isinstance(filtros, dict):
            return {'erro': 'Os filtros devem ser um objeto no formato {coluna: valor}'}
        try:
            return self._get_data(tablename, filtros)
        except ValueError as err:
            return {
                'erro': str(err),
                'dica': (
                    "Refaça a consulta usando somente as tabelas e colunas de 'esquema'; "
                    "se o filtro inválido não for essencial, omita-o ou envie query_filter {}. "
                    "O erro é da consulta, não do usuário: não peça a ele que confirme dados por causa dele."
                ),
                'esquema': self.esquema(),
            }

    def _get_db_json_format(self, tablename):
        type_str = ['VARCHAR', 'TEXT', 'CHAR']
        # PRAGMA table_info: nome, tipo; a coluna `id` é gerada pelo banco e não entra no schema
        list_props = [
            {
                'name':nome,
                'type':tipo.lower() if not any(x in tipo for x in type_str) else 'string'
            }
            for nome, tipo in self._colunas(tablename) if(nome != 'id')]
        return createJsonFormat(f'{tablename}_json_format', list_props)

    def _cria_tabela(self, tablename, fields:list[str]):
        self.tabelas_criadas.append(tablename)
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            cursor = conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {tablename}({','.join(fields)})")
        self._garantir_chave(tablename)

    def _chave_de(self, colunas:list[str], dados:dict) -> str:
        """Hash do conteúdo: mesmas colunas e mesmos valores (sem diferenciar maiúsculas ou espaços) dão a mesma chave."""
        canonico = {c: ('' if dados.get(c) is None else str(dados[c]).strip().casefold()) for c in colunas}
        return hashlib.sha256(json.dumps(canonico, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()

    def _chave(self, tablename:str, dados:dict) -> str:
        return self._chave_de([nome for nome, _ in self._colunas(tablename) if nome != 'id'], dados)

    def _garantir_chave(self, tablename:str) -> None:
        """Migra bancos antigos: cria a coluna da chave, preenche as linhas existentes e impede novas duplicatas."""
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            colunas = [c[1] for c in conn.execute(f"PRAGMA table_info({tablename})")]
            if CHAVE not in colunas:
                conn.execute(f"ALTER TABLE {tablename} ADD COLUMN {CHAVE} TEXT")
            visiveis = [c for c in colunas if c not in ('id', CHAVE)]
            conn.row_factory = sqlite3.Row
            usadas = {r[0] for r in conn.execute(f"SELECT {CHAVE} FROM {tablename} WHERE {CHAVE} IS NOT NULL")}
            for linha in conn.execute(f"SELECT id, {','.join(visiveis)} FROM {tablename} WHERE {CHAVE} IS NULL").fetchall():
                chave = self._chave_de(visiveis, dict(linha))
                if chave in usadas: continue  # duplicata antiga: fica sem chave, o índice único ignora NULL
                conn.execute(f"UPDATE {tablename} SET {CHAVE}=? WHERE id=?", (chave, linha['id']))
                usadas.add(chave)
            conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{tablename}_{CHAVE} ON {tablename}({CHAVE})")

    def _inserir_tabela(self, tablename, data:dict) -> dict:
        print(f"""
            --- REALIZANDO INSERÇÃO EM BASE ---
                - nm_tabela: {tablename}
                - dados: {data}
        """)
        colunas = [nome for nome, _ in self._colunas(tablename) if nome != 'id']
        dados = {k: v for k, v in data.items() if k != 'id'}
        desconhecidas = [k for k in dados if k not in colunas]
        if desconhecidas:
            raise ValueError(f"Colunas inexistentes em '{tablename}': {desconhecidas}. Colunas disponíveis: {colunas}")
        chave = self._chave_de(colunas, dados)
        cols = [c for c in colunas if c in dados]
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            if conn.execute(f"SELECT 1 FROM {tablename} WHERE {CHAVE} = ?", (chave,)).fetchone():
                return {'ja_existia': True}
            conn.execute(
                f"INSERT INTO {tablename} ({','.join(cols + [CHAVE])}) VALUES ({','.join('?' * (len(cols) + 1))})",
                [dados[c] for c in cols] + [chave]
            )
        return {'ja_existia': False}

    def inserir(self, tablename:str, dados:dict) -> dict:
        """Escrita idempotente, com erro como dado. A chave vem do conteúdo: repetir a chamada não grava de novo."""
        try:
            resultado = self._inserir_tabela(tablename, dados)
        except (ValueError, sqlite3.Error) as err:
            return {'erro': f'Falha ao inserir em {tablename}: {err}'}
        return {
            'sucesso': 'Linha já existia, nada foi gravado.' if resultado['ja_existia'] else 'Linha registrada com sucesso!',
            **resultado
        }

    def _loop_insert_data(self, sys_message):
        try:
            conteudo = json.loads(sys_message['conteudo'])
            json_format = self._get_db_json_format(conteudo['nm_tabela'])
            messages = [
                Message('system', 'Estruture os dados que serão enviados pelo o usuário em um json').to_dict(),
                Message('user', str(conteudo['dado_a_ser_registrado'])).to_dict()
            ] 
            # Técnica: extração estruturada zero-shot.
            # Contrato: schema estrito derivado das colunas da tabela (PRAGMA table_info), sem `id`.
            # Impede: coluna inexistente ou valor de tipo errado chegar ao INSERT.
            response = json.loads(self.client.chat.completions.create(
                model= self.model,
                messages=messages,
                response_format=json_format,
                temperature=0
            ).choices[0].message.content)
            return self.inserir(conteudo['nm_tabela'], response)
        except Exception as err:
            print(err)
            return {'erro': f'Falha ao tentar inserir registro: {err}'}

    def _loop_select_data(self, sys_message):
        try:
            conteudo = json.loads(sys_message['conteudo'])
            return self.resgatar(conteudo['nm_tabela'], conteudo.get('filtros'))
        except Exception as err:
            print(err)
            return {'erro': f'Falha ao tentar recuperar dados: {err}'}
   
    def run(self):
        response_format = createJsonFormat('loop_json_format', [
            {'name':'pensamento', 'type':'string'},
            {'name':'acao', 'type':'string', 'enum':["RESGATAR_DADOS", "INSERIR_DADOS"]},
            {'name':'conteudo', 'type':'string'},
        ])
        for _ in range(1):
            self.send_message(Message('system','escolha qual será o proximo passo.'))
            # Técnica: roteamento zero-shot entre duas ações, com `pensamento` como justificativa curta.
            # Contrato: schema estrito {pensamento, acao: RESGATAR_DADOS|INSERIR_DADOS, conteudo: JSON em string}.
            #   O enum garante que a ação é válida, não que seja a certa.
            # Impede: ação fora das duas permitidas e resposta em texto livre.
            sys_message = json.loads(self.get_answer(response_format=response_format, temperature=0).content)
            
            if(sys_message['acao'] == "INSERIR_DADOS"):
                return self._loop_insert_data(sys_message)
            elif(sys_message['acao'] == "RESGATAR_DADOS"):
                return self._loop_select_data(sys_message)
