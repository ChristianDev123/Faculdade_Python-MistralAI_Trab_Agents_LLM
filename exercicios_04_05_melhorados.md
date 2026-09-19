# Exercícios 4 e 5

## Exercício 4 — O Case

**Setor:** varejo de autopeças / pós-venda automotivo.

**Problema em uma frase:** consumidores e mecânicos não confirmam no balcão se uma peça é compatível com o veículo específico (modelo, ano, motorização), gerando compra errada e atraso no conserto.

**Contexto**
- Hoje: balconista consulta catálogo impresso/sistema básico ou liga pro distribuidor; casos ambíguos levam dias.
- Regras do domínio: compatibilidade exige modelo + ano + motorização; peça descontinuada tem substituta indicada; existe original vs. paralela.
- Casos difíceis: motorização não informada, geração do modelo na fronteira do ano, peça sem substituta exata (o certo é dizer "não encontrei", nunca chutar — item de segurança).

**O que a indústria já faz (3 casos reais)**
1. Rede de autopeças usa GenAI no WhatsApp (LangGraph + Gemini), catálogo padronizado (ACES/PIES), respostas em 3–5s. Não divulga taxa de acerto nem quanto é resolvido sem humano. *[(Grid Dynamics)](https://www.griddynamics.com/blog/genai-search-agent-case-study)*
2. AWS publicou arquitetura de referência "Car Parts Assistant": agente com RAG (manuais) + API (compatibilidade). É demonstração, sem métrica de erro real de produção. *[(AWS ML Blog)](https://aws.amazon.com/pt/blogs/machine-learning/enhance-customer-support-with-amazon-bedrock-agents-by-integrating-enterprise-data-apis/)*
3. Moglix usa Vertex AI para casar comprador-fornecedor de peças de manutenção (MRO): reporta 4x de eficiência no sourcing. Não isola o que veio da IA do crescimento geral da plataforma. *[(catálogo Google Cloud)](https://blog.google/innovation-and-ai/infrastructure-and-cloud/google-cloud/gen-ai-business-use-cases/)*

**Usuários**

| Perfil | Quer | Sabe | Pode fazer |
|---|---|---|---|
| Consumidor | Confirmar peça sozinho | Modelo/ano; raramente a motorização | Consulta; não reserva |
| Mecânico (usuário principal) | Achar a peça certa rápido | Modelo/ano/motorização | Consulta **e** confirma a reserva (ação irreversível) |

**Interação:** chat, reativo, 2 a 6 trocas.
```
Mecânico: Pastilha de freio dianteira, Onix 2021.
Sistema:  Turbo ou aspirado?
Mecânico: Turbo.
Sistema:  ABC123 (original) ou XYZ789 (paralela)?
Mecânico: XYZ789.
Sistema:  Reservo 1 unidade — confirma?
Mecânico: Confirmo.
Sistema:  Pedido #4821 registrado.
```
O que falta informar de cara: a motorização — é o dado que o sistema precisa descobrir perguntando. É essa decisão que justifica um agente, não um formulário fixo.

**Ganhos** (formato pronto — troquem pelos números reais medidos pelo grupo)

| Eixo | Linha de base (medir) | Alvo | Volume |
|---|---|---|---|
| Tempo por tarefa | ex.: 11 min (cronometrar 10 casos reais) | 3 min | ~600 consultas/mês |
| Erro / retrabalho | ex.: 8% devolução (ERP, últimos 3 meses) | 3% | ~450 vendas/mês |

**Risco a resolver antes de começar:** acesso ao catálogo estruturado de compatibilidade — não garantido hoje.

---

## Exercício 5 — Arquitetura

**Entrada:** texto livre. ~65% peça, ~25% dúvida de manual, ~10% fora de escopo/incompleto.

**System prompt (resumo):** assistente de identificação de peças e consulta a manual técnico; não recomenda preço nem faz diagnóstico de defeito.

**Ferramentas**

| Ferramenta | Leitura/Escrita | Reversível? |
|---|---|---|
| `consultar_catalogo` | Leitura | — |
| `buscar_manual` (RAG) | Leitura | — |
| `reservar_peca` | Escrita | **Não** |
| `escalonar_humano` | Escrita | Sim |

**Orçamento:** catálogo até 3 chamadas · manual até 2 buscas / 5 chunks · avaliador até 3 rodadas · resposta até 300 tokens · teto geral: 8 passos / 30s por conversa.

**Fluxo**
```
1. ENTRADA                                                [—]
2. TRIAGEM (peça / manual / fora de escopo / incompleto)  [ROUTER]
3. CONSULTA CATÁLOGO                          [AGENTE, até 3 passos]
4. CONSULTA MANUAL (recuperação indexada)        [RAG, até 2 buscas]
5. PARECER (confere contra dados do veículo)  [AVALIADOR, 3 rodadas]
6. ESCALONAMENTO (se não resolver)                     [ESCRITA]
7. RESERVA (só após confirmação do usuário)  [ESCRITA — irreversível]
8. RETORNO                                                [—]
```

**Correção principal em relação à v0:** a etapa de manual era um agente lendo até 400 páginas sequencialmente — virou recuperação indexada (RAG), o que conecta direto com o Exercício 6.

**Justificativas curtas**
- *Router:* entrada heterogênea — precisa entender texto livre para saber pra onde mandar.
- *Catálogo como agente pequeno:* às vezes falta um dado (motorização) e precisa perguntar; com dados completos a resposta é determinística.
- *Manual como RAG:* ler o manual inteiro é caro e desnecessário quando dá pra indexar.
- *Avaliador:* errar peça de segurança tem custo alto — vale a rodada extra de checagem.
- *Reserva com confirmação humana:* decrementa estoque real, não é reversível sozinho.
