# Assistente Informacional de Manutenção Automotiva

Ajuda mecânicos e proprietários a (1) descobrir a peça compatível com um veículo e (2) tirar dúvidas do manual do proprietário. Recebe a pergunta em **texto livre**, pergunta o que falta, consulta a base local, o manual indexado ou o catálogo web da montadora e devolve um objeto validado com **resultado, fonte e suficiência**. É só informativo: não compra nem reserva peças.

Por dentro é um grafo LangGraph: o modelo só decide a intenção e os dados do texto livre; o resto é regra em código. Veja [docs/grafo.md](docs/grafo.md).

## Como rodar

Requisitos: Linux ou WSL, Python 3.12+, Chromium do sistema (o scraper usa `/usr/bin/chromium`) e uma chave de API (Groq) ou um modelo local no Ollama. **Sem nada disso instalado, use o Docker** (seção "Com Docker", logo abaixo).

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
| `AI_MODEL` | modelo a usar (obrigatório em `local`; em `remote` vazio usa `openai/gpt-oss-120b`). No Ollama use o nome com a tag, por exemplo `qwen2.5:7b` |
| `GROQ_API_KEY` | chave da Groq (modo `remote`) |

### Com Docker

Alternativa ao `venv`: a imagem já traz Python 3.14, o Chromium, as dependências e o modelo de embeddings. Só é preciso o Docker com o plugin Compose.

```bash
cp .env.example .env                       # preencha GROQ_API_KEY (deixe MODE vazio: vale remote)
docker compose build                       # 1ª vez: ~4 min e uma imagem de ~4 GB; depois fica em cache
docker compose run --rm app                # abre a conversa; "docker compose run --rm app minha-sessao" retoma uma sessão
```

- **Onde ficam os dados.** A base de peças, o índice do manual, a memória, as conversas e os logs ficam em volumes do Docker (`databases` e `logs`), que nascem com o conteúdo da imagem. Os arquivos do repositório não são alterados. `docker compose down -v` volta ao estado da imagem.
- **Outros scripts** rodam trocando o ponto de entrada: `docker compose run --rm --entrypoint python app conferir_grafo.py`.
- **Modelo local no Docker (perfil `local`).** `docker compose --profile local up -d ollama`, depois `docker compose --profile local run --rm puxar-modelo` (baixa o `AI_MODEL`; o `qwen2.5:7b` tem 4,7 GB) e `MODE=local AI_MODEL=qwen2.5:7b docker compose run --rm app`. **É lento**: o Ollama do contêiner usa só CPU (há um trecho de GPU NVIDIA comentado no `docker-compose.yml`), e o `LLM_TIMEOUT` padrão de 90 s pode estourar na leitura do manual. Para usar o Ollama já instalado no computador, ponha `OLLAMA_URL` no `.env` (Docker Desktop: `http://host.docker.internal:11434/v1`; Docker Engine no Linux/WSL, com o Ollama no Windows ou no próprio Linux: `docker run --rm -it --network host -e MODE=local -e AI_MODEL=qwen2.5:7b assistente-automotivo`, que enxerga o `localhost:11434` do computador).
- **Versão nos logs.** A imagem não tem o `.git`; o commit do carimbo vem do build: `docker compose build --build-arg CODE_COMMIT=$(git rev-parse --short HEAD)`. `codigo_limpo` fica `null` dentro do contêiner, porque não há como saber se havia alteração sem commit.
- **Validado** em 2026-10-23 (conversa real no contêiner, `MODE=local` apontando para o Ollama do computador): pergunta de peça, raspagem do catálogo da Chevrolet, pausa para aprovação, gravação e, numa segunda execução, resposta vinda da base guardada no volume. O modo `remote` (Groq) usa o mesmo caminho do código, mas **não foi exercitado** (sem chave neste ambiente).

Verificações úteis: `python src/verificar_local.py` (o modelo aceita saída estruturada e tool calling?) e `python conferir_grafo.py` (nós e arestas do grafo).

## Como usar

**O que a pessoa digita:** uma frase, como falaria no balcão. `python src/main.py` abre a conversa; Enter vazio encerra. Passar um nome de sessão (`python src/main.py minha-sessao`) retoma a conversa de onde ela parou.

**O que o sistema faz:** descobre se é pedido de peça ou dúvida de manual, pergunta o que faltar (uma coisa por vez), consulta a base local e, se não achar, o catálogo web (peça) ou o manual em PDF (dúvida). Antes de **gravar** peças do catálogo na base, ele **para e pede aprovação**.

**Exemplo real** (cenário `feliz`, log `logs/exemplos/feliz/trajetoria.jsonl`, commit `30e8bee` (árvore limpa), 2026-10-16, modelo `qwen2.5:7b`):

```
user: Qual o código da palheta traseira do Corsa 2008 1.4 da Chevrolet?
Bot: Encontrei 1 peça(s) para Corsa 2008 1.4 na base local:
  1. Palheta traseira ACDelco — código 93356933
[respondido | suficiencia=true | fonte: base_local]
```

Saída completa (objeto `Saida`, validado em [src/contrato.py](src/contrato.py)):

```json
{
  "resultado": "Encontrei 1 peça(s) para Corsa 2008 1.4 na base local:\n  1. Palheta traseira ACDelco — código 93356933",
  "dados": [
    {
      "nome_peca": "Palheta traseira ACDelco",
      "codigo_peca": "93356933",
      "carros_compativeis": [
        "Corsa A Hatch",
        "Corsa A Pickup",
        "Corsa A Sedan",
        "Corsa A Wagon"
      ]
    }
  ],
  "fonte": [
    {
      "tipo": "base_local",
      "origem": "pecas_automoveis",
      "evidencia": "1 linha(s) com {'modelo': 'Corsa', 'ano_fabricacao': 2008, 'motorizacao': '1.4', 'nm_peca': 'palheta traseira'}"
    }
  ],
  "suficiencia": true,
  "situacao": "respondido",
  "pergunta_pendente": null
}
```

**Quando o grafo para e espera alguém:** se a peça não está na base, o sistema busca no catálogo e mostra o que **vai gravar**:

```
Vou GRAVAR 24 peça(s) na base local (tabela pecas_automoveis) para Onix 2018 1.0, vindas do catálogo da Chevrolet:
  1. Bujão do orifício do atuador da tampa traseira — código 52056750
  ...
Consequência: respostas futuras sobre este veículo passam a usar estes dados, sem nova consulta ao catálogo. ...
Prazo: 24 h; depois disso nada é gravado.
Responda: aprovar | rejeitar | editar remover 3,5 | editar codigo 2 ABC123
aprovação:
```

Você pode aprovar, rejeitar ou **aprovar editando** (remover itens ou corrigir um código). Se fechar o programa sem responder, a pendência fica salva: abra de novo com a mesma sessão e ela volta. Passado o prazo, nada é gravado. Detalhes em [docs/humano.md](docs/humano.md).

**Dúvidas de manual.** O sistema escolhe o PDF pelo modelo e pelo ano do veículo (se não há manual desse ano, diz que não tem, sem aproximar), busca por termo os 6 trechos mais relevantes e responde só com eles; se os trechos não respondem, recusa. Medições, corpus e limites em [docs/rag.md](docs/rag.md); `python avaliar_rag.py perguntas` repete a avaliação.

**Memória.** O sistema lembra o veículo de cada usuário entre conversas (na seguinte, não precisa dizer de novo; ele avisa "Usei o veículo que você informou antes...") e reaproveita uma dúvida de manual já respondida quando a pergunta é praticamente a mesma. Nada é guardado se a resposta não foi entregue com base. Detalhes em [docs/memoria.md](docs/memoria.md).

**Apagar os próprios dados.** Basta pedir ("apague todos os meus dados"). O sistema conta o que vai apagar, **para e pede confirmação** (`confirmar` ou `cancelar`) e só então apaga o veículo lembrado, as dúvidas registradas, as conversas salvas e os logs. Quem administra usa `python src/esquecer.py <user_id>` e confere com `python verificar_remocao.py <user_id>`.

**O que o sistema não faz e como recusa:**
- compra, reserva, preço e diagnóstico de defeito: responde o que ele faz e encerra (`fora_do_escopo`);
- sem dados suficientes: pergunta; depois de 3 perguntas iguais sem resposta, desiste e diz por quê;
- sem base para responder: diz que não encontrou (`sem_base`) em vez de inventar.

## Estrutura

```
src/              o sistema (grafo, nós, estado, contrato, memória, serviços)
  prompts/        prompts em arquivo, carregados em tempo de execução
Dockerfile, docker-compose.yml, .dockerignore   a imagem e o compose (seção "Com Docker")
conferir_grafo.py nós e arestas do grafo executado
verificar_remocao.py varre todas as estruturas atrás de um identificador (prova da remoção)
avaliar_rag.py   avalia o RAG com dados/perguntas_rag.json (`perguntas` pelo grafo, `manual` só pelo leitor)
gerar_exemplos.py roda os cenários de dados/exemplos.json no sistema real e grava logs/exemplos/ (os exemplos da documentação)
demo_reducer.py   demonstração do reducer num grafo paralelo
interfaces/       formatos auxiliares usados pelos scripts de verificação
databases/        SQLite local, índice ChromaDB e manuais em PDF
docs/             case, modelos, prompts, arquitetura, io, memória, RAG, grafo, humano, fontes
logs/             trajetória de cada execução (um JSON por evento)
```

## Contribuidores

- Christian Lima Santana
- Marcelo Fernandes de Oliveira Junior
- Gustavo Oliveira dos Santos
