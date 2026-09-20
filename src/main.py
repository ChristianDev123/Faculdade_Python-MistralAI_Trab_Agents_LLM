from orquestrador import Orquestrador
from openai import OpenAI
import os

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"]
)

orquestrador = Orquestrador(client)
orquestrador.run()