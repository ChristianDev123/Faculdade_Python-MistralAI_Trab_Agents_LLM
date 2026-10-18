# Arquitetura do agente

Este documento descreve o sistema **como ele está hoje**, nas seis perguntas que a arquitetura precisa responder. O grafo em detalhe, os padrões e o estado estão em [grafo.md](grafo.md); as paradas humanas em [humano.md](humano.md); a memória em [memoria.md](memoria.md); a recuperação em [rag.md](rag.md); o contrato em [io.md](io.md) e os prompts em [prompts.md](prompts.md).

> **Proveniência.** Os números e as execuções citados vêm de `python gerar_exemplos.py`, rodado em 2026-10-16 sobre o commit `30e8bee` com a árvore limpa, no modelo `qwen2.5:7b` (local). Os logs estão em `logs/exemplos/`.

## 1. O desenho

### 1.1 Os componentes

```
 pessoa ── texto livre ──► src/main.py ──► grafo.invoke(thread_id = "<usuário>:<sessão>")
 (balcão/Discord)  + user_id     (CLI)             │
 ◄── Saida validada ◄───────────────────────────── │
                                                    ▼
   ┌───────────────────────────── LangGraph  (src/grafo.py, 15 nós) ───────────────────────────────┐
   │  ★ MODELO decide:  extrair (intenção e dados do veículo)                                     │
   │                     ler_manual (a dúvida foi respondida pelos trechos?)                      │
   │                     raspar (extrai as peças da página do catálogo)                           │
   │  CÓDIGO decide:    as 8 funções de rota (22 arestas), os portões, as perguntas, a recusa,    │
   │                     a consulta, a gravação, o texto da resposta e o motivo de término        │
   │  ⏸ HUMANO decide:  aprovar_gravacao (gravar peças do catálogo)                               │
   │                     confirmar_esquecimento (apagar os dados do titular)                      │
   └──────┬───────────────┬──────────────────┬────────────────────┬─────────────────┬────────────┘
          ▼               ▼                  ▼                    ▼                 ▼
  databases/db.sqlite  databases/chroma_db  databases/manuais/  databases/         logs/<usuário>/
  pecas_automoveis     trechos dos manuais  PDFs               checkpoints.sqlite  <sessão>/
  webcatalogos         (lidos por BM25) e                      (estado de cada     trajetoria.jsonl
  log_interacoes       memoria_episodica                       conversa)           (um evento por passo)
  memoria_semantica    (vetores)                                                   src/prompts/ (versão
                                                                                   carimbada no log)
```

Sites externos: apenas o catálogo web da montadora, consultado pelo nó `raspar` (leitura). O modelo roda no Ollama (`MODE=local`) ou na Groq (`MODE=remote`).

### 1.2 O grafo, com quem decide cada passo

Este é o mesmo desenho de [grafo.md](grafo.md) §2 (a fonte única). `[MODELO]` marca o que só o modelo decide; `[código]` o que é regra; `⏸ INTERRUPT` onde o sistema para e espera uma pessoa. As condições de parada são os destinos em `emitir` e `END`; a lista completa está na §2.5.

```
START
  │
  ▼
entrada ─┬─ turno 1 ──► lembrar [código: lê a memória semântica] ──┐
 [código]│                                                         ▼
         ├─ turno > 1 ──────────────────────────────────────────► extrair            1 chamada ao modelo
         │                                                      [MODELO] Extracao{intencao, veiculo, ...}
         └─ passou do limite de turnos ─► emitir                    │
                                                                    ▼  rota_pos_extracao  [CÓDIGO]
        ┌───────────────┬──────────────┬──────────────┬────────────┘
   ESQUECER      fora do escopo   faltam dados /     completo
        │              │          3ª repetição           │
        ▼              ▼              ▼                  ▼
 confirmar_esquecimento recusar    perguntar        consultar_base [código]
 ⏸ INTERRUPT [humano]  [código]    [código]        MANUAL: busca episódica por similaridade
        │                 │           │                  │ rota_pos_base [CÓDIGO]
   confirmou/cancelou     │           │       ┌──────────┼───────────────┐
        │                 │           │     achou    PECA sem base   MANUAL sem base
        ▼                 │           │       │           ▼                ▼
    esquecer              │           │       │        raspar          ler_manual
    [código: apaga]       │           │       │      [MODELO]     [busca textual + MODELO]
        │                 │           │       │     NÃO grava        RAG → {trecho, sanada}
        │                 │           │       │           │                │
        │                 │           │       │   rota_pos_raspagem  rota_pos_manual
        │                 │           │       │           │                │
        │                 │           │       │    erro/vazio│candidatas  sanada│não sanada/erro
        │                 │           │       │           ▼                ▼
        │                 │           │       │   aprovar_gravacao   registrar_duvida
        │                 │           │       │    ⏸ INTERRUPT       [código, grava a
        │                 │           │       │           │           memória episódica]
        │                 │           │       │   rota_pos_aprovacao        │
        │                 │           │       │     aprovou/editou          │
        │                 │           │       │           ▼                 │
        │                 │           │       │        gravar               │
        ▼                 ▼           ▼       ▼           ▼                 ▼
       ═══════════════════════════════ emitir ═════════════════════════════════
                  [código] valida Saida (Pydantic), grava log e motivo_termino
                                       │ rota_pos_emissao [CÓDIGO]
                              respondido│            │ qualquer outro motivo
                                        ▼            ▼
                                   memorizar        END
                      [código: grava a memória semântica] ──► END
```

## 2. As seis perguntas

### 2.1 As ferramentas

O modelo **não escolhe ferramentas**: nenhuma é exposta a ele como função. Cada capacidade abaixo é chamada por um nó, e a escolha do nó é uma aresta decidida por código.

| Capacidade | Nó | O que faz | Leitura ou escrita | Reversível? | Conversa com |
|---|---|---|---|---|---|
| `Registrador.resgatar` | `consultar_base` | consulta com filtros (texto "contém", número "igual") | leitura | n/a | SQLite |
| `Memoria.buscar_episodio` | `consultar_base` | pergunta parecida já respondida | leitura | n/a | Chroma (vetores) |
| `LeitorManualPDF.ler` | `ler_manual` | BM25 nos trechos do manual e leitura pelo modelo | leitura | n/a | Chroma (trechos), PDFs |
| `WebScrapper.buscar_candidatas` | `raspar` | navegador sem tela no catálogo; os cartões `/peca/<código>/` são lidos em código, e só a página sem esse formato vai ao modelo (em lotes, com o código conferido contra o texto) | leitura externa; **não grava** | n/a | sites das montadoras |
| `Registrador.inserir` em `pecas_automoveis` | `gravar` | grava peça do catálogo, idempotente | **escrita** | só por `DELETE` manual; **exige aprovação humana** | SQLite |
| `Registrador.inserir` em `log_interacoes` e `Memoria.registrar_episodio` | `registrar_duvida` | guarda a dúvida respondida e o vetor | **escrita** | sim: `python src/esquecer.py --episodio <id>` | SQLite e Chroma |
| `Memoria.memorizar_veiculo` | `memorizar` | guarda o veículo; só acrescenta | **escrita** | sim, pela remoção do titular | SQLite |
| `Memoria.esquecer_usuario` | `esquecer` | apaga os dados do titular | **escrita destrutiva** | **não**; exige confirmação humana | todas as estruturas |

### 2.2 O laço

Dentro de uma mensagem **não há laço**: o grafo não tem ciclos, e cada mensagem percorre um caminho de 2 a 9 nós até o `emitir` (nas 28 mensagens dos cenários: de 2, no limite de mensagens, a 9, na gravação do catálogo). O que faz a volta seguinte existir é a **próxima mensagem da pessoa**: a CLI lê outra linha e chama o grafo de novo com o mesmo `thread_id`, e o checkpoint devolve o estado.

A cada mensagem acontece, nesta ordem: `entrada` (conta o turno, zera o que é por turno e registra o texto), `lembrar` (só na primeira), `extrair`, a rota decidida por código, a consulta ou a pergunta, `emitir` (valida e registra), `memorizar` (só se respondeu).

**Chamadas ao modelo por mensagem (medido, nos 19 cenários):** 1 quando o sistema pergunta, recusa ou acha a peça na base; 2 quando lê o manual; 1 quando raspa o catálogo da Chevrolet (a leitura é em código; o modelo só entra na reserva, e os cenários de `logs/exemplos/` com pausa foram gerados antes dessa mudança, com 2); 0 quando passa do limite de mensagens.

### 2.3 O estado

O que é objeto explícito e o que ficou na lista de mensagens está em [grafo.md](grafo.md) §6. Em resumo: a lista de mensagens guarda **só o texto da conversa**; intenção, veículo, peça, dúvida, candidatas, aprovação, contadores e motivo de término são campos próprios, cada um com o reducer que diz o que acontece quando dois nós escrevem. O estado inteiro é gravado no checkpoint a cada nó, o que permite retomar uma pausa depois de o processo terminar.

### 2.4 O orçamento

O que impede uma execução de não acabar:

| Teto | Valor | Onde | Observado |
|---|---|---|---|
| passos do grafo | `recursion_limit = 25`; o caminho mais longo percorre **9** nós (`entrada`, `lembrar`, `extrair`, `consultar_base`, `raspar`, `aprovar_gravacao`, `gravar`, `emitir`, `memorizar`) | `src/grafo.py` | o cenário `pausa_edicao` percorreu os 9 |
| mensagens por conversa | `MAX_TURNOS = 15` | `src/nos.py` | cenário `limite_turnos`, com o teto em 1 |
| tempo por chamada ao modelo | `LLM_TIMEOUT = 90` s, 1 retentativa | `src/config.py` | cenário `erro_modelo`, com o teto em 0,15 s |
| tokens de saída por chamada | 300 (`extrair`), 600 (`ler_manual`), 4096 (lote da reserva da raspagem) | `src/nos.py`, `leitor_manual_pdf.py`, `webscrapper.py` | — |
| páginas e tempo da raspagem | `MAX_PAGINAS = 3`, `MAX_SEGUNDOS = 120`, conferidos entre páginas e entre lotes; o `avisos` diz quando o teto cortou | `src/webscrapper.py` | `avaliar_raspagem.py modelo`: o teto de 120 s cortou a reserva em 91 e 111 peças |
| contexto enviado | `JANELA_TOKENS = 3000`, últimas 6 mensagens, 6 trechos do manual | `src/util.py`, `memoria.py` | [memoria.md](memoria.md) §1 |
| mesma pergunta sem resposta | 3 | `src/nos.py` | cenário `desistiu` |
| prazo da aprovação humana | 24 h (`PRAZO_APROVACAO_HORAS`) | `src/nos.py` | cenário `expirado`, com o prazo em 0,036 s |

**O que o orçamento não cobre:**
- **Tempo total por execução.** Só a raspagem tem teto de tempo total (120 s, conferido entre páginas e lotes); o resto do laço tem teto por chamada (`LLM_TIMEOUT`) e por passo. Uma única navegação ou chamada já lenta passa do teto da raspagem.
- **Páginas da raspagem.** O limite de 3 páginas é de código (antes era o `max_pagina` que o modelo lia da página). Quando corta, o `avisos` diz que podem faltar peças.
- **Dinheiro.** Com o modelo local o custo é zero; na Groq só há o teto de tokens por chamada, não por execução.

### 2.5 O término

Os doze motivos pelos quais uma execução termina. O motivo é definido **por código** em `emitir`, nunca pelo modelo.

| Motivo de término | `situacao` | Execução que o produziu | Log | Chamadas ao modelo | Duração da mensagem |
|---|---|---|---|---|---|
| `respondido` | `respondido` | `feliz` | `logs/exemplos/feliz/` | 1 | 2.9 s |
| `sem_base` | `sem_base` | `recusa_fora_corpus` | `logs/exemplos/recusa_fora_corpus/` | 2 | 12.6 s |
| `faltam_dados` | `faltam_dados` | `incompleta` | `logs/exemplos/incompleta/` | 1 | 2.7 s |
| `fora_do_escopo` | `fora_do_escopo` | `fora_escopo` | `logs/exemplos/fora_escopo/` | 1 | 2.9 s |
| `rejeitado_pelo_humano` | `rejeitado` | `rejeitado` | `logs/exemplos/rejeitado/` | 2 | 42.6 s |
| `aprovacao_expirada` | `expirado` | `expirado` | `logs/exemplos/expirado/` | 2 | 41.4 s |
| `desistiu_apos_3_perguntas` | `faltam_dados` | `desistiu` | `logs/exemplos/desistiu/` | 1 | 0.9 s |
| `erro_modelo` | `erro` | `erro_modelo` | `logs/exemplos/erro_modelo/` | 1 | 2.5 s |
| `limite_turnos` | `erro` | `limite_turnos` | `logs/exemplos/limite_turnos/` | 0 | 0.1 s |
| `esquecimento_recusado` | `rejeitado` | `esquecer_cancelar` | `logs/exemplo-titular-a/esquecer_cancelar-2/` | 1 | 8.5 s |
| `esquecido` | `esquecido` | `esquecer_confirmar` | (apagado pela própria remoção; ver abaixo) | 1 | 2.0 s |
| `erro_ferramenta` | `erro` | **não observado** | — | — | — |

**11 dos 12 motivos foram produzidos por execuções reais.** `erro_ferramenta` (a consulta ao banco, a leitura do manual ou o navegador levantam um erro) está implementado em `_montar_saida`, mas não consegui provocá-lo sem simular a falha; fica declarado como previsto e não observado.

**O `esquecido` não deixa log por desenho:** a remoção apaga `logs/<usuário>/`. A prova dele está em outro lugar: o `resultado.json` guarda a transcrição, a varredura independente logo após apagar deu **0 ocorrências** e a linha de auditoria da remoção (só com o hash do identificador) está em `cenarios.esquecer_confirmar.auditoria_da_remocao`. A conversa seguinte voltou a perguntar o modelo do veículo.

### 2.6 O humano

| Onde ele entra | Quem é chamado | Se ele não responder |
|---|---|---|
| `aprovar_gravacao`: gravar peças do catálogo na base | a pessoa que está na conversa | nada é gravado. O prazo de 24 h é conferido **quando alguém retoma** (não há temporizador); vencido, o motivo é `aprovacao_expirada` |
| `confirmar_esquecimento`: apagar os dados do titular | o próprio titular | nada é apagado; a pendência fica no checkpoint |
| fim de cada mensagem | a pessoa | a conversa só continua quando ela escreve de novo |

**O perfil não é distinguido.** Pelo [case.md](case.md), quem deveria aprovar gravação de peça no cache é o mecânico ou o balconista, que conhecem o domínio; o proprietário "descreve e consulta". Hoje **quem conversa aprova**, e o sistema não tem papel por usuário. Uma gravação aprovada pelo proprietário passaria sem o crivo de quem conhece a peça. Decisão pendente para o grupo; os detalhes das pausas estão em [humano.md](humano.md).

## 3. A defesa do nível de autonomia

**O nível é roteador.** Um modelo classifica a entrada em texto livre (nó `extrair`) e a rota seguinte é regra em código.

**Onde está a decisão que só o modelo toma** (marcada nos diagramas): `extrair` decide qual é a intenção e quais dados do veículo a pessoa já deu, a partir de uma frase como "me ve a palheta traseria do corsa 2008 motor 1.4". Não há regra em código que faça isso; seria um formulário. `ler_manual` decide se os trechos respondem a dúvida; `raspar` deixou de ser uma decisão do modelo no catálogo da Chevrolet: os códigos estão no endereço dos links, e ler isso é regra em código ([prompts.md](prompts.md) §5). O modelo só entra como reserva, para página de formato desconhecido.

**Por que o degrau de baixo (um workflow sequencial puro) não servia.** Sem o `extrair`, a entrada teria de ser um formulário, e o enunciado exclui isso: o ponto do sistema é descobrir o que a pessoa quer, perguntar o que falta e decidir quando já sabe o suficiente.

**Por que o degrau de cima (agente com laço livre) foi abandonado.** A primeira versão deixava o modelo escolher ferramenta a cada volta. Nas 22 execuções com log dessa versão (`logs/local/`, commits `a112ee2` e `d44a907`):

| Falha do laço livre | Ocorrências |
|---|---|
| o modelo escreveu o nome da ferramenta no campo `acao` em vez de chamá-la | 29 |
| chamadas de ferramenta que voltaram com erro | 17 de 60 |
| respostas ao usuário barradas por não ter consultado nenhuma fonte | 10 |
| execuções com pelo menos uma das duas primeiras falhas (ação inválida ou resposta barrada) | 12 de 22 |

Nenhuma decisão que sobrou exigia escolher uma ferramenta em tempo de execução: com a intenção conhecida, a fonte a consultar é determinada. **Ressalva:** essas 22 execuções são do `qwen2.5:7b`; o `gpt-oss-120b`, modelo escolhido em [modelos.md](modelos.md), não foi usado nelas nem nas medições do grafo. Com um modelo mais forte o laço livre poderia se comportar melhor, e o grafo continuaria sendo a opção mais barata e auditável.

**O que faria reconsiderar:** uma pergunta que exigisse consultas em sequência cuja segunda dependesse do resultado da primeira (por exemplo, buscar uma peça e, conforme o que voltasse, cruzar com outra fonte). Hoje cada intenção tem uma sequência fixa.

## 4. Riscos e limites desta arquitetura

- **Tudo foi medido com o `qwen2.5:7b` local**, que não é determinístico. Duas perguntas que dependem de exceção falham na leitura do manual ([rag.md](rag.md) §3).
- **O perfil que aprova não é o do domínio** (§2.6).
- **A raspagem validava mal o código da peça** (corrigido em 2026-10-18): o modelo lia 6% a 12% da página e inventava de 57% a 62% dos códigos, e as peças esgotadas vinham com o aviso do site, "Ooops, o estoque acabou", no campo de código. Hoje o código vem do endereço do link e é conferido contra o texto da página ([prompts.md](prompts.md) §5). **O que fica:** o filtro por nome (as palavras do pedido no nome da peça, [prompts.md](prompts.md) §5.4) não conhece sinônimo, e o leitor em código depende do formato do site da Chevrolet; o da Volkswagen não foi inspecionado.
- **O mapa de montadoras** (`MODELO_FABRICANTE`, em `src/nos.py`) é uma lista curta escrita pelo grupo de desenvolvimento; modelo fora dela gera a pergunta da montadora.
- **Manuais por ano exato:** um Fox 2016 a 2019 fica sem manual ([rag.md](rag.md) §2).
