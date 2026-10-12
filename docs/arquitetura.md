# 2. Plano de Prompt Engineering

Este documento estabelece o planejamento, a arquitetura e a estratégia de validação dos prompts utilizados no sistema, separando a documentação estratégica do código-fonte dos prompts.

---

## 2.1 Documento de Raciocínio (`docs/prompts.md`)

A tabela abaixo detalha cada etapa do sistema em que o modelo de linguagem é chamado, especificando a técnica utilizada, a justificativa, o contrato estrito de saída e o critério de teste associado.

| Etapa | Técnica | Por que ela | Contrato de saída | Como é testada |
| :--- | :--- | :--- | :--- | :--- |
| **Triagem** | zero-shot + Chain of Thought | A classificação depende de regras de negócio e convenções de domínio específicas que o modelo pré-treinado não conhece nativamente. | JSON estrito contendo os campos: `pensamento`, `conteúdo` (Campo de resposta ao usuário) e `ação` (string enumerada de possíveis ações do sistema). Proibido texto livre fora do JSON. | 15 casos rotulados, com meta de $\ge 13$ acertos. |
| **Resposta do RAG** | Cadeia de pensamento (Chain-of-Thought) | O modelo precisa primeiro sintetizar os trechos recuperados para evitar alucinações e fundamentar a resposta estritamente no contexto fornecido. | JSON estruturado contendo: `pensamento`, `trecho original` e `resumo` | 10 perguntas de teste com gabarito de contexto, avaliadas por similaridade semântica e ausência de alucinação. |
| **Resposta da consulta em banco de dados relacional** | Cadeia de pensamento (Chain-of-Thought) | O modelo precisa identificar base de dados à consulta e executar operações solicitadas pelo usuário, isso tudo normalizando a query de acordo com a estrutura física das tabelas | JSON semi-estruturado dinâmicamente de acordo com a estrutura da base consultada ou a ter dados inseridos | 10 casos de linhas recuperadas manualmente, comparadas à extraídas pelo sistema
| **Extração de dados via WebScrapping** | Cadeia de pensamento (Chain-of-Thought) + Few-Shot | A etapa necessita solicitar ao registrador o link do webcatálogo, e identificar trechos dentro do html/markdown onde há os dados à serem incluídos em base local | - | Comparação manual dos dados extraídos com os dados disponibilizados em site

---

## 2.2 Organização dos Prompts em Arquivo (`src/prompts/`)
Com excessão de prompts para padronização de dados em json, a partir desta entrega, **nenhum prompt reside dentro do código Python em f-strings**. Todos os prompts foram migrados para arquivos individuais dentro de `src/prompts/`, garantindo versionamento, histórico de alterações via Git e carregamento dinâmico em tempo de execução.

### Estrutura de Arquivos Implementada:
```cmd
prompts/
├── leitor_manual_pdf
│   ├── leitor_manual_pdf_prompt.md
│   └── tool_call_leitura_pdf.md
├── orquestrador_system_prompt.md
├── registrador_system_prompt.md
├── system_prompt.py
└── webscrapper
    ├── geral.md
    ├── tool_scrapping.md
    └── tool_webcatalog.md
```
Cada execução do sistema agora registra obrigatoriamente no log inicial a versão e o hash/conteúdo do prompt em uso, conforme exigido pelas diretrizes de rastreabilidade.

---

## 2.3 Relatório da Regra da Frase (Otimização de Prompt)

> *“Se vocês apagarem uma frase do prompt e não souberem dizer o que ela impedia, ela não estava fazendo nada.”*

### Experimento realizado no prompt: `src/prompts/triagem.txt`

**Frase removida:** 

    ## Regra de Formatação de Resposta
    - NUNCA emita uma chamada de ferramenta (tool call) com o nome "json".
    - Quando a ação for "RESPONDER_USUARIO", envie a resposta como texto simples de mensagem contendo o JSON no corpo da resposta (content), e NÃO como uma chamada de função/ferramenta (tool call).

**O que aconteceu:** 
    
    O programa parou de funcionar. apresentando chamada à uma tool_call inexistente.

**Conclusão (A frase voltou?):** 
  **Sim, a frase voltou.** O teste provou que ela exercia uma trava essencial para o funcionamento do sistema, evitando delírio na orquestração de chamadas de ferramentas na etapa de orquestração de ações.


  # Arquitetura do sistema

> **Status do documento:** descrição baseada no fluxo e nos trechos de código conhecidos até 12/10/2026. Onde o código disponível não permite confirmar um comportamento, isso é declarado como **não confirmado** em vez de ser apresentado como implementado.
>
> **Legenda de alteração**
> - `[ADD: caminho]`: adicionar o trecho/documentação correspondente nesse arquivo.
> - `[CHECK: caminho]`: conferir o código real antes de afirmar o comportamento.
> - `[GAP]`: comportamento que precisa ser implementado ou decidido.

# 3. A arquitetura do agente,

## 3.1 Diagrama de execução

```text
                         ┌──────────────────────────────┐
                         │ Pessoa usuária               │
                         │ pergunta em texto livre      │
                         └──────────────┬───────────────┘
                                        │
                                        v
                         ┌──────────────────────────────┐
                         │ Orquestrador                 │
                         │ mantém lista de mensagens    │
                         │ limite externo: 10 iterações │
                         └──────────────┬───────────────┘
                                        │
                                        v
                         ┌──────────────────────────────┐
                         │ Modelo                        │
                         │ decide: responder, pedir dado │
                         │ ou emitir tool_call           │
                         └──────────────┬───────────────┘
                                        │
                   ┌────────────────────┴─────────────────────┐
                   │                                          │
          resposta sem ferramenta                     response.tool_calls
                   │                                          │
                   v                                          v
       ┌────────────────────────┐                ┌──────────────────────────┐
       │ Interpretar JSON       │                │ Código despacha a chamada│
       │ e campo `acao`         │                │ por tool_calls_func_link │
       └───────────┬────────────┘                └────────────┬─────────────┘
                   │                                          │
          ┌────────┴─────────┐                                v
          │                  │                   ┌──────────────────────────┐
          v                  v                   │ Ferramentas               │
 `RESPONDER_USUARIO`   outra ação/JSON            │                          │
          │            sem tool_call              │ get_all_table_names      │
          v                  │                   │ rescue_db_data            │
  ┌────────────────┐         │                   │ insert_db_question        │
  │ Exibir resposta│         │                   │ read_manual_pdf           │
  │ e aguardar     │         │                   │ execute_scrapping         │
  │ próximo input  │         │                   └────────────┬─────────────┘
  └────────────────┘         │                                │
                             │                                v
                             │                   ┌──────────────────────────┐
                             │                   │ Resultado da ferramenta  │
                             │                   │ é anexado como mensagem  │
                             │                   │ `role=tool`               │
                             │                   └────────────┬─────────────┘
                             │                                │
                             └──────────────┬─────────────────┘
                                            │
                                            v
                              ┌──────────────────────────────┐
                              │ Próxima chamada ao modelo    │
                              │ se houver iteração disponível│
                              └──────────────┬───────────────┘
                                             │
                           ┌─────────────────┴────────────────┐
                           │                                  │
                           v                                  v
                limite/condição de parada              novo ciclo do modelo
                           │
                           v
                ┌─────────────────────────────┐
                │ Encerrar ou retornar estado │
                │ final ao chamador           │
                └─────────────────────────────┘


 Subfluxo da ferramenta read_manual_pdf:

       pergunta técnica
              │
              v
    ┌───────────────────────────┐
    │ LeitorManualPDF           │
    │ get_pdf_filename          │
    │ read_pdf_pages             │
    └─────────────┬─────────────┘
                  │
                  v
    ┌───────────────────────────┐       ┌───────────────────────────┐
    │ PDF / PyPDFLoader         │──────>│ Divisão em chunks de 800  │
    └───────────────────────────┘       └─────────────┬─────────────┘
                                                      │
                                                      v
                                         ┌───────────────────────────┐
                                         │ ChromaDB persistente      │
                                         │ databases/chroma_db       │
                                         │ coleção por manual        │
                                         │ upsert + busca semântica  │
                                         │ top-5 resultados          │
                                         └───────────────────────────┘
```

## 3.2 As Seis Perguntas

### 3.2.1 Ferramentas: função, efeito e reversibilidade

A tabela descreve o contrato aparente a partir dos nomes e do fluxo conhecido. O efeito real deve ser confirmado nas implementações.

| Ferramenta | Responsabilidade | Leitura/escrita | Reversibilidade |
|---|---|---|---|
| `get_all_table_names` | Listar as tabelas/bases disponíveis para orientar a consulta | Leitura | Reversível/não mutável |
| `rescue_db_data` | Recuperar registros da base de dados para responder à dúvida | Leitura | Reversível/não mutável |
| `insert_db_question` | Registrar uma pergunta ou retorno associado à consulta técnica | Escrita | Não confirmado; pode exigir exclusão/compensação |
| `read_manual_pdf` | Acionar a leitura/recuperação de informação de manual PDF | Leitura do conteúdo; pode envolver escrita no índice | Leitura é não mutável; indexação altera o índice |
| `execute_scrapping` | Obter informações externas de peças e compatibilidade | Leitura externa; efeitos colaterais do site não confirmados | Não mutável ao usuário/agente, mas reversível |
| `get_pdf_filename` | Localizar/selecionar o nome do PDF a consultar | Leitura | Reversível/não mutável |
| `read_pdf_pages` | Ler páginas/trechos do manual e apoiar a recuperação semântica | Leitura e, se indexar conteúdo, escrita no ChromaDB | Leitura não mutável; `upsert` é uma escrita repetível, mas altera o índice |

### 3.2.2 O laço

O orquestrador executa um laço limitado por `range(10)`. Em cada volta, a sequência conhecida é:

1. Chamar o modelo com a lista atual de mensagens, o formato JSON esperado e as ferramentas disponíveis.
2. Se a resposta contiver `response.tool_calls`, iterar pelas chamadas solicitadas pelo modelo.
3. Para cada chamada, localizar a função em `tool_calls_func_link`, decodificar os argumentos JSON e invocar a função conforme sua assinatura.
4. Anexar o resultado ao histórico como mensagem com papel `tool`.
5. Fazer outra chamada ao modelo, desde que ainda haja uma iteração disponível e o fluxo não tenha encerrado.
6. Se não houver chamada de ferramenta, interpretar o JSON de resposta. A resposta ao usuário só é considerada final quando o código reconhece a ação de resposta, conhecida como `RESPONDER_USUARIO`.

**O que faz a volta seguinte existir:** uma chamada de ferramenta foi solicitada e processada, e o orquestrador continua o ciclo para que o modelo possa interpretar o resultado. A simples presença de um campo textual como `CHAMAR_SUBAGENTE` não executa uma ferramenta por si só. Para ativar um subagente, o modelo precisa emitir um `tool_call` que o código reconheça e despache.

### 3.2.3 Estado: objetos explícitos e lista de mensagens

#### 3.2.3.1 Estado explícito conhecido

- Configuração do orquestrador: formato JSON esperado, ferramentas e mapeamento `tool_calls_func_link`.
- Contador do laço externo: limitado por `range(10)`.
- Componentes do leitor de PDF: coleção ChromaDB associada ao manual e diretório persistente `databases/chroma_db`.
- Dados e resultados retornados pelas funções, incluindo resultados das consultas a banco, manual e scraping.

#### 3.2.3.2 Estado mantido na lista de mensagens

A lista `messages` representa o histórico de interação enviado ao modelo. Ela pode conter:

- mensagens de sistema/instruções;
- mensagens da pessoa usuária;
- mensagens do assistente;
- chamadas de ferramenta emitidas pelo assistente;
- resultados das ferramentas, anexados com `role="tool"`.

O histórico é parte do estado operacional da conversa, mas não substitui variáveis explícitas de controle. Informações como número de passos restantes, prazo máximo, ferramenta já tentada, estado de aprovação e motivo final deveriam ser registradas explicitamente se o sistema precisar garantir esses comportamentos.

### 3.2.4 Orçamento e garantias de término

| Limite | Situação conhecida | Consequência |
|---|---|---|
| Iterações do orquestrador | `range(10)` | Limita o número de voltas do laço externo, conforme a unidade efetiva do código |
| Tempo total da execução | Não confirmado | Sem timeout global, uma chamada externa bloqueada pode impedir o término |
| Timeout de cada chamada ao modelo | Não confirmado | Deve ser definido/verificado no cliente e na configuração da API |
| Timeout de banco e scraping | Não confirmado | Uma função bloqueada pode impedir o orquestrador de avançar |
| Iterações do leitor de PDF | Sem limite explícito conhecido | Pode repetir chamadas e não terminar |
| Tamanho do histórico/tokens | Métricas de tokens já foram usadas no projeto, mas teto de execução não confirmado | O custo e o tamanho do contexto podem crescer sem política de corte |

O limite de dez iterações é uma proteção parcial, não uma garantia completa de término: ele só funciona se cada chamada de modelo e cada ferramenta retornar o controle ao laço. Para garantir término, definir também um prazo global monotônico, timeouts por operação e um limite para o laço do leitor de PDF. Ao atingir qualquer teto, encerrar com um motivo explícito, registrar o evento e retornar uma resposta controlada.

`[ADD: implementação do orquestrador]` Adicionar controle de prazo global e timeout por ferramenta, se ainda não existirem.
`[ADD: implementação do leitor de PDF]` Adicionar contador máximo de chamadas e condição de saída para repetição de `get_pdf_filename`.

### 3.2.5 Término: taxonomia dos motivos

A taxonomia abaixo é a recomendada para tornar os encerramentos observáveis. Nem todos os motivos estão comprovados como estados implementados hoje.

| Motivo | Classificação | Situação |
|---|---|---|
| `RESPONDER_USUARIO` | Encerramento normal: resposta entregue | Ação conhecida no fluxo |
| `LIMITE_ITERACOES` | Encerramento por orçamento de passos | Há limite externo de dez iterações; confirmar se ele retorna esse motivo explicitamente |
| `TIMEOUT_GLOBAL` | Encerramento por orçamento de tempo | Não confirmado |
| `TIMEOUT_FERRAMENTA` | Ferramenta excedeu o tempo permitido | Não confirmado |
| `ERRO_MODELO` | Erro na chamada ao modelo/API | O tratamento específico precisa ser conferido |
| `ERRO_FERRAMENTA` | Função chamada falhou ou argumentos não puderam ser processados | O tratamento específico precisa ser conferido |
| `TOOL_CALL_DESCONHECIDA` | Nome da ferramenta não está no mapeamento | Confirmar se há tratamento explícito |
| `JSON_INVALIDO` | Resposta ou argumentos não puderam ser decodificados/validados | Confirmar se há tratamento explícito |
| `ACAO_NAO_TRATADA` | O modelo retornou uma ação que o código não executa, por exemplo um `CHAMAR_SUBAGENTE` textual sem `tool_call` | Problema já observado no fluxo anterior |
| `CANCELADO` | Execução cancelada por código ou pessoa | Não confirmado |
| `ESGOTAMENTO_DE_TENTATIVAS_PDF` | Leitor de PDF atingiu o limite de tentativas | Não implementado/conhecido |
| `FALHA_INTERNA` | Erro inesperado não classificado | Confirmar o tratamento global |

Para cada encerramento, registrar pelo menos: `motivo`, etapa/ferramenta atual, contador de iterações, duração e mensagem de erro sanitizada. A taxonomia só deve ser descrita como implementada depois de existir no código e haver teste para cada ramo.

`[ADD: classe/retorno do orquestrador]` Padronizar os motivos de encerramento e garantir que todos os caminhos retornem um estado final, em vez de simplesmente sair do laço.

### 3.2.6 O humano: entrada, perfil, espera e silêncio

#### 3.2.6.1 Onde a pessoa entra hoje

1. Envia a dúvida inicial em texto livre.
2. Responde às perguntas de coleta de dados do veículo, uma informação por vez.
3. Recebe a resposta final do assistente e pode enviar outra mensagem. Há referência a um `input()` após a resposta.

O perfil chamado é a própria pessoa usuária, que conhece a dúvida e os dados do veículo. Não há evidência conhecida de uma etapa distinta que solicite aprovação de especialista, mecânico ou administrador antes de uma ação.

#### 3.2.6.2 Aprovação humana

Não foi identificado, nos trechos conhecidos, um ponto de aprovação humana implementado. Portanto, o diagrama não deve sugerir que exista uma pausa de aprovação antes de consultar bases, ler PDFs ou executar scraping.

`[GAP]` Se for adicionada aprovação humana, especificar explicitamente:
- qual ação exige aprovação e por quê;
- quem pode aprovar ou rejeitar;
- como a execução fica suspensa e como é retomada;
- o prazo máximo de espera;
- o comportamento no silêncio ou timeout;
- o comportamento em caso de rejeição ou cancelamento.

**Política recomendada para silêncio:** não manter a execução suspensa indefinidamente. Ao vencer o prazo, registrar `APROVACAO_EXPIRADA`, não executar a ação pendente e devolver um estado que permita retomar ou encerrar a conversa. Para ações que não possam ocorrer sem aprovação, a ausência de resposta deve equivaler a **não aprovado**, nunca a aprovação implícita.

## 3.3 Defesa do nível de autonomia

### 3.3.1 Classificação atual: roteador com uso de ferramentas, condicionado à validação em execução

A arquitetura conhecida tem um orquestrador que encaminha a solicitação para ferramentas distintas — consulta de tabelas, recuperação de registros, leitura de manual e scraping — e devolve os resultados ao modelo para uma nova decisão. Isso é mais que um workflow estritamente fixo **se** a escolha da próxima ferramenta for realmente feita pelo modelo durante a execução e variar conforme a pergunta e os resultados.

A decisão concreta a demonstrar é:

> **Depois de receber a pergunta e os dados recuperados do banco, o modelo decide se já consegue responder, se precisa consultar o manual PDF ou se precisa executar scraping para identificar/validar uma peça.**

Essa escolha precisa aparecer em um teste executável, com logs das chamadas de ferramenta. Uma resposta textual dizendo `CHAMAR_SUBAGENTE`, sem `tool_call` correspondente, não demonstra autonomia: é apenas texto que o código pode não executar.

### 3.3.2 Por que um workflow de nível inferior pode não bastar

Um workflow fixo seria suficiente se as etapas e os caminhos fossem predeterminados por regras de código, por exemplo: consultar sempre a base, depois sempre o manual e por fim sempre o scraping. O roteador só se justifica se a seleção entre essas ferramentas depender do conteúdo da pergunta, dos dados já coletados e dos resultados retornados — situações em que o modelo escolhe dinamicamente o próximo passo.

Não há evidência suficiente para classificar o sistema como um agente plenamente autônomo com planejamento aberto. O fluxo tem um conjunto conhecido de ferramentas e um teto externo de dez iterações. Assim, **roteador** é a classificação mais conservadora compatível com o desenho descrito, desde que a decisão dinâmica seja comprovada. Se o teste mostrar que o modelo não escolhe efetivamente o caminho e o código executa sempre uma sequência fixa, a classificação correta é **workflow**.
