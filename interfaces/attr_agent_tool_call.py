import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from agent import Agent

class AttrAgentToolCall:
    def __init__(self, id:str, json_schema:dict, ref:Agent):
        self.id = id,
        self.json_schema = json_schema,
        self.ref = ref