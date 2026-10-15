# Plano de Prompt Engineering

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
src/prompts/
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
