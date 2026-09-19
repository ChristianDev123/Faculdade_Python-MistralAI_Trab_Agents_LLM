import os
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from openai import OpenAI
from prompts.system_prompt import SYSTEM_PROMPT

load_dotenv()

CASOS = [
    ("1. Simples (dados completos)",
     "Preciso de pastilha de freio dianteira pro Onix 2021, motor 1.0 Turbo."),
    ("2. Motorização não informada",
     "Filtro de óleo pro HB20 2019."),
    ("3. Ano na fronteira de duas gerações",
     "Amortecedor traseiro pro Corolla 2019/2020."),
    ("4. Peça descontinuada, com substituta",
     "O usuário perguntou pela pastilha de freio traseira do Civic 2015. "
     "A ferramenta de consulta ao catálogo retornou: peça original DEF456 "
     "foi descontinuada pelo fabricante; a substituta indicada é a peça "
     "UVW321. Responda ao usuário."),
    ("5. Peça sem substituta",
     "O usuário perguntou pelo amortecedor dianteiro de um Fiat Uno 1998. "
     "A ferramenta de consulta ao catálogo retornou: nenhuma peça "
     "compatível encontrada, e não há substituta cadastrada. Responda "
     "ao usuário."),
]

client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=os.environ["MISTRAL_API_KEY"])

for nome, texto in CASOS:
    try:
        resp = client.chat.completions.create(
            model="mistral-small-latest",
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": texto},
            ],
        )
        print(f"{nome}: {resp.choices[0].message.content}\n")
    except Exception as e:
        print(f"{nome}: [ERRO] {e}\n")
    time.sleep(15)