# Arquitetura do agente

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

| Limite | Situação Atual | Consequência |
|---|---|---|
| Iterações do orquestrador | `range(10)` | Limita o número de voltas do laço externo, conforme a unidade efetiva do código |
| Iterações do leitor de PDF | 10 páginas extraídas via Chroma | Limita quantidade de páginas extraídas do pdf com o objetivo de determinar uma resposta suscinta ao usuário |
| Tamanho do histórico/tokens | Métricas de tokens já foram usadas no projeto, tendo como teto ~800 tokens por execução de agentes e subagente e uma média de 150 tokens por saída, tendo saída limitada no máximo em 400 tokens | O custo e o tamanho do contexto podem crescer sem política de corte |

### 3.2.5 Término: taxonomia dos motivos

A taxonomia abaixo é a recomendada para tornar os encerramentos observáveis. Nem todos os motivos estão comprovados como estados implementados hoje.

| Motivo | Classificação | Situação |
|---|---|---|
| `RESPONDER_USUARIO` | Encerramento normal: resposta entregue | Ação conhecida no fluxo |
| `LIMITE_ITERACOES` | Encerramento por orçamento de passos | Há limite externo de dez iterações; confirmar se ele retorna esse motivo explicitamente |
| `ERRO_SISTEMICO` | Erro em qualquer uma das ferramentas disponíveis ao orquestrador | O tratamento específico precisa ser conferido |

### 3.2.6 O humano: entrada, perfil, espera e silêncio

#### 3.2.6.1 Onde a pessoa entra hoje

1. Envia a dúvida inicial em texto livre.
2. Responde às perguntas de coleta de dados do veículo, uma informação por vez.
3. Recebe a resposta final do assistente e pode enviar outra mensagem. Há referência a um `input()` após a resposta.

O perfil chamado é a própria pessoa usuária, que conhece a dúvida e os dados do veículo. Não há evidência conhecida de uma etapa distinta que solicite aprovação de especialista, mecânico ou administrador antes de uma ação.

#### 3.2.6.2 Aprovação humana

Nenhuma das decisões que o sistema toma até o momento necessita de uma aprovação humana para prosseguimento da ação.

## 3.3 Defesa do nível de autonomia

### 3.3.1 Classificação atual: roteador com uso de ferramentas, condicionado à validação em execução
A classificação atual do projeto é um roteador.

Depois de receber a pergunta e os dados recuperados do banco, o modelo decide se já consegue responder, se precisa consultar o manual PDF ou se precisa executar scraping para identificar/validar uma peça.

As ações de decisão do modelo podem ser vistas no workflow do projeto nos pontos de escolhas entre resgatar informações em banco de dados, realizar leitura de pdf, realizar extração via webscrapping e armazenar dados em banco de dados em uma tabela específica, não pré-determinada. 


### 3.3.2 Por que um workflow de nível inferior pode não bastar

Um workflow fixo seria suficiente se as etapas e os caminhos fossem predeterminados por regras de código, por exemplo: consultar sempre a base, depois sempre o manual e por fim sempre o scraping. O roteador só se justifica se a seleção entre essas ferramentas depender do conteúdo da pergunta, dos dados já coletados e dos resultados retornados — situações em que o modelo escolhe dinamicamente o próximo passo.

