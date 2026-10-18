# Model Card: Agente Assistente de Manutenção Automotiva

**Caminho do Arquivo:** `docs/model-card.md`  
**Status de Auditoria:** Parcialmente Validado (com Lacunas Declaradas)

\---

## 1\. Identificação

* **Nome do Sistema:** Agente Assistente de Manutenção e Consulta de Peças Automotivas
* **Versão:** `v0.1.0-alpha`
* **Data da Última Atualização:** 16 de Outubro de 2026
* **Responsáveis Nomeados:**

  * Christian Lima Santana
  * Marcelo Fernandes de Oliveira Junior
  * Gustavo Oliveira dos Santos

**Repositório:** https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLMEvidência

\---

## 2\. Finalidade

* **O que o agente decide/executa:**

  * Interpreta dúvidas técnicas de manutenção preventiva/corretiva veicular.
  * Realiza busca semântica em manuais técnicos de serviços e especificações de peças veiculares indexadas em banco vetorial.
  * Executa pesquisas complementares via web-scraping.
  * Retorna diagnósticos preliminares, especificações exatas de fluidos/peças e instruções de manutenção.
* **Para quem:** Mecânicos independentes e proprietários de veículos.
* **Usos fora de escopo (Proibidos):**

  * Emissão de ordens de compra diretas com execução financeira ou transação bancária sem aprovação prévia.
  * Diagnóstico crítico em tempo real de sistemas de segurança ativa (e.g., reprogramação de módulos ABS, Airbag ou ECU via porta OBD-II).
  * Validação de conformidade legal de modificações veiculares perante o DETRAN/CONTRAN.

### Evidência / Prova

* **Código:** https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/docs/prompts.md.

\---

## 3\. Autoridade e Limites de Ação

Esta seção detalha o que o agente tem capacidade técnica/operacional de executar e onde cada trava está implementada no código e na infraestrutura.

|Parâmetro de Autoridade|Descrição do Limite|Onde é Aplicado|Evidência no Repositório / Sistema|
|-|-|-|-|
|**Ações de Leitura/Consulta**|Consulta a PDFs/Manuais no ChromaDB e leituras via WebScrapping|Código + Ferramenta|https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/leitor\_manual\_pdf.py<br /><br />https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/webscrapper.py|
|**Ações de Escrita/Persistência**|Gravação de logs de histórico de conversas e telemetria|Código / Banco|https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/orquestrador.py (Linhas 97 - 101)|
|**Alteração em Banco de Dados**|Acesso ao SQLite restrito a `INSERT` de logs e `SELECT` de histórico. Sem comandos `DROP` / `DELETE` / `UPDATE`|Código|https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/registrador.py.|

\---

## 4\. Ferramentas e Integrações

Mapeamento completo das ferramentas disponíveis para o agente, com permissões, reversibilidade e integrações de acordo com a especificação técnica do sistema:

|Ferramenta|O que faz|Leitura/Escrita|Reversível?|Com quem se comunica|Origem / Código de Evidência|
|-|-|-|-|-|-|
|`executar\_webscrapping`|Realiza extração de todo um site de webcatálogo de uma determinada montadora|Escrita|—|Sites de Catálogos|https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/orquestrador.py (linhas 113 - 121)|
|`buscar\_manual`|Recupera trecho relevante do manual do veículo|Leitura|—|Manuais em PDF indexados|https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/orquestrador.py (linhas 103 - 111)|
|`registrar`|Grava no cache os modelos dados estruturados em json|Escrita|Sim (é cache, pode ser sobrescrito)|SQLite local|https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/orquestrador.py (linhas 82 - 95)|
|`resgatar`|Resgata dados à partir do cache local|Leitura|—|SQLite local|https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/orquestrador.py (linhas 74 - 80)|

### Evidência / Prova

* **Logs de Execução:** https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/tree/main/logs

\---

## 5\. Modelo e Provedor

* **Modelo Base:** `ollama/qwen2.5-coder:7b-instruct-q4\_K\_M` *(ou equivalente validado na esteira local via LM Studio)*
* **Provedor:** Local / On-Premise (executado via servidor Ollama / LM Studio no ecossistema Linux/WSL2 do desenvolvedor)
* **Região de Processamento:** Localhost (`127.0.0.1:11434`) — sem egresso de dados para provedores de nuvem internacionais.
* **Termos de Retenção e Treino:** **Zero Retention / Zero Data Training**. O processamento ocorre 100% em infraestrutura controlada, garantindo que os *prompts* e contextos dos manuais não alimentem modelos de terceiros.

### Evidência / Prova

* **Configuração:** https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/.env.example

\---

## 6\. Inventário de Dados Pessoais e LGPD

Mapeamento do fluxo de dados tratados pelo agente, finalidade técnica e conformidade com a LGPD (Lei nº 13.709/2018, Art. 7º).

|Ponto de Entrada / Local|Dado Pessoal Tratado|Finalidade|Base Legal (Art. 7º LGPD)|Prazo de Guarda|Avaliação de Minimização|
|-|-|-|-|-|-|
|**Índice Vetorial (ChromaDB)**|Nenhum (apenas manuais e dados técnicos de veículos)|Indexação de conhecimento técnico e RAG|N/A (Dados estritamente anônimos / técnicos)|Permanente (base de conhecimento)|**Conforme:** Não armazena PII (*Personally Identifiable Information*).|
|**Logs**|Prompt original, ID de usuário e metadados de execução|Auditoria de respostas, depuração e medição da acurácia do agente|Inciso IX (Interesse Legítimo) / Inciso II (Cumprimento de obrigação legal)|90 dias|**LACUNA:** O banco grava a string completa da mensagem do usuário sem aplicar técnica de sanitização/anonimização automática de PII (e.g. remoção de CPF/Telefone no log).|

### Evidência / Prova

* **Código:** https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/registrador.py.

\---

## 7\. Avaliação e Métricas do Modelo

* **Suíte de Avaliação:** `automotive\_agent\_eval\_suite\_v1` (Base de testes com *Golden Dataset* contendo 50 cenários de dúvidas mecânicas complexas).
* **Versão da Suíte:** `v1.2`
* **Resultados Agregados:**

  * **Acurácia Semântica de Recuperação (RAG Precision@3):** 88.4%
  * **Fidelidade da Resposta (Faithfulness via LLM-as-a-Judge):** 91.2%
  * **Taxa de Alucinação em Unidades/Torques de Peças:** < 2.5%
* **Concordância Juiz vs. Humano:** Coeficiente Cohen's Kappa ($\\kappa$) de **0.78** na avaliação comparativa de 20 casos de testes entre a nota atribuída pelo Juiz LLM e o especialista humano (Mecânico/Engenheiro).

### Evidência / Prova

* **Código/Dados:** Arquivo do Golden Dataset em `evals/golden\_dataset.json`.
* **Script de Execução:** `python -m evals.run\_evaluation` cujos resultados formatados estão salvos em `evals/reports/eval\_results\_v1.2.json`.

\---

## 8\. Limites Conhecidos e Modos de Falha

1. **OCR em Imagens de Manuais Antigos:** Baixa acurácia ao ler tabelas de torque em manuais digitalizados de veículos antigos (década de 1990/2000) com alta degradação de imagem.
2. **Conflito de Códigos de Peças Equivalentes:** Dificuldade em cruzar *Part Numbers* de mercado paralelo com peças originais de montadora (*OEM*) quando não presentes explicitamente na documentação indexada.
3. **Terminologia Regional:** O agente pode falhar em mapear gírias mecânicas regionais do Brasil (ex: "cinemática", "homocinética", "bolachão") para a nomenclatura oficial técnica de catálogo sem um pré-processamento de sinônimos.

### Evidência / Prova

* **Registros de Testes:** Casos de falha documentados e mapeados em `tests/failed\_cases\_log.md` (casos de teste `#14` e `#28`).

\---

## 9\. Riscos Aceitos

|Risco Mapeado|Razão da Aceitação|Medida Mitigadora que Limita o Risco|
|-|-|-|
|**Indicação incorreta de fluido/óleo**|Impossibilidade de cobrir 100% das variações de motores importados sem manual oficial.|Mensagem fixa obrigatória ao final de cada resposta recomendando a checagem da vareta/manual físico.|
|**Injeção de Prompt via Web Scraping**|O scraper pode extrair conteúdo malicioso ao resumir fóruns automotivos externos.|Sanitização de HTML e limitação de contexto a 1500 tokens por requisição scraper (`src/tools/web\_scraper.py`).|

\---

## 10\. Supervisão Humana e Desconexão (*Human-in-the-loop*)

* **Condições de Pausa:** Dúvidas técnicas em que o índice vetorial retorne score de similaridade inferior a $0.65$ (Score de incerteza).
* **Mecanismo de Aprovação:** O agente marca a resposta com o status `STATUS\_REQUIRES\_HUMAN\_REVIEW` e notifica o operador no console.
* **Tempo Médio de Resposta/Revisão:** Assíncrono (dependente da ação do operador humano).
* **Desconexão de Emergência (*Emergency Stop*):** Envio de comando via CLI `python src/main.py --shutdown` ou emissão do sinal `SIGTERM` no contêiner/processo.

### Evidência / Prova

* **Código:** https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/blob/main/src/orquestrador.py

\---

## 11\. Registro e Retenção de Logs

* **O que é Registrado:**

  * Timestamp da requisição.
  * *Hash* do Prompt de entrada do usuário.
  * Trechos de Manuais/Contexto recuperados no ChromaDB (IDs dos documentos).
  * Lista de ferramentas acionadas e parâmetros passados.
  * Resposta gerada e tempo total de inferência (latência em ms).
* **Tempo de Retenção:** 90 dias em arquivo local.
* **Controle de Acesso:** Acesso restrito ao perfil de Administrador do sistema/desenvolvedor responsável local.

### Evidência / Prova

* **Código/Configuração:** https://github.com/ChristianDev123/Faculdade\_Python-MistralAI\_Trab\_Agents\_LLM/tree/main/logs

\---

## 12\. Lacunas Mapeadas (Pendências de Governança)

|ID|Descrição da Lacuna|Risco Associado|Correção Proposta|Prioridade|
|-|-|-|-|-|
|**LACUNA-01**|**Trava de Execução de Shell apenas no Prompt:** O agente é instruído a não rodar códigos de sistema, mas não há isolamento via container (AppArmor/Docker sandbox).|Prompt Injection pode tentar manipular o agente para ler/escrever arquivos no SO host.|Implementar execução do serviço dentro de um container Docker não-root com *read-only filesystem*.|**ALTA**|
|**LACUNA-02**|**Ausência de Sanitização de PII nos Logs:** Mensagens do usuário são salvas integralmente no SQLite (`agent\_history.db`) sem remoção prévia de e-mails/telefones.|Não conformidade com o princípio da minimização da LGPD caso o usuário digite dados pessoais sensíveis.|Inserir middleware de regex/NER (e.g. Presidio) no `sqlite\_logger.py` para mascarar PIIs antes da gravação.|**MÉDIA**|
|**LACUNA-03**|**Falta de Rate-Limit Hardcoded nas ferramentas Web Scraper:** O limite de chamadas depende de timeout do HTTP e não de uma trava de cota global por minuto/hora.|Consumo excessivo de recursos de rede ou bloqueio de IP por *rate-limiting* de sites de autopeças.|Implementar decorador `@limits(calls=10, period=60)` no scraper (`src/tools/web\_scraper.py`).|**BAIXA**|



