# Plano de observabilidade — agente de trocas

Grupo: Christian Lima Santana, Marcelo Fernandes de Oliveira Junior, Gustavo Oliveira dos Santos · Data: 2026-10-30

---

## 1. Perguntas

| Interessado | Pergunta | Decisão que a resposta muda |
|---|---|---|
| o negócio | Que fração das trocas o agente resolve sem atendente (aprova ou recusa), e quantas das aprovadas estavam fora da política? | manter, ampliar ou suspender a aprovação automática (a promessa é 60% resolvidas e menos de 1% fora da política) |
| a operação | Quantas conversas terminam sem desfecho, por orçamento esgotado ou erro, e em qual versão do agente? | investigar ou reverter a versão no ar |
| quem paga | Quantos tokens, e quantos passos do orçamento, gasta uma conversa, e quanto disso vai para conversas que não resolvem nada? | trocar de modelo, encurtar o contexto ou rever o limite de 6 passos |
| quem responde pelo sistema | A troca foi registrada só depois de consultar o pedido e a política, e só uma vez? | exigir aprovação humana em `registrar_troca` ou corrigir o prompt |

---

## 2. O *trace* de uma conversa

**Árvore de *spans* de uma conversa típica (troca aprovada):**

```text
invoke_agent  agente-de-trocas
├── chat <modelo>                    (o modelo pede consultar_pedido)
├── execute_tool consultar_pedido
├── chat <modelo>                    (o modelo pede consultar_politica)
├── execute_tool consultar_politica
├── chat <modelo>                    (o modelo decide aprovar e pede registrar_troca)
├── execute_tool registrar_troca
└── chat <modelo>                    (o modelo responde ao cliente)
```

Quatro voltas, abaixo do teto de 6 passos. Numa recusa o `registrar_troca` não aparece; numa conversa encaminhada ao atendente o último `chat` anuncia o encaminhamento.

**Atributos próprios na raiz:**

| Atributo | Valores possíveis | Para que serve |
|---|---|---|
| `troca.desfecho` | aprovada, recusada, encaminhada, orcamento_esgotado, erro | separa o que o agente resolveu do que passou ao humano ou parou no meio; é a base do "60% sem atendente" |
| `troca.dentro_da_politica` | sim, nao, desconhecido | calculado em código com a data da compra e o prazo devolvido por `consultar_politica`, não pelo modelo; é a base do "menos de 1% fora da política" |
| `troca.motivo_encaminhamento` | incerteza_do_modelo, politica_sem_regra, ferramenta_falhou, orcamento_esgotado | diz por que a conversa foi para o atendente, para saber se o problema é o modelo, a política ou a ferramenta |

---

## 3. Modos de falha

| Componente | Falha | Ruidosa ou silenciosa | Sinal que a torna visível |
|---|---|---|---|
| modelo | aprova uma troca fora do prazo (erra a conta dos dias ou ignora a data) | silenciosa: o agente responde, só que errado | `troca.desfecho = aprovada` com `troca.dentro_da_politica = nao` |
| `consultar_politica` | devolve vazio ou a política de outra categoria, e o agente decide com o prazo padrão de 30 dias | silenciosa | span `execute_tool consultar_politica` com resultado vazio, ou categoria diferente da do pedido; `troca.dentro_da_politica = desconhecido` |
| `registrar_troca` | é chamada duas vezes, ou sem `consultar_pedido` antes, e registra uma troca duplicada ou sem conferência | silenciosa: o sistema da loja aceita | mais de um span `execute_tool registrar_troca` com o mesmo número no *trace*, ou `registrar_troca` sem `consultar_pedido` antes dele |
| `consultar_pedido` | o sistema da loja está fora do ar ou estoura o tempo | ruidosa | span com status de erro e `troca.desfecho = erro` |

---

## 4. Objetivos

| Tipo | Indicador | Objetivo | Janela |
|---|---|---|---|
| operacional | conversas que terminam com desfecho (aprovada, recusada ou encaminhada), sem erro e sem esgotar o orçamento de 6 passos | ≥ 97% | 28 dias |
| a promessa da loja | trocas aprovadas fora da política, sobre o total de aprovadas | < 1% | 28 dias |

---

## 5. Alertas

| Alerta | Condição e limiar | SLO de origem | Quem é avisado | O que faz |
|---|---|---|---|---|
| custo | conversas terminadas por orçamento esgotado acima de 3% na última hora (cada uma gasta os 6 passos sem resolver nada) | operacional: ≥ 97% terminam com desfecho | o responsável pelo agente | compara a versão no ar (prompt e modelo) com a anterior e reverte se for o caso; confere se as ferramentas estão devolvendo vazio |
| degradação silenciosa | trocas aprovadas com `troca.dentro_da_politica = nao` acima de 1% das aprovadas nas últimas 24 h | a promessa: < 1% fora da política | o responsável pelo agente e o gestor do atendimento | passa o `registrar_troca` para aprovação humana até entender a causa e revisa uma amostra das aprovadas |
