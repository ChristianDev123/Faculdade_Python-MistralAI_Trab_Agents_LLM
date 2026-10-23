# Imagem do assistente. Alternativa ao venv do README: não precisa instalar Python, Chromium nem dependências no computador.
# Python 3.14 é a versão em que o requirements.txt foi congelado.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    CHROMIUM_NO_SANDBOX=1

# O scraper usa o Chromium do sistema (/usr/bin/chromium), não o baixado pelo Playwright.
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# O requirements.txt foi gerado numa máquina com GPU: traz o torch com CUDA e uns vinte pacotes nvidia-*/cuda-*/triton que juntos
# pesam vários GB. No contêiner o torch roda em CPU (só serve para gerar os embeddings da memória episódica), na MESMA versão fixada,
# vinda do índice CPU do PyTorch. O requirements.txt do repositório não é alterado.
COPY requirements.txt .
RUN grep -v -E '^(nvidia-|cuda-|triton==)' requirements.txt \
      | sed -E 's/^torch==(.+)$/torch==\1+cpu/' > /tmp/requirements-cpu.txt \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements-cpu.txt

# O modelo de embeddings fica dentro da imagem: a primeira execução não depende do Hugging Face.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY src ./src
COPY interfaces ./interfaces
COPY dados ./dados
COPY databases ./databases
COPY *.py ./

# Sem o .git na imagem, o carimbo de versão dos logs vem daqui: docker compose build --build-arg CODE_COMMIT=$(git rev-parse --short HEAD)
ARG CODE_COMMIT=
ENV CODE_COMMIT=${CODE_COMMIT}

ENTRYPOINT ["python", "src/main.py"]
