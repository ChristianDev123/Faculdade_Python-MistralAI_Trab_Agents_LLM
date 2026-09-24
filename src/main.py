from dotenv import load_dotenv
load_dotenv()
from orquestrador import Orquestrador
from leitor_manual_pdf import LeitorManualPDF
from openai import OpenAI
import os


if(os.environ['MODE'] == 'local'):
    client = OpenAI(
        base_url='http://localhost:11434/v1',
        api_key='ollama'
    )
else:
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