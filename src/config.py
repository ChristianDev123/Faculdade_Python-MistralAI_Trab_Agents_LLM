import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # lê o .env na raiz do projeto, se existir

client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
MODEL = os.environ["LLM_MODEL"]