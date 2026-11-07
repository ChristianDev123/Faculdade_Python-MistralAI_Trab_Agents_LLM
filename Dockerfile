# Python 3.14: a versão em que o requirements.txt foi congelado.
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

# Torch em CPU, na versão fixada no requirements.txt, sem os pacotes de GPU (nvidia-*, cuda-*, triton), que pesam vários GB.
COPY requirements.txt .
RUN grep -v -E '^(nvidia-|cuda-|triton==)' requirements.txt \
      | sed -E 's/^torch==(.+)$/torch==\1+cpu/' > /tmp/requirements-cpu.txt \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements-cpu.txt

# O modelo de embeddings fica dentro da imagem.
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
