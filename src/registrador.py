import sys
from pathlib import Path
sys.path.append(Path(__file__).resolve().parent.parent)
from interfaces.agent import Agent
from interfaces.message import Message
from interfaces.json_format import createJsonFormat
from openai import OpenAI
import sqlite3
import json


class Registrador(Agent):
    
    def __init__(self, client:OpenAI):
        super().__init__('registrador',client)
        self.input = input
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
        ])
        self._default_data()
        self.send_message(Message('system', f"Ao Realizar uma operação, você estritamente só poderá escolher entre as tabelas :[{','.join(self.tabelas_criadas)}]"))
        self.tool_calls = []
        self.tool_calls_func = {}

    def _default_data(self):
        if(len(self._get_data('webcatalogos')) == 0):
            datalist = [
                {
                    "fabricante":'Volkswagen',
                    'link':'https://pecas.vw.com.br/todas-categorias',
                    'regra':'q=<modelo> + <ano> + <motorizacao>&page=<num_page>'
                },
            ]
            for data in datalist: 
                self._inserir_tabela('webcatalogos',data)

    def _get_data(self, tablename:str, filter:list[str] = []):
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"""SELECT * FROM {tablename}""")
            return [dict(line) for line in cursor.fetchall()]
        
    def _get_db_json_format(self, tablename):
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({tablename})")

            # Estrutura: cid, nome_campo, tipo campo, not null (0=false, 1=true), default_value, primary key (0=False, 1=True)
            columns = cursor.fetchall()

            type_str = ['VARCHAR', 'TEXT', 'CHAR']
            
            list_props = [
                {
                    'name':col[1], 
                    'type':str(col[2]).lower() if not any(map(lambda x: x in col[2], type_str)) else 'string' 
                } 
                for col in columns if(col[1] != 'id')]
            return createJsonFormat(f'{tablename}_json_format', list_props)
            
    def _cria_tabela(self, tablename, fields:list[str]):
        self.tabelas_criadas.append(tablename)
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            cursor = conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {tablename}({','.join(fields)})")

    def _inserir_tabela(self, tablename, data:dict):
        print(f"""
            --- REALIZANDO INSERÇÃO EM BASE ---
                - nm_tabela: {tablename}
                - dados: {data}
        """)
        with sqlite3.connect(self.PATH_DATABASE / 'db.sqlite') as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {tablename} LIMIT 0")
            if(data.get('id')): del data['id']
            cols = [str(col[0]) for col in cursor.description if(str(col[0]) != 'id')]
            desc_db = self._get_db_json_format(tablename)['json_schema']['schema']['properties']
            ordenated_data=dict(sorted(data.items(), key=lambda item: cols.index(item[0])))
            def func_map(key):    
                if(str(desc_db[key]['type']).lower() in ['integer', 'float', 'decimal']):
                    return str(ordenated_data[key])
                else:
                    return f"'{ordenated_data[key]}'"
            ordenated_data = list(map(func_map, ordenated_data.keys()))
            cursor.execute(f"""
                INSERT INTO {tablename} 
                ({','.join(cols)})
                VALUES
                ({','.join(ordenated_data)})
            """)

    def _loop_insert_data(self, sys_message):
        conteudo = json.loads(sys_message['conteudo'])
        json_format = self._get_db_json_format(conteudo['nm_database'])
        messages = [
            Message('system', 'Estruture os dados que serão enviados pelo o usuário em um json').to_dict(),
            Message('user', str(conteudo['dado_a_ser_registrado'])).to_dict()
        ] 
        response = json.loads(self.client.chat.completions.create(
            model= self.model,
            messages=messages,
            response_format=json_format,
            temperature=0
        ).choices[0].message.content)
        try:
            self._inserir_tabela(conteudo['nm_tabela'], response)
            return {'Sucesso': 'Linha registrada com sucesso!'}
        except Exception as err:
            print(err)
            return {'Erro':'Falha ao tentar inserir registro!'}

    def _loop_select_data(self, sys_message):
        conteudo = json.loads(sys_message['conteudo'])
        try:
            response = self._get_data(conteudo['nm_tabela'],[])
            return response
        except Exception as err:
            print(err)
            return {'Erro': 'Falha ao tentar recuperar dados'}
   
    def run(self):
        response_format = createJsonFormat('loop_json_format', [
            {'name':'pensamento', 'type':'string'},
            {'name':'acao', 'type':'string', 'enum':["RESGATAR_DADOS", "INSERIR_DADOS"]},
            {'name':'conteudo', 'type':'string'},
        ])
        for _ in range(1):
            self.send_message(Message('system','escolha qual será o proximo passo.'))
            sys_message = json.loads(self.get_answer(response_format=response_format).content)
            
            if(sys_message['acao'] == "INSERIR_DADOS"):
                return self._loop_insert_data(sys_message)
            elif(sys_message['acao'] == "RESGATAR_DADOS"):
                return self._loop_select_data(sys_message)