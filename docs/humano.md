# Human-in-the-loop

Código: nó `aprovar_gravacao` em [src/nos.py](../src/nos.py), laço de CLI em [src/main.py](../src/main.py).

## 1. Onde o grafo para, e por qual critério

| Parada | Critério | Perfil chamado |
|---|---|---|
| **`aprovar_gravacao`** (`interrupt`) | **escrita de dados de terceiro, não verificados, no cache que alimenta respostas futuras.** O catálogo web devolve o que a busca dele entende, e o sistema já viu o risco de um dado errado virar resposta (um "não encontrei" gravado como se fosse resposta). | o usuário principal: o mecânico ou o balconista em nome dele |
| **`confirmar_esquecimento`** (`interrupt`) | **ação irreversível:** apagar os dados do titular (veículo lembrado, dúvidas, conversas salvas e logs). | o próprio titular, quem tem o `user_id` da conversa |
| fim de cada turno | espera a próxima mensagem de texto. Não é aprovação: o estado fica no checkpoint e a conversa continua com o mesmo `thread_id` | o usuário |

Não pedem aprovação: `memorizar` (grava o veículo; é reversível pela contradição e pela remoção), `registrar_duvida` (só grava se a dúvida foi sanada; é cache reversível por sobrescrita) e as leituras (base, manual, catálogo).

## 2. O que a pessoa vê, e o que ela devolve

O texto é montado por código com a ação exata, os argumentos e a consequência. Exemplo real (execução `logs/local/s4-fixa`, lista encurtada):

```
Vou GRAVAR 24 peça(s) na base local (tabela pecas_automoveis) para Onix 2018 1.0, vindas do catálogo da Chevrolet:
  1. Bujão do orifício do atuador da tampa traseira — código 52056750
  2. Forro do painel da caixa de roda traseira — código 52096890
  ...
  24. Suspensão traseira — código 94746824
Consequência: respostas futuras sobre este veículo passam a usar estes dados, sem nova consulta ao catálogo. Para desfazer, é preciso apagar as linhas da base.
Prazo: 24 h; depois disso nada é gravado.
Responda: aprovar | rejeitar | editar remover 3,5 | editar codigo 2 ABC123
```

| Resposta | Efeito |
|---|---|
| `aprovar` | grava a lista como veio |
| `rejeitar` | não grava; motivo `rejeitado_pelo_humano` |
| `editar remover 1,2,3,4,5` / `editar codigo 2 ABC123` | **aprova editando**: a lista corrigida é a que grava |

Na execução `s4-fixa`, a pessoa removeu 5 das 24 peças e o sistema gravou 19: a edição vale, não é carimbo.

## 3. A implementação, e por que ela depende do checkpoint

A pausa é `interrupt()` dentro do nó; a retomada é uma nova chamada com `Command(resume=...)`, e o valor devolvido vira o retorno do `interrupt`. Na retomada o nó roda de novo **desde o começo**, por isso nada com efeito colateral vem antes dele e o carimbo de tempo da pausa nasce no nó anterior (`raspar`), não aqui.

- **Checkpointer:** `SqliteSaver`, em `databases/checkpoints.sqlite` (não versionado). Grava em arquivo, então a aprovação pendente sobrevive ao fim do processo.
- **`thread_id`:** `<usuario>:<sessao>`. A mesma pessoa pode abrir duas conversas ao mesmo tempo: são duas sessões, dois `thread_id`, dois históricos separados. Duas mensagens ao mesmo `thread_id` ao mesmo tempo não são suportadas (a CLI atende uma por vez).
- **Limitação:** o checkpoint está num arquivo local; quem usar outra máquina não vê a pendência.

**Prova (execuções reais, `logs/local/sB-fixa`):** o processo terminou na pausa (sem resposta); em outro processo, com a mesma sessão, a aprovação pendente voltou na tela e a resposta `rejeitar` foi aplicada.

## 4. O que acontece se ninguém responder

- **Prazo:** `PRAZO_APROVACAO_HORAS`, padrão 24 h.
- **Caminho padrão ao vencer:** **não gravar**, avisar o usuário e terminar com motivo `aprovacao_expirada`. O silêncio nunca aprova.
- **Como é verificado:** no momento em que alguém retoma, o nó compara a hora atual com o carimbo da pausa. **Não há temporizador em segundo plano**: se ninguém voltar, a pendência fica no checkpoint até alguém retomar. Isso está declarado como limitação.

**Prova (execução real, `logs/local/sC-fixa`, com o prazo reduzido a 0,036 s por `PRAZO_APROVACAO_HORAS=0.00001`):** resposta `aprovar` chegou depois do prazo; saída `A aprovação não veio a tempo`, motivo `aprovacao_expirada`, e `pecas_automoveis` ficou com o mesmo número de linhas (31).

## 5. Aprovar duas vezes

A gravação usa chave de idempotência derivada do conteúdo (hash dos campos da linha), com `ja_existia` no retorno. Repetir a aprovação não cria linha.

**Prova (execuções reais):**

| Execução | Resultado | Linhas em `pecas_automoveis` |
|---|---|---|
| `s4-fixa`: aprovou editando (19 de 24) | `19 nova(s), 0 já existia(m)` | 7 → 26 |
| `sA-fixa`: nova conversa, aprovou as 24 | `5 nova(s), 19 já existia(m)` | 26 → 31 |
| consulta de duplicatas por (nome, código, modelo, ano, motorização) | 0 duplicadas | 31 |

As linhas estão em `logs/local/<sessao>/trajetoria.jsonl`. Esses logs registram o commit `99a7289`, mas o código desta funcionalidade ainda não estava commitado quando rodaram.

## 6. A segunda parada: confirmar antes de apagar os dados

Quando a pessoa pede "apague todos os meus dados", o grafo conta o que será apagado (só leitura), **para** e mostra a ação exata:

```
Vou APAGAR todos os dados do usuário usuario-teste-7f3a: 2 fato(s) sobre o veículo, 1 dúvida(s) registrada(s) e 1 item(ns) do índice, 4 conversa(s) salva(s) (esta inclusive) e 4 arquivo(s) de log.
Não dá para desfazer. Se ninguém confirmar, nada é apagado.
Responda: confirmar | cancelar
```

| Resposta | Efeito |
|---|---|
| `confirmar` | apaga (cobertura em [memoria.md](memoria.md)); motivo `esquecido` |
| `cancelar` | nada é apagado; motivo `esquecimento_recusado` |

- **Se ninguém responder:** nada é apagado. Aqui o silêncio **nunca** executa, e a pendência fica no checkpoint como a da gravação. Não há prazo: apagar dados não tem urgência que justifique agir sem resposta.
- **Aprovar duas vezes:** a remoção é idempotente por natureza (apagar o que já foi apagado devolve zero linhas), e a conversa em andamento é apagada depois, fora do grafo.
- **Prova (execuções reais):** em uma execução a pessoa cancelou e nada saiu; em outra confirmou, a varredura independente deu 0 ocorrências e a conversa seguinte voltou a perguntar o veículo.
