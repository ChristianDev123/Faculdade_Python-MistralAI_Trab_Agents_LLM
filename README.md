# Assistente Informacional de Manutenção Automotiva

Agente que ajuda mecânicos e proprietários a (1) identificar peças compatíveis com um veículo e (2) responder dúvidas a partir do manual do proprietário. Recebe a pergunta em **texto livre**, pergunta o que falta e consulta, nesta ordem, a base local (SQLite), o manual indexado (ChromaDB) ou o catálogo de peças (web scraping). É apenas informativo: não compra nem reserva peças.

## Como rodar

Requisitos: Linux ou WSL, Python 3.12+, Chromium do sistema (o web scraping usa `/usr/bin/chromium`) e uma chave de API (Groq) ou um modelo local no Ollama.

```bash
sudo apt install chromium
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # e preencha as variáveis (veja abaixo)
python src/main.py
```

Variáveis do `.env` (nomes em `.env.example`):

| Variável | Para quê |
|---|---|
| `MODE` | `remote` (Groq) ou `local` (Ollama em `localhost:11434`) |
| `AI_MODEL` | modelo a usar (obrigatório em `local`; em `remote` vazio usa `openai/gpt-oss-120b`) |
| `GROQ_API_KEY` | chave da Groq (modo `remote`) |

## Como usar

> **Pendente:** exemplo principal (entrada digitada + saída completa) e comportamento quando o grafo para e espera uma pessoa. Serão preenchidos a partir de uma execução real — ver `docs/io.md` e `logs/`.

## Estrutura

```
src/              o sistema (agentes, ferramentas)
  prompts/        prompts em arquivo, carregados em tempo de execução
interfaces/       classes base (Agent, Message, ToolCall, formatos JSON)
databases/        SQLite local, índice ChromaDB e manuais em PDF
docs/             case, modelos, prompts, arquitetura, io, memória, RAG, grafo, humano, fontes
logs/             execuções demonstradas
```

## Contribuidores

- Christian Lima Santana
- Marcelo Fernandes de Oliveira Junior
- Gustavo Oliveira dos Santos
