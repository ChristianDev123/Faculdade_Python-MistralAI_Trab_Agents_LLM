import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # lê o .env na raiz do projeto, se existir

base_url = ""
api_key = ""
MODEL = None

if(os.environ['MODE'] == 'local'):
    base_url = 'http://localhost:11434/v1'
    api_key = 'ollama'
    MODEL = os.environ["AI_MODEL"]
else:
    base_url = "https://api.groq.com/openai/v1"
    api_key = os.environ["GROQ_API_KEY"]
    
client = OpenAI(
    base_url = base_url,
    api_key = api_key,
)