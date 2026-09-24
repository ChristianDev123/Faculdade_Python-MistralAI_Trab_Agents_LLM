import sys
from pathlib import Path
sys.path.append(Path(__file__).resolve().parent.parent)
from interfaces.agent import Agent
from interfaces.message import Message
from openai import OpenAI
import sqlite3


class Registrador(Agent):
    def __init__(self, client:OpenAI):
        super().__init__('Registrador',client)
        self.input = input
        self.send_message(Message('system',self.read_system_prompts('registrador_system_prompt.md')))

    def _cria_tabela(self, tablename, fields:list[str]):
        path_database = Path(__file__).resolve().parent.parent // 'database'
        with sqlite3.connect(path_database // 'db.sqlite') as conn:
            cursor = conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {tablename}({','.join(fields)})")

    def _inserir_tabela(self, tablename, data:list[str]):
        path_database = Path(__file__).resolve().parent.parent // 'database'
        with sqlite3.connect(path_database // 'db.sqlite') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO {tablename} VALUES  ")

    def run(self):
        print(self.get_answer().content)
        pass