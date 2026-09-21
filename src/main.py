from orquestrador import Orquestrador
from leitor_manual_pdf import LeitorManualPDF
from openai import OpenAI
import os

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"]
)

orquestrador = Orquestrador(
    client=client,
    agents=[
        LeitorManualPDF(client)
    ]
)
orquestrador.run()