import os
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from openai import OpenAI
from prompts.system_prompt import SYSTEM_PROMPT

load_dotenv()

CANDIDATOS = {
    "mistral_small": dict(
        base_url="https://api.mistral.ai/v1",
        api_key=os.environ["MISTRAL_API_KEY"],
        model="mistral-small-latest",
    ),
    "gpt_oss_groq": dict(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
        model="openai/gpt-oss-120b",
    ),
    "gemini_flash": dict(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=os.environ["GOOGLE_API_KEY"],
        model="gemini-3.6-flash",
    ),
}

# Os 5 casos do docs/modelos.md § 3.3
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


def chamar_com_retry(client, cfg, mensagens, tentativas=3):
    for tentativa in range(tentativas):
        try:
            return client.chat.completions.create(
                model=cfg["model"], temperature=0, messages=mensagens
            )
        except Exception as e:
            if "429" in str(e) and tentativa < tentativas - 1:
                espera = 5 * (tentativa + 1)
                print(f"    rate limit, esperando {espera}s...")
                time.sleep(espera)
                continue
            raise


def rodar():
    linhas = [f"# Verificação mínima — {datetime.now():%Y-%m-%d %H:%M}\n"]

    for nome_caso, texto_caso in CASOS:
        linhas.append(f"\n## {nome_caso}\nEntrada: {texto_caso}\n")
        print(f"\n=== {nome_caso} ===")

        for nome_modelo, cfg in CANDIDATOS.items():
            print(f"  consultando {nome_modelo}...")
            try:
                client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
                resp = chamar_com_retry(client, cfg, [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": texto_caso},
                ])
                saida = resp.choices[0].message.content
            except Exception as e:
                saida = f"[ERRO] {e}"

            linhas.append(f"\n**{nome_modelo}:**\n{saida}\n")
            time.sleep(1.5)  # pausa entre chamadas, evita novo rate limit

    os.makedirs("docs", exist_ok=True)
    caminho = "docs/verificacao-modelos.txt"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))

    print(f"\nPronto. Resultado salvo em {caminho}")


if __name__ == "__main__":
    rodar()