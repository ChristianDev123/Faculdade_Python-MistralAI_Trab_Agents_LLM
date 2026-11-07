# Observabilidade

O plano declara o que se precisa saber sobre o sistema enquanto ele roda; a instrumentação em [src/rastreio.py](../src/rastreio.py) produz os sinais que o plano pede. Os números vêm das rodadas `evals/resultados/v2.0.0` e `v3.0.0` e são reproduzidos por `python -m evals.metricas`.

## 1. As perguntas

| Interessado | Pergunta | Decisão que a resposta muda |
|---|---|---|
| o negócio | Que fração das execuções entrega uma resposta com base, e quanto termina em recusa? | ampliar o corpus de manuais e os catálogos cadastrados |
| a operação | Quantas execuções param no meio, por limite ou erro, e em qual versão? | investigar ou reverter a versão no ar |
| quem paga | Quantos tokens custa uma execução? | manter o modelo, trocar de modelo ou reduzir o contexto |
| quem responde pelo sistema | O que foi gravado na base e na memória, com aprovação de quem, e o que foi bloqueado? | suspender a gravação e rever um controle |

## 2. O trace de uma execução

Uma execução é uma chamada ao grafo. A que para numa aprovação termina como `aguardando_humano`, e a retomada é outra execução da mesma conversa (`gen_ai.conversation.id`). Exemplo real de dúvida de manual (`python -m evals.ver_trace evals/resultados/v3.0.0/traces.jsonl manual_tanque`):

```text
invoke_agent assistente-automotivo
├── execute_tool lembrar_veiculo
├── chat qwen2.5:7b                  (extrair: intenção e dados do veículo)
├── execute_tool consultar_base      (memória episódica)
├── execute_tool buscar_manual       (BM25: devolve os ids dos trechos)
├── chat qwen2.5:7b                  (ler_manual: resposta com os trechos)
├── execute_tool registrar_duvida
└── execute_tool memorizar_veiculo
```

Os atributos `gen_ai.*` seguem as convenções GenAI do OpenTelemetry. Os atributos próprios da raiz:

| Atributo | Valores | Para que serve |
|---|---|---|
| `agente.termino` | os 12 motivos de `src/contrato.py`, mais `aguardando_humano` e `erro_nao_tratado` | separa a execução que terminou bem da que parou no meio; é o SLI da §6 |
| `agente.versao` | `VERSAO_SISTEMA`, em `src/trajetoria.py` | sem ela, nenhum número se compara entre versões |
| `agente.commit`, `agente.codigo_limpo`, `agente.prompts` | commit, se havia alteração sem commit, hash de cada prompt | a versão exata do código e dos prompts |
| `agente.entrada`, `agente.saida`, `agente.suficiencia` | o texto digitado e o objeto `Saida` | a decisão, reconstruível ([model-card.md](model-card.md) §11) |

Eventos: `no` (cada nó, com o que escreveu no estado), `pausa` (o texto mostrado à pessoa), `aprovacao_humana` (quem, quando e o que respondeu) e `leitura_rejeitada` (o controle 1 de [seguranca.md](seguranca.md)).

**Onde ver.** Cada conversa grava em `logs/<usuario>/<sessao>/trace.jsonl`, um span por linha, no formato JSON do OpenTelemetry. `python -m evals.ver_trace <arquivo>` mostra a árvore. Os traces das rodadas ficam em `evals/resultados/<rodada>/traces.jsonl`. Não há coletor nem painel: arquivo é o destino, porque o sistema roda localmente e o volume é pequeno.

## 3. Os modos de falha

| Componente | Falha | Ruidosa ou silenciosa | Sinal que a torna visível |
|---|---|---|---|
| modelo em `ler_manual` | responde com um valor que veio da pergunta, não do manual | silenciosa | evento `leitura_rejeitada` na raiz |
| modelo em `extrair` | classifica errado (diagnóstico vira pedido de dados) | silenciosa | nenhum em produção; só o caso `recusa_diagnostico` da suíte. **Lacuna** |
| `buscar_candidatas` | o site muda o layout, e a leitura cai na reserva com o modelo, lenta e incompleta | silenciosa | resultado do span `raspar_catalogo` com "pelo modelo", e o aviso de teto de tempo |
| conversa | pergunta 3 vezes sem obter o dado e desiste | silenciosa | `agente.termino = desistiu_apos_3_perguntas` |
| catálogo ou banco | indisponível | ruidosa | span `execute_tool` com status `ERROR` e `agente.termino = erro_ferramenta` |
| provedor do modelo | não responde a tempo | ruidosa | exceção no span `chat` e `agente.termino = erro_modelo` |

## 4. As métricas

Sobre as execuções da suíte (um caso pode ter várias), `qwen2.5:7b` local, contexto 8192. **São execuções de teste, não de produção:** a distribuição reflete a composição do dataset.

| | v2.0.0 | v3.0.0 |
|---|---|---|
| execuções | 50 | 50 |
| chamadas ao modelo | 59 | 59 |
| latência p50 | 3,3 s | 4,1 s |
| latência p95 | 19,9 s | 23,7 s |
| tokens por execução (entrada / saída) | 1.519 / 75 | 1.519 / 75 |
| custo por execução, preço de referência¹ | US$ 0,000273 | US$ 0,000273 |

¹ US$ 0,15 e 0,60 por milhão de tokens, o preço do modelo remoto em [modelos.md](modelos.md). Com o modelo local o custo por token é zero. Os tokens medidos são do modelo local.

A diferença de latência não é atribuída ao controle 1, que só compara textos: as rodadas rodaram em momentos diferentes, na mesma máquina, sem isolamento de carga.

| Motivo de término | v2.0.0 | v3.0.0 |
|---|---:|---:|
| `respondido` | 21 | 20 |
| `faltam_dados` | 10 | 10 |
| `sem_base` | 7 | 8 |
| `aguardando_humano` | 6 | 6 |
| `fora_do_escopo` | 3 | 3 |
| `desistiu_apos_3_perguntas` | 1 | 1 |
| `rejeitado_pelo_humano` | 1 | 1 |
| `aprovacao_expirada` | 1 | 1 |

| Ferramenta (chamadas, erros) | v2.0.0 | v3.0.0 |
|---|---:|---:|
| `lembrar_veiculo` | 38, 0 | 38, 0 |
| `consultar_base` | 31, 0 | 31, 0 |
| `memorizar_veiculo` | 21, 0 | 20, 0 |
| `buscar_manual` | 13, 0 | 13, 0 |
| `registrar_duvida` | 10, 0 | 9, 0 |
| `raspar_catalogo` | 8, 0 | 8, 0 |
| `gravar_pecas` | 3, 0 | 3, 0 |

**A taxa de erro é 0 porque a suíte não derruba nenhuma ferramenta:** o número não mostra que elas não falham.

## 5. As perguntas, respondidas

- **O negócio.** Na v3.0.0, de 44 execuções que terminaram, 20 entregaram resposta com base (45%), 8 terminaram em `sem_base` e 3 em fora do escopo; 10 pediram dados. **Lacuna:** a fração real do balcão só existe em produção, e a suíte tem recusas de propósito.
- **A operação.** 1 de 44 parou no meio, nas duas versões: o caso `coleta_desiste`, que existe para isso.
- **Quem paga.** 1.519 tokens de entrada e 75 de saída por execução, cerca de US$ 0,27 por mil execuções no preço de referência. A entrada pesa mais que a saída, então o corte de custo está no contexto.
- **Quem responde pelo sistema.** Na v3.0.0, `gravar_pecas` rodou 3 vezes e todas vieram depois de um evento `aprovacao_humana`. O controle 1 bloqueou 1 leitura (`leitura_rejeitada`, "número 999"), a que na v2.0.0 foi respondida e gravada na memória.

## 6. O SLO de qualidade

**SLI:** fração das execuções válidas que entregam um desfecho do contrato, calculada sobre o atributo `agente.termino` da raiz.
- **Válidas:** todas, menos `aguardando_humano`, porque a execução seguinte da conversa é que termina.
- **Boas:** as válidas fora da lista de ruins.
- **Ruins:** `desistiu_apos_3_perguntas`, `limite_turnos`, `erro_modelo`, `erro_ferramenta`, `erro_nao_tratado`.

**SLO:** ≥ 95% das execuções válidas são boas, em 7 dias.

| | v2.0.0 | v3.0.0 |
|---|---|---|
| valor medido | 97,7% (43 de 44) | 97,7% (43 de 44) |
| orçamento de erro consumido | 45% | 45% |

O orçamento é de 5% das execuções válidas, e a execução ruim consome 2,3 pontos. O objetivo foi fixado antes de medir. **A medição é de uma rodada da suíte, não de 7 dias de uso**, e a única execução ruim é um caso criado para isso.

O SLO cobre o que para no meio sem erro: `desistiu_apos_3_perguntas` não move a taxa de erro. **Ele não vê resposta errada:** um `respondido` falso conta como bom. Para isso existe a suíte, e o caso `manual_bateria` mostra um `respondido` que a expressão regular reprova.

## 7. Lacunas

- Sem alerta: os sinais existem, mas ninguém é avisado. A leitura é manual, por `evals.metricas`.
- Erro de classificação do `extrair` não tem sinal em execução (§3).
- As métricas não vêm de uso real: o sistema não está em produção.
