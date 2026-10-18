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

O texto é montado por código com a ação exata, os argumentos e a consequência. Exemplo real (cenário `pausa_edicao`, log `logs/exemplos/pausa_edicao/trajetoria.jsonl`, commit `30e8bee` (árvore limpa), 2026-10-16; lista encurtada):

```
Vou GRAVAR 26 peça(s) na base local (tabela pecas_automoveis) para Onix 2018 1.0, vindas do catálogo da Chevrolet:
  1. Moldura da guarnição do estribo da porta traseira — código 52056749
  2. Bujão do orifício do atuador da tampa traseira — código 52056750
  ...
  26. Porta traseira — código Ooops, o estoque acabou
Consequência: respostas futuras sobre este veículo passam a usar estes dados, sem nova consulta ao catálogo. Para desfazer, é preciso apagar as linhas da base.
Prazo: 24 h; depois disso nada é gravado.
Responda: aprovar | rejeitar | editar remover 3,5 | editar codigo 2 ABC123
```

| Resposta | Efeito |
|---|---|
| `aprovar` | grava a lista como veio |
| `rejeitar` | não grava; motivo `rejeitado_pelo_humano` |
| `editar remover 1,2,3,4,5` / `editar codigo 2 ABC123` | **aprova editando**: a lista corrigida é a que grava |

No mesmo cenário, a pessoa respondeu `editar remover 1,2,3,4,5`: das 26 candidatas, 5 saíram e o sistema gravou **21** (21 novas, nenhuma que já existisse): a edição vale, não é carimbo. O log registra a pausa com 26 candidatas e a resposta humana com 21.

**Um defeito que a aprovação deixou passar.** Nesta mesma lista, os itens 24 a 26 ("Mola traseira", "Suspensão traseira", "Porta traseira") mostram como código o texto "Ooops, o estoque acabou": é o aviso do site para peça esgotada, não um código. A pessoa roteirizada removeu só os itens 1 a 5, e os três foram gravados. A parada humana só protege se a informação mostrada for clara e se o sistema recusar o que não tem forma de código; hoje não recusa ([arquitetura.md](arquitetura.md) §4). A mesma lista, com os mesmos três itens, apareceu nos cenários `rejeitado` e `expirado`.

## 3. A implementação, e por que ela depende do checkpoint

A pausa é `interrupt()` dentro do nó; a retomada é uma nova chamada com `Command(resume=...)`, e o valor devolvido vira o retorno do `interrupt`. Na retomada o nó roda de novo **desde o começo**, por isso nada com efeito colateral vem antes dele e o carimbo de tempo da pausa nasce no nó anterior (`raspar`), não aqui.

- **Checkpointer:** `SqliteSaver`, em `databases/checkpoints.sqlite` (não versionado). Grava em arquivo, então a aprovação pendente sobrevive ao fim do processo.
- **`thread_id`:** `<usuario>:<sessao>`. A mesma pessoa pode abrir duas conversas ao mesmo tempo: são duas sessões, dois `thread_id`, dois históricos separados. Duas mensagens ao mesmo `thread_id` ao mesmo tempo não são suportadas (a CLI atende uma por vez).
- **Limitação:** o checkpoint está num arquivo local; quem usar outra máquina não vê a pendência.

**Prova (execução manual, `logs/local/sB-fixa`, commit `99a7289`, 2026-10-16):** o processo terminou na pausa (sem resposta); em outro processo, com a mesma sessão, a aprovação pendente voltou na tela e a resposta `rejeitar` foi aplicada. **Esta prova não está em `gerar_exemplos.py`** (os cenários rodam num só processo por conversa) e é anterior ao carimbo `codigo_limpo`: vale como observação, não como evidência com commit conferível.

## 4. O que acontece se ninguém responder

- **Prazo:** `PRAZO_APROVACAO_HORAS`, padrão 24 h.
- **Caminho padrão ao vencer:** **não gravar**, avisar o usuário e terminar com motivo `aprovacao_expirada`. O silêncio nunca aprova.
- **Como é verificado:** no momento em que alguém retoma, o nó compara a hora atual com o carimbo da pausa. **Não há temporizador em segundo plano**: se ninguém voltar, a pendência fica no checkpoint até alguém retomar. Isso está declarado como limitação.

**Prova (cenário `expirado`, log `logs/exemplos/expirado/trajetoria.jsonl`, commit `30e8bee` (árvore limpa), 2026-10-16, prazo reduzido a 0,036 s por `PRAZO_APROVACAO_HORAS=0.00001`):** a resposta `aprovar` chegou depois do prazo; saída "A aprovação não veio a tempo (passou de 1e-05 h sem resposta). Nada foi gravado.", motivo `aprovacao_expirada`. O caminho no log termina em `aprovar_gravacao > emitir`: o nó `gravar` não rodou.

## 5. Aprovar duas vezes

A gravação usa chave de idempotência derivada do conteúdo (hash dos campos da linha), com `ja_existia` no retorno. Repetir a aprovação não cria linha.

**Prova (cenário `pausa_edicao`, commit `30e8bee` (árvore limpa), 2026-10-16; duas conversas do mesmo usuário, a segunda raspa o catálogo de novo e a pessoa responde a mesma edição):**

| Conversa | Log | Resposta digitada | Resultado |
|---|---|---|---|
| 1 | `logs/exemplos/pausa_edicao/` | `editar remover 1,2,3,4,5` | 21 nova(s), 0 já existia(m) |
| 2 | `logs/exemplos/pausa_edicao-2/` | `editar remover 1,2,3,4,5` | **0 nova(s)**, 21 já existia(m) |

A aprovação repetida não criou linha nenhuma. O gerador restaura o banco depois de cada cenário, então não há contagem de linhas da tabela para citar: a prova é o `ja_existia` devolvido pela gravação.

## 6. A segunda parada: confirmar antes de apagar os dados

Quando a pessoa pede "apague todos os meus dados", o grafo conta o que será apagado (só leitura), **para** e mostra a ação exata:

```
Vou APAGAR todos os dados do usuário exemplo-titular-b: 2 fato(s) sobre o veículo, 1 dúvida(s) registrada(s) e 1 item(ns) do índice, 3 conversa(s) salva(s) (esta inclusive) e 3 arquivo(s) de log.
Não dá para desfazer. Se ninguém confirmar, nada é apagado.
Responda: confirmar | cancelar
```

| Resposta | Efeito |
|---|---|
| `confirmar` | apaga (cobertura em [memoria.md](memoria.md)); motivo `esquecido` |
| `cancelar` | nada é apagado; motivo `esquecimento_recusado` |

- **Se ninguém responder:** nada é apagado. Aqui o silêncio **nunca** executa, e a pendência fica no checkpoint como a da gravação. Não há prazo: apagar dados não tem urgência que justifique agir sem resposta.
- **Aprovar duas vezes:** a remoção é idempotente por natureza (apagar o que já foi apagado devolve zero linhas), e a conversa em andamento é apagada depois, fora do grafo.
- **Prova (commit `30e8bee` (árvore limpa), 2026-10-16):** no cenário `esquecer_cancelar` (log `logs/exemplo-titular-a/esquecer_cancelar-2/`) a pessoa cancelou e a saída foi "Cancelei: nada foi apagado.". No cenário `esquecer_confirmar` ela confirmou: a varredura independente logo após apagar deu **0 ocorrências** (`Varredura por "exemplo-titular-b": 0 ocorrência(s).`) e a mensagem seguinte voltou a perguntar "Qual é o modelo do veículo?". Os logs do titular foram apagados pela própria remoção; a transcrição e a linha de auditoria (só o hash) estão em `logs/exemplos/resultado.json`.
