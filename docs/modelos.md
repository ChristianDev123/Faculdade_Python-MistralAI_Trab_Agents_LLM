# 3. Análise de modelos

## 3.1 Os candidatos

**Eixos escolhidos, e por quê:** tool calling/saída estruturada (pré-requisito — sem
isso não há agente, já que o fluxo usa 3 ferramentas); custo por milhão de tokens
(há várias chamadas por execução: coleta, consulta, registro, apresentação);
multimídia (o usuário às vezes manda foto da peça antiga, ver 2.1.2.2). Janela de
contexto pesa pouco, porque o manual é consultado por recuperação (RAG), não
lido inteiro.

| Eixo | Mistral Small | GPT-OSS 120B (Groq) | Gemini 3.6 Flash |
|---|---|---|---|
| Tool calling / saída estruturada | Sim | Sim | Sim |
| Multimídia (foto da peça) | Sim | Não | Sim |
| Contexto | 256K | 131K | 1M |
| Custo entrada/saída por milhão de tokens (produção) | $0,15 / $0,60 | $0,15 / $0,60 | ~$0,75 / $3,75* |
| Onde roda | API Mistral | API Groq | API Google |

\* fontes de preço da Gemini 3.6 Flash divergem entre si ($0,75/$3,75 vs. $1,50/$7,50)
— conferir em ai.google.dev/gemini-api/docs/pricing antes de orçar produção de verdade.

## 3.2 A conta

Estimativa por execução (4 chamadas de modelo: coleta, consulta, registro,
apresentação; ~800 tokens de entrada e ~150 de saída por chamada), usando o preço
de produção do Mistral Small como referência:

800 tokens entrada × 4 chamadas × $0,15/1M = $0,00048
150 tokens saída × 4 chamadas × $0,60/1M = $0,00036
= $0,00084 por execução


- Custo por 100 execuções: ~$0,084 (~R$0,45)
- Custo estimado do semestre (~2.000 execuções entre testes e demos): ~$1,70 (~R$9)

A verificação e os testes do semestre rodam nos tiers gratuitos dos três provedores;
a conta acima estima o custo se o sistema fosse para produção.

## 3.3 A verificação mínima

5 casos do domínio, mesmo prompt (`temperature=0`), nos 3 candidatos:

| # | Caso | Mistral Small | GPT-OSS 120B (Groq) | Gemini 3.6 Flash |
|---|---|---|---|---|
| 1 | Simples (dados completos) | não testado¹ | ✅ não inventou código — pediu confirmação por VIN/manual | ❌ **inventou 4 códigos de peça** (GM, Fras-le, Cobreq, Bosch) sem nenhum dado de catálogo real |
| 2 | Motorização não informada | não testado¹ | ✅ perguntou | ✅ perguntou |
| 3 | Ano na fronteira de duas gerações | não testado¹ | ⚠️ perguntou a motorização, mas não citou a troca de geração | ✅ identificou a troca de geração (11ª→12ª) explicitamente |
| 4 | Peça descontinuada, com substituta | não testado¹ | ✅ informou a substituta corretamente | ✅ informou a substituta corretamente |
| 5 | Peça sem substituta | não testado¹ | ✅ disse que não encontrou, sem inventar | ✅ disse que não encontrou, sem inventar |

¹ Tier gratuito da Mistral (plano "Experiment") não ficou ativo a tempo da entrega, pendente. Decisão do 3.4 tomada com 2 dos
3 candidatos; a Mistral entra na comparação assim que validada.

**O achado que mais pesa:** no caso 1, sem nenhum dado de ferramenta simulado no
prompt, o GPT-OSS se recusou a chutar um código de peça, e o Gemini inventou quatro,
com nome de fabricante, como se tivesse consultado um catálogo real. É exatamente o
risco que o `case.md` já registrava (peça de segurança errada é risco real, não só
comercial).

## 3.4 A decisão

**GPT-OSS 120B (Groq)** O Gemini 3.6 Flash
fica descartado como padrão: o caso 1 mostrou que ele inventa código de peça quando
não tem dado real pra responder — incompatível com a regra do sistema de nunca
aproximar uma peça (2.1, "o que dá errado hoje").

**Mudaríamos de ideia** se: (a) a Mistral, uma vez validada, passar nos 5 casos sem
inventar dado — aí vence por custo; (b) o GPT-OSS, já com as ferramentas reais
plugadas (não mais simuladas no prompt), também começar a inventar código quando a
ferramenta retornar erro ou vazio — nesse caso nenhum dos três atende sem um prompt
mais restritivo, e isso vira o maior risco do 2.11.