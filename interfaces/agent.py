from openai import OpenAI
from abc import ABC, abstractmethod
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from interfaces.message import Message
from pathlib import Path
import os

class Agent(ABC):
    def __init__(self, name:str, client:OpenAI, model="openai/gpt-oss-120b"):
        self.name = name
        self.client = client
        self.messages = []
        self.model = model
        
    @abstractmethod
    def run(self):
        pass

    def read_system_prompts(self, filename):
            path = Path(__file__).resolve().parent.parent
            with open(f'{path}/prompts/{filename}','r') as prompt:
                return prompt.read()

    def send_message(self, message:Message)->None:
        self.messages.append(message.to_dict())
        
    def get_answer(self, **kwargs):
        response = self.client.chat.completions.create(
            model= self.model,
            messages=self.messages,
            **kwargs
        )
        self.send_message(Message('assistant', response.choices[0].message.content))
        return response.choices[0].message