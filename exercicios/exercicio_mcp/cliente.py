
import os
from dotenv import load_dotenv
load_dotenv()
from langchain_ollama import ChatOllama

MODELO = os.environ.get("AI_MODEL")

modelo = ChatOllama(
    model=MODELO,
    base_url="http://localhost:11434",
    validate_model_on_init=True,
)