from dotenv import load_dotenv
load_dotenv()
from orquestrador import Orquestrador
from leitor_manual_pdf import LeitorManualPDF
from registrador import Registrador
from openai import OpenAI
import os
from pathlib import Path
import sys
sys.path.append(Path(__file__).resolve().parent.parent)
from interfaces.message import Message

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
        LeitorManualPDF(client),
        Registrador(client)
    ]
)
orquestrador.run()


# r = Registrador(client)
# r.send_message(Message('user', '{' \
# '"modelo":"Fox", "Ano":2015, "motorizacao":1.6,'
# '"duvida_usuario":"Quais são os itens de segurança presentes no meu carro?",' \
# '"kws_duvida_usuario":["segurança","itens","carro"],' \
# '"resolucao":"O veículo possui diversos itens de segurança, incluindo airbags, ' \
#             'apoios de cabeça, bancos, cintos de segurança com limitador e pré‑tensionador, ' \
#             'coluna de direção, freios e freio de estacionamento, luz de advertência dos cintos, ' \
#             'luz de controle dos airbags e unidades de controle e sensores.' \
# '"}'))
# r.run()