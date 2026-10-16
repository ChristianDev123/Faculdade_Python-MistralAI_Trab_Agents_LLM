# O grafo

Código: [src/grafo.py](../src/grafo.py) (montagem), [src/nos.py](../src/nos.py) (nós e rotas), [src/estado.py](../src/estado.py) (estado e reducers), [src/contrato.py](../src/contrato.py) (contratos Pydantic). Conferência: `python conferir_grafo.py`.

## 1. Decisão de projeto: roteador, e não agente

Antes, um laço livre deixava o modelo escolher a ferramenta a cada volta. Nos testes reais isso falhou de forma repetida: o modelo escrevia a tool call como texto JSON, respondia sem consultar, ou gastava voltas em ações inválidas. Hoje o modelo decide **só o que exige julgamento sobre texto livre**: qual é a intenção e quais dados do veículo o usuário já deu (nó `extrair`). Tudo o mais é regra em código, inclusive a memória (`lembrar`, `memorizar`) e o esquecimento (`esquecer`).

Isso responde à pergunta do §3.3 do enunciado: a decisão que só o modelo toma é classificar a intenção e extrair os dados do texto livre. O nível de autonomia é **roteador**; o laço livre foi removido porque nenhuma outra decisão precisava de modelo. Custo medido: um pedido de peça que já está na base usa **1** chamada ao modelo (antes, de 4 a 8).

## 2. Desenho

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

### Saída de `conferir_grafo.py`

Comando: `python conferir_grafo.py` (importa o mesmo objeto `grafo` que `src/main.py` executa).

```
NÓS
  __start__
  entrada
  extrair
  recusar
  perguntar
  consultar_base
  raspar
  aprovar_gravacao
  gravar
  ler_manual
  registrar_duvida
  lembrar
  memorizar
  confirmar_esquecimento
  esquecer
  emitir
  __end__

ARESTAS  (origem -> destino; [condicional] = o destino depende de uma regra)
  __start__ -> entrada
  aprovar_gravacao -> emitir  [condicional]
  aprovar_gravacao -> gravar  [condicional]
  confirmar_esquecimento -> emitir  [condicional]
  confirmar_esquecimento -> esquecer  [condicional]
  consultar_base -> emitir  [condicional]
  consultar_base -> ler_manual  [condicional]
  consultar_base -> raspar  [condicional]
  emitir -> __end__  [condicional]
  emitir -> memorizar  [condicional]
  entrada -> emitir  [condicional]
  entrada -> extrair  [condicional]
  entrada -> lembrar  [condicional]
  esquecer -> emitir
  extrair -> confirmar_esquecimento  [condicional]
  extrair -> consultar_base  [condicional]
  extrair -> emitir  [condicional]
  extrair -> perguntar  [condicional]
  extrair -> recusar  [condicional]
  gravar -> emitir
  lembrar -> extrair
  ler_manual -> emitir  [condicional]
  ler_manual -> registrar_duvida  [condicional]
  perguntar -> emitir
  raspar -> aprovar_gravacao  [condicional]
  raspar -> emitir  [condicional]
  recusar -> emitir
  registrar_duvida -> emitir
  memorizar -> __end__
```

O desenho e as duas listas coincidem. Se divergirem um dia, vale o código.

## 3. Nós

| Nó | Quem executa | Efeito no mundo |
|---|---|---|
| `entrada` | código | zera o que é por turno e conta o turno |
| `lembrar` | código | leitura: memória semântica (veículo do usuário) |
| `extrair` | **modelo** (schema Pydantic) | nenhum |
| `recusar`, `perguntar` | código | nenhum |
| `confirmar_esquecimento` | **humano** (`interrupt`) | pausa |
| `esquecer` | código | **apaga** os dados do titular (ver memoria.md) |
| `consultar_base` | código | leitura (SQLite; para dúvida de manual, a memória episódica) |
| `raspar` | modelo (extração da página) + web | leitura externa; **não grava** |
| `aprovar_gravacao` | **humano** (`interrupt`) | pausa |
| `gravar` | código | **escrita**, idempotente |
| `ler_manual` | busca textual (BM25) por código + modelo (resposta fundamentada nos 6 trechos); o PDF é escolhido por código a partir de modelo e ano | leitura |
| `registrar_duvida` | código | **escrita** (episódica), idempotente; só se a dúvida foi sanada |
| `emitir` | código | valida `Saida` e grava o log |
| `memorizar` | código | **escrita** (semântica), idempotente; só depois de `respondido` |

## 4. Padrões da Aula 05

| Padrão | Onde, no grafo | Por que ele, e não o de baixo | Condição de não uso |
|---|---|---|---|
| sequencial com portão | `consultar_base` (cache antes de fontes externas), `perguntar` (dados antes de agir), `aprovar_gravacao` (humano antes de gravar) | um portão que olha um campo vazio ou uma lista não precisa de modelo | — |
| *router* | `rota_pos_extracao` por `intencao` | rotas poucas e estáveis; a escolha da intenção é o único julgamento sobre texto livre | — |
| paralelização | não usado | o provedor local atende uma requisição por vez (o ganho de tempo seria nulo) e as fontes dependem uma da outra (a externa só vale se a base não responde) | usar se duas fontes independentes custassem pouco cada uma |
| orquestrador-trabalhador | não usado | as tarefas são fixas, não geradas em tempo de execução | quando o número de subtarefas depender da entrada |
| avaliador-otimizador | não usado | nenhuma etapa produz algo que um avaliador possa reprovar e refazer; a avaliação é o humano na gravação | se houver filtro de relevância com nova tentativa |
| agente (laço) | **removido** | nenhuma decisão restante exigia escolher ferramenta em tempo de execução | — |

## 5. Quem decide cada aresta condicional

Todas por **regra em código** (o degrau mais barato). O modelo escolhe **valores** que o código lê (`intencao`, `sanada`); nenhuma aresta é escolhida diretamente por ele. O schema com `Literal` garante uma rota válida, não a rota certa: por isso o prompt de extração tem 6 exemplos e foi testado em execução real.

| Aresta | Condição |
|---|---|
| `rota_pos_entrada` | `turno > MAX_TURNOS` → `emitir`; turno 1 → `lembrar`; senão `extrair` |
| `rota_pos_extracao` | erro → `emitir`; `ESQUECER` → `confirmar_esquecimento`; `FORA_DO_ESCOPO` → `recusar`; campo obrigatório vazio → `perguntar`; completo → `consultar_base` |
| `rota_pos_base` | erro ou linhas encontradas → `emitir`; senão `PECA` → `raspar`, `MANUAL` → `ler_manual` |
| `rota_pos_raspagem` | sem erro e com candidatas → `aprovar_gravacao`; senão `emitir` |
| `rota_pos_aprovacao` | `decisao == aprovar` → `gravar`; senão `emitir` |
| `rota_pos_manual` | sem erro e `sanada` → `registrar_duvida`; senão `emitir` |
| `rota_pos_confirmacao` | `decisao == confirmar` → `esquecer`; senão `emitir` |
| `rota_pos_emissao` | `motivo_termino == respondido` → `memorizar`; qualquer outro → fim |

Campos obrigatórios: `PECA` exige modelo, ano, motorização, montadora e nome da peça; `MANUAL` exige modelo, ano e a dúvida.

## 6. O estado

| Campo | Tipo | Quem **escreve** | Quem **lê** | Reducer, e por quê |
|---|---|---|---|---|
| `mensagens` | lista de mensagens | `entrada` (via CLI), `emitir` | `extrair` | `add_messages`: acumula só o texto da conversa |
| `turno` | int | `entrada` | `entrada`, rotas | sobrescreve (um só escritor) |
| `passos` | lista | nós com modelo | `emitir` (log) | `acumular`: soma, `entrada` zera a cada turno |
| `intencao` | texto | `extrair` | rotas | `manter_se_definida`: `INDEFINIDA` não apaga `PECA`/`MANUAL` |
| `veiculo` | dict | `lembrar` (do que a memória guarda), `extrair` | consulta, raspagem, manual | `mesclar`: valor novo não nulo vence; nulo nunca apaga; `LIMPAR` apaga de propósito (outro modelo de carro descarta ano e motorização do anterior) |
| `nome_peca`, `duvida` | texto | `extrair` | consulta, raspagem, manual | `ultimo_nao_nulo` |
| `avisos` | lista | `extrair` | `emitir` | `acumular` |
| `tentativas_pergunta` | dict | `perguntar` | `perguntar` | `somar_por_chave` |
| `consulta`, `candidatas`, `gravadas`, `leitura`, `registro`, `pergunta`, `erro` | vários | um nó cada (`candidatas` também o humano, editando) | rotas e `emitir` | sobrescreve; `entrada` zera |
| `aprovacao` | dict | `raspar` (carimbo), `aprovar_gravacao` (decisão) | rotas, `gravar` | sobrescreve; sequenciais, nunca no mesmo passo |
| `evidencias` | lista | consulta, raspagem, gravação, manual | `emitir` | `acumular` |
| `desvio` | texto | `entrada`, `recusar`, `perguntar` | `emitir` | sobrescreve; ramos exclusivos, nunca no mesmo passo |
| `saida`, `motivo_termino` | dict, texto | `emitir` | CLI e log | sobrescreve |
| `perfil_lembrado` | dict | `lembrar` | `emitir` (para declarar o que foi usado) | sobrescreve (um só escritor, no turno 1) |
| `campos_ditos` | lista | `extrair` | `emitir` | `uniao`: só cresce; distingue o que o usuário disse do que veio da memória |
| `memorizado` | dict | `memorizar` | log | sobrescreve; `entrada` zera |
| `esquecimento` | dict | `confirmar_esquecimento`, `esquecer` | rotas e `emitir` | sobrescreve; sequenciais, nunca no mesmo passo; `entrada` zera |

### O que NÃO está no estado

- **Na lista de mensagens:** só o texto da conversa (a fala do usuário e a resposta do sistema). Decisão, contador e identificador são campos próprios.
- **Derivado e não guardado:** o que ainda falta perguntar (calculado de `intencao` e `veiculo` a cada vez, para não haver duas fontes de verdade); o `thread_id` (vai na configuração da chamada); o carimbo de prompts (vai no log); o HTML da página e os resultados brutos das ferramentas (só entram objetos tipados).

## 7. Reducers: o que acontece sem eles

O grafo do sistema é sequencial, então a demonstração roda num grafo mínimo à parte, com dois nós paralelos escrevendo no mesmo campo: `python demo_reducer.py`. Saída real (langgraph 1.2.14):

```
--- 1. campo SEM reducer (padrão do framework)
   InvalidUpdateError: At key 'evidencias': Can receive only one value per step. Use an Annotated key to handle multiple values.
--- 2. reducer "o último que terminou vence"
   resultado: ['manual: achou 1 fonte']
--- 3. reducer operator.add (soma as listas)
   resultado: ['base_local: achou 1 fonte', 'manual: achou 1 fonte']
--- 4. reducer `acumular` do sistema
   resultado: ['base_local: achou 1 fonte', 'manual: achou 1 fonte']
```

**Achado:** nesta versão do framework, um campo **sem** reducer **não** é sobrescrito em silêncio: a execução falha alto com `InvalidUpdateError`. O trabalho de um ramo só desaparece sem erro quando alguém declara um reducer que descarta (caso 2), e é isso que o reducer errado causa. O enunciado descreve o primeiro comportamento como silencioso; em 1.2.14 não é.

## 8. O que o framework não deu

| Frente | O que o framework cobre | O que foi escrito |
|---|---|---|
| Motivo de término | o nó terminal diz que acabou, não por quê | `MotivoTermino` (contrato.py, 13 linhas) + `emitir` e `_montar_saida` (nos.py, ~75 linhas) |
| Detector de laço | `recursion_limit` limita, não detecta | o grafo **não tem ciclos**, então não há laço a detectar. A única repetição é entre turnos: `perguntar` desiste na 4ª vez que o mesmo campo faltaria (`desistiu_apos_3_perguntas`), ~4 linhas |
| Tetos | só o de super-passos (`recursion_limit`) | turnos por conversa (`MAX_TURNOS`), tempo por chamada (`LLM_TIMEOUT`, em `config.py`), prazo da aprovação (`PRAZO_APROVACAO_HORAS`). Teto de tokens por chamada está nas chamadas ao modelo. |
| Erro recuperável × fatal | nada | `erro.origem`: `sem_base` (recusa útil), `modelo` (`erro_modelo`) e `ferramenta` (`erro_ferramenta`), mapeados em `_montar_saida` |
| Checkpoint em disco | `SqliteSaver` cobre inteiro: `src/grafo.py`, `_criar_checkpointer` (3 linhas); não foi preciso escrever persistência | — |

## 9. A decisão que virou parâmetro

`recursion_limit`: o framework tem o padrão 25 e ele limita o dano, não o previne. O grafo não tem ciclos e uma execução usa no máximo 7 super-passos (entrada, extrair, consultar_base, raspar, aprovar_gravacao, gravar, emitir). Antes (laço livre), o teto de passos era uma decisão de projeto explícita (10 voltas); no framework ela vira um parâmetro com valor padrão que ninguém lê. Se o padrão da biblioteca mudasse numa atualização, o sistema não notaria: execuções presas gastariam o novo teto inteiro. Por isso o valor está declarado em `src/grafo.py` (`RECURSION_LIMIT = 25`) e passado em toda chamada de `src/main.py`, mesmo coincidindo com o padrão.

## 10. Desvios em relação ao desenho aprovado

- Dado que o usuário corrige no meio da conversa **não** vira pergunta de confirmação: vale o mais recente e a resposta declara a escolha ("Considerei ano = 2016 (você tinha dito 2015)"). Perguntar de novo criaria um laço (o usuário confirmaria e o valor continuaria divergindo do guardado).
- Existe a aresta `entrada -> emitir` (teto de turnos) e `recusar`/`perguntar` passam por `emitir`, que é o único nó que produz `Saida`.
- A regra "mesma pergunta 3 vezes" vive no nó `perguntar`, não na aresta.
- O estado ganhou o campo `desvio`.
- **Memória (item 5):** o grafo passou de 11 para 15 nós (`lembrar`, `memorizar`, `confirmar_esquecimento`, `esquecer`). Há **duas** paradas humanas (a segunda é a confirmação de apagar os dados, que é irreversível), e `emitir` deixou de ser o último nó: depois dele, uma resposta entregue passa por `memorizar`. Ver [memoria.md](memoria.md).
- O aviso de dado corrigido ficou "Considerei modelo = Onix (antes: Corsa)", sem dizer "você tinha dito", porque o valor antigo pode ter vindo da memória.
