# Especificação e Arquitetura de Memória — Agente de Manutenção Automotiva

Este documento detalha o funcionamento, as políticas de armazenamento, o orçamento de contexto e os procedimentos de expurgo/esquecimento da memória do **Agente Assistente de Manutenção Automotiva**.

\---

## 1\. Níveis de Memória do Sistema

|Nível|Curto Prazo|Longo Prazo|
|-|-|-|
|**O que é**|A janela de contexto da execução/sessão corrente do usuário.|O histórico acumulado e compartilhado entre múltiplas execuções do agente.|
|**Conteúdo no Case**|System prompt, objetivo da manutenção atual, histórico recente de mensagens da sessão, trechos recuperados de manuais e peças buscadas.|Dados de leituras e consultas de manuais em PDF, histórico de interações e dados extraídos via scraping de peças.|
|**Persistido como**|**Checkpoint de Sessão**: Assim que há a utilização de subagentes - Arquivo JSON/Texto local individual por sessão (`/sessions/{session\\\\\\\_id}.json`).|**Leitura de Manuais**: Tabelas relacionais em banco SQLite, **Interações de Usuário**: Arquivos de log/histórico individual (`/history/user\\\\\\\_{id}.json`).|
|**Lido**|Uma vez, no início do laço de execução da sessão atual.|Na inicialização do programa (busca por interações semelhantes anteriores) e por demanda a cada passo/ferramenta (busca semântica/por chave).|
|**Acesso**|Por ID da sessão atual (`session\\\\\\\_id`).|Por similaridade de embedding (vetorial/RAG), busca textual ou chave direta (`user\\\\\\\_id` / código da peça / modelo do veículo).|
|**Ciclo de vida**|Encerra com o fim da execução/sessão do usuário.|Acumula continuadamente até ser alterado ou expurgado por remoção.|

## 

## 2\. Orçamento da Janela de Contexto (Curto Prazo)

Para evitar estourar o teto de tokens do modelo (ex: limite de 8.192 tokens na janela ativa), a distribuição máxima das 5 fontes de contexto é configurada conforme a tabela abaixo:

|Fonte|Teto (Tokens)|Descrição no Domínio Automotivo|
|-|-|-|
|**System Prompt**|$1.000$|Diretrizes de conduta técnica, segurança mecânica e formato de saída.|
|**Objetivo do Usuário**|$500$|Descrição do problema ou requisição atual (ex: "Como trocar a correia dentada do Gol G5?").|
|**Trajetória / Histórico**|$2.500$|Mensagens recentes da conversa e histórico de ferramentas invocadas na sessão.|
|**Trechos de Manuais (PDF)**|$1.000$|Fragmentos técnicos recuperados do manual via SQLite/RAG.|
|**Memória de Longo Prazo / Peças**|$1.500$|Informações recuperadas de interações semelhantes passadas e cotação de peças (scraping).|
|**TOTAL MÁXIMO**|**$6.500$**|**Margem de $1692$ tokens reservada para a geração do modelo.**|

### 

### Política de Descarte (Estouro de Janela)



Se a soma dos tokens ultrapassar o limite de $8.000$ tokens:

1. **Primeiro descarte:** Truncamento do histórico antigo da **Trajetória** da sessão atual, preservando sempre o `System Prompt`, o `Objetivo` inicial e as últimas interações do usuário.



## 3\. Estrutura da Memória de Longo Prazo e Políticas de Escrita

### 3.1 As Três Memórias no Case

|Tipo|O que guarda no case|Estrutura|Como é recuperada|
|-|-|-|-|
|**Episódica**|Interações anteriores de usuários com problemas semelhantes (ex: "qual o código de disco de freio do Corolla 2020").|Arquivos `.jsonl` indexados vetorialmente por embeddings.|Por busca de similaridade no início da execução da aplicação.|
|**Semântica**|Mapeamento de termos técnicos, códigos de peças, compatibilidades e dados extraídos dos PDFs.|Tabelas no banco SQLite (`SQLite`).|Por consulta SQL direta, chave-valor (`part\\\\\\\_number`, `veiculo\\\\\\\_id`) ou busca FTS (*Full-Text Search*).|
|**Procedural**|Guias passo a passo padronizados de manutenção e regras fixas de segurança.|Texto plano injetado dinamicamente no `System Prompt`.|Injeção fixa no contexto de inicialização do agente.|

### 3.2 O que NÃO entra na memória

* **Credenciais e Dados Sensíveis:** Senhas, tokens de API, dados bancários de compra de peças e dados pessoais do usuário (CPF, telefone) são omitidos/mascarados antes de salvar os arquivos.
* **Resultados Instáveis de Web Scraping:** Preços e disponibilidades de peças do scraping **não** são gravados na memória semântica permanente, apenas no log temporário da sessão (pois mudam constantemente e tornam-se obsoletos rapidamente).
* **Arquivos PDF Brutos:** O agente armazena no SQLite apenas os trechos processados, índices e metadados, e nunca os binários dos manuais dentro do histórico.

\---

## 4\. Especificação do Esquecimento (Contradição, Decaimento e Remoção)

### 4.1 Contradição (O fato mudou)

* **Cenário:** O manual antigo previa a troca de óleo a cada 10.000 km, mas uma atualização da montadora (novo PDF lido) alterou a recomendação para 7.500 km.
* **Regra de Desempate:** Toda entrada no SQLite e nos arquivos possui o campo `created\\\\\\\_at` (timestamp ISO-8601 UTC). O agente aplica a regra determinística `max(created\\\\\\\_at)`, priorizando o fato mais recente.
* **Registro de Descarte:** Quando uma contradição é detectada na leitura, o fato antigo é ignorado e um log de aviso é gerado (`\\\\\\\[WARN] Fato contraditório descartado em favor de registro mais recente: ID\\\\\\\_XXX`).

### 4.2 Decaimento (O fato envelheceu)

\*\* Não Se Aplica \*\*

## 4.3 Remoção (O titular solicitou expurgo dos dados)

Conforme especificado, o expurgo dos dados do usuário é realizado via **remoção direta e completa**.

#### Estruturas Afetadas:

1. **Arquivos de Interações de Usuário:** Exclusão do arquivo `/history/user\\\\\\\_{id}.jsonl`.
2. **Sessões e Checkpoints:** Remoção dos arquivos em `/sessions/` vinculados ao `user\\\\\\\_id`.
3. **Base SQLite:** Exclusão de registros de interações vinculados ao titular (`DELETE FROM interacoes WHERE user\\\\\\\_id = ...`).

#### Procedimento de Verificação Indeterminada (Auditoria de Expurgo):

Sempre que uma solicitação de remoção é concluída:

1. Executa-se o script de expurgo passando o `user\\\\\\\_id`.
2. É realizada uma varredura independente (*full scan*) que busca o `user\\\\\\\_id` em:

   * Todas as tabelas SQLite.
   * Todos os arquivos do diretório `/history/` e `/sessions/`.
   * Arquivos de log de ferramentas.
3. Se o número de correspondências for $0$, o sistema emite o certificado interno de exclusão concluída.

> \\\\\\\*\\\\\\\*Impacto no Sistema:\\\\\\\*\\\\\\\* A remoção de interações de um usuário não exige a reconstrução total do banco de manuais em SQLite, apenas a remoção das entradas específicas associadas ao titular e a invalidação dos índices de busca vetorial das interações afetadas.

```


