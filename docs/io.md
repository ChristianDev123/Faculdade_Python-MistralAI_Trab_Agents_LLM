# Contrato de entrada e saída

O sistema recebe **texto livre** e devolve um **objeto validado**, `Saida`, definido em [src/contrato.py](../src/contrato.py). Toda resposta passa pelo nó `emitir`, que monta o texto por código e valida o objeto com Pydantic antes de devolvê-lo: não existe caminho de saída que o contorne. Este documento define o contrato e mostra exemplos **copiados de execuções reais**.

> **De onde vêm os exemplos.** Todos saem de `python gerar_exemplos.py`, rodado em 2026-10-16 sobre o commit `30e8bee` (árvore limpa: `true`) com a árvore limpa, no modelo `qwen2.5:7b` (Ollama, local). Cada exemplo traz a entrada exata, a saída completa e o log em `logs/exemplos/`; o resultado completo está em `logs/exemplos/resultado.json`. O modelo local não é determinístico nem com `temperature=0`: ao regenerar, o texto de uma resposta que passa pelo modelo pode variar. Para regenerar um exemplo: `python gerar_exemplos.py <cenário>`.

## 1.1 A entrada é texto

**O sistema recebe texto livre, em linguagem natural.** Não há formulário com campos, nem JSON montado por outro programa: é a entrada em texto que obriga o sistema a descobrir o que a pessoa quer (nó `extrair`), perguntar o que falta e decidir quando já sabe o suficiente.

| Forma | Onde ela entra neste sistema |
|---|---|
| **texto livre** | **a entrada do sistema**: uma frase como se fala no balcão, com erros de digitação se houver |
| arquivo, planilha, imagem | nunca como pergunta. São conteúdo que o sistema busca: os manuais em PDF e o catálogo web |
| formulário, evento de outro sistema | gatilho que antecede o sistema: o bot do Discord da loja (descrito em [case.md](case.md)) entrega a mensagem, o `user_id` e a sessão. Hoje a interface é a linha de comando, `python src/main.py [sessão]` |

**O que acompanha o texto sem ser digitado por ninguém:**

| Dado | De onde vem | Para que serve |
|---|---|---|
| `user_id` | variável `USER_ID` (padrão `local`); no Discord, o identificador de quem escreveu | dono da memória de longo prazo e da remoção de dados |
| sessão | argumento da linha de comando (padrão: data e hora) | identifica a conversa |
| `thread_id` | `"<user_id>:<sessão>"` | endereço do checkpoint: mesma chave, mesma conversa; chave nova, histórico vazio ([memoria.md](memoria.md) §7) |

## 1.2 O contrato de saída

A saída é um `Saida` (Pydantic). Os três campos que o contrato exige são **`resultado`**, **`fonte`** e **`suficiencia`**; os outros dois dizem o que aconteceu e o que falta.

```python
class Fonte(BaseModel):
    tipo: Literal['base_local', 'manual_pdf', 'catalogo_web', 'memoria_semantica', 'memoria_episodica', 'nenhuma']
    origem: str        # a tabela, o PDF, o endereço consultado
    evidencia: str     # o que foi consultado e quanto voltou

class Saida(BaseModel):
    resultado: str                    # o texto para a pessoa (montado por código, não pelo modelo)
    dados: Optional[list[Peca]]       # as peças, estruturadas, quando a resposta é uma lista de peças
    fonte: list[Fonte]                # o que sustenta o resultado, conferível
    suficiencia: bool                 # o sistema teve base para responder?
    situacao: Literal['respondido', 'faltam_dados', 'fora_do_escopo', 'sem_base', 'rejeitado', 'expirado', 'esquecido', 'erro']
    pergunta_pendente: Optional[str]  # a pergunta feita à pessoa, se a situação for faltam_dados
```

| Campo | Regra |
|---|---|
| `resultado` | sempre preenchido, inclusive na recusa. O texto vem de `_montar_saida` (código), nunca do modelo, exceto o resumo do manual |
| `fonte` | a lista de onde o sistema **procurou**. Só `suficiencia = true` diz que a fonte **sustenta** o resultado: numa recusa de manual, `fonte` lista as páginas consultadas, que não responderam |
| `suficiencia` | `true` quando a resposta tem base (`respondido`) ou a ação pedida foi concluída (`esquecido`); `false` em todo o resto |
| `situacao` | uma das oito; o motivo de término fino (doze valores) fica em [arquitetura.md](arquitetura.md) |

**A recusa é parte do contrato, não exceção dele.** Pergunta que o corpus não responde volta como `situacao: "sem_base"`, `suficiencia: false` e um `resultado` que diz o que falta (exemplos 3 e 4).

O modelo também tem um contrato de saída, para as etapas em que é chamado: `Extracao` (intenção, modelo, ano, motorização, montadora, peça, dúvida, com `null` para o que a pessoa não disse) e `LeituraManual` (`pensamento`, `trecho_original`, `resumo`, `sanada`). Eles estão em [prompts.md](prompts.md).

## 1.3 Os exemplos

Sete execuções reais. As quatro primeiras mostram o uso principal e a recusa; as três últimas, as entradas que não dá para atender como estão (§1.4).

| # | Exemplo | Situação | Cenário |
|---|---|---|---|
| 1 | caminho feliz: peça que está na base | `respondido` | `feliz` |
| 2 | dúvida de manual respondida, com a fonte | `respondido` | `manual` |
| 3 | **recusa:** a resposta não está no corpus | `sem_base` | `recusa_fora_corpus` |
| 4 | **recusa útil:** a peça existe, mas sem código | `sem_base` | `recusa_sem_codigo` |
| 5 | entrada **incompleta** | `faltam_dados` | `incompleta` |
| 6 | entrada **ambígua** | `faltam_dados` | `ambigua` |
| 7 | entrada **fora do escopo** | `fora_do_escopo` | `fora_escopo` |

### Exemplo 1: caminho feliz, peça que está na base local

**Entrada exata:**

```text
Qual o código da palheta traseira do Corsa 2008 1.4 da Chevrolet?
```

**Saída completa** (o objeto inteiro, com os campos vazios):

```json
{
  "resultado": "Encontrei 1 peça(s) para Corsa 2008 1.4 na base local:\n  1. Palheta traseira ACDelco — código 93356933",
  "dados": [
    {
      "nome_peca": "Palheta traseira ACDelco",
      "codigo_peca": "93356933",
      "carros_compativeis": [
        "Corsa A Hatch",
        "Corsa A Pickup",
        "Corsa A Sedan",
        "Corsa A Wagon"
      ]
    }
  ],
  "fonte": [
    {
      "tipo": "base_local",
      "origem": "pecas_automoveis",
      "evidencia": "1 linha(s) com {'modelo': 'Corsa', 'ano_fabricacao': 2008, 'motorizacao': '1.4', 'nm_peca': 'palheta traseira'}"
    }
  ],
  "suficiencia": true,
  "situacao": "respondido",
  "pergunta_pendente": null
}
```

**O que ler ali:** `suficiencia: true`, `situacao: "respondido"` e, em `fonte`, a tabela e o filtro exatos que a sustentam (`pecas_automoveis`, modelo, ano, motorização e peça). O código `93356933` vem de uma linha do banco, não do modelo: o modelo só extraiu os dados do texto. `dados` traz a peça estruturada, com os carros compatíveis.

**Execução:** commit `30e8bee` (árvore limpa: `true`), 2026-10-16, modelo `qwen2.5:7b`; cenário `feliz` de `gerar_exemplos.py`; log `logs/exemplos/feliz/trajetoria.jsonl`; 1 chamada(s) ao modelo, 2.9 s.

### Exemplo 2: dúvida de manual respondida

**Entrada exata:**

```text
Qual a capacidade do tanque de combustível do meu Fox 2015?
```

**Saída completa** (o objeto inteiro, com os campos vazios):

```json
{
  "resultado": "O tanque de combustível tem uma capacidade aproximada de 50 litros, com 7 litros reservados.\n(Manual Volkswagen_Fox_2015.pdf, páginas [195, 196, 197])",
  "dados": null,
  "fonte": [
    {
      "tipo": "memoria_episodica",
      "origem": "memoria_episodica",
      "evidencia": "nenhuma pergunta parecida (melhor distância None, limiar de corte em memoria.py)"
    },
    {
      "tipo": "manual_pdf",
      "origem": "Volkswagen_Fox_2015.pdf",
      "evidencia": "páginas [195, 196, 197]"
    }
  ],
  "suficiencia": true,
  "situacao": "respondido",
  "pergunta_pendente": null
}
```

**O que ler ali:** a resposta cita o manual e as páginas (`[195, 196, 197]`), e `fonte` traz duas entradas: a **memória episódica**, que procurou uma pergunta parecida e não achou (`nenhuma pergunta parecida`), e o **manual**, de onde veio a resposta. A segunda vez que a mesma pergunta aparece, essa busca acerta e o manual deixa de ser lido ([memoria.md](memoria.md) §5).

**Execução:** commit `30e8bee` (árvore limpa: `true`), 2026-10-16, modelo `qwen2.5:7b`; cenário `manual` de `gerar_exemplos.py`; log `logs/exemplos/manual/trajetoria.jsonl`; 2 chamada(s) ao modelo, 13.1 s.

### Exemplo 3: recusa: a resposta não está no corpus

**Entrada exata:**

```text
Quais são os períodos de manutenção do meu Fox 2015?
```

**Saída completa** (o objeto inteiro, com os campos vazios):

```json
{
  "resultado": "O manual Volkswagen_Fox_2015.pdf não traz uma resposta clara para essa dúvida. O manual não especifica os períodos de manutenção para o Fox 2015. Consulte a concessionária para confirmar.",
  "dados": null,
  "fonte": [
    {
      "tipo": "memoria_episodica",
      "origem": "memoria_episodica",
      "evidencia": "nenhuma pergunta parecida (melhor distância None, limiar de corte em memoria.py)"
    },
    {
      "tipo": "manual_pdf",
      "origem": "Volkswagen_Fox_2015.pdf",
      "evidencia": "páginas [22, 29, 37, 224, 225, 257]"
    }
  ],
  "suficiencia": false,
  "situacao": "sem_base",
  "pergunta_pendente": null
}
```

**O que ler ali:** `suficiencia: false` e `situacao: "sem_base"`. O sistema **não inventou** um intervalo de manutenção: disse que o manual não traz a resposta e mandou consultar a concessionária. As páginas em `fonte` são onde se procurou. O manual só remete ao caderno "Manutenção e garantia", que não faz parte do corpus ([rag.md](rag.md) §3).

**Execução:** commit `30e8bee` (árvore limpa: `true`), 2026-10-16, modelo `qwen2.5:7b`; cenário `recusa_fora_corpus` de `gerar_exemplos.py`; log `logs/exemplos/recusa_fora_corpus/trajetoria.jsonl`; 2 chamada(s) ao modelo, 12.6 s.

### Exemplo 4: recusa útil: a peça existe, mas sem código cadastrado

**Entrada exata:**

```text
Qual o código da roda de liga leve do Corsa 2008 1.4 da Chevrolet?
```

**Saída completa** (o objeto inteiro, com os campos vazios):

```json
{
  "resultado": "Encontrei \"Roda de liga leve\" para Corsa 2008 1.4 no catálogo, mas sem código cadastrado. Sem o código não indico a peça; confirme no balcão ou com o distribuidor.",
  "dados": null,
  "fonte": [
    {
      "tipo": "base_local",
      "origem": "pecas_automoveis",
      "evidencia": "1 linha(s) com {'modelo': 'Corsa', 'ano_fabricacao': 2008, 'motorizacao': '1.4', 'nm_peca': 'roda de liga leve'}"
    }
  ],
  "suficiencia": false,
  "situacao": "sem_base",
  "pergunta_pendente": null
}
```

**O que ler ali:** a base **tem** a "Roda de liga leve" para este veículo, mas o código no catálogo é "N/A". A regra do domínio ([case.md](case.md)) é dizer que não encontrou, nunca aproximar: o sistema recusou (`suficiencia: false`) e disse o que fazer em seguida. Antes de uma correção feita nesta frente, a resposta era "código N/A" com `suficiencia: true`.

**Execução:** commit `30e8bee` (árvore limpa: `true`), 2026-10-16, modelo `qwen2.5:7b`; cenário `recusa_sem_codigo` de `gerar_exemplos.py`; log `logs/exemplos/recusa_sem_codigo/trajetoria.jsonl`; 1 chamada(s) ao modelo, 2.9 s.

## 1.4 A entrada que não dá para atender

Nas três situações abaixo, responder como se a entrada estivesse completa produziria uma saída que parece boa e não é. Por isso elas são tratadas no contrato, por regra em código (`rota_pos_extracao`), e não pelo humor do modelo.

| Situação | O que o sistema faz | Exemplo |
|---|---|---|
| **incompleta** | pergunta **uma** coisa que falta, na ordem modelo, ano, motorização, montadora, peça. Depois de 3 perguntas iguais sem resposta, desiste e diz por quê | 5 |
| **ambígua** | não escolhe: pergunta | 6 |
| **fora do escopo** | recusa e diz o que ele faz; não consulta nem grava nada | 7 |

### Exemplo 5: entrada incompleta

**Entrada exata:**

```text
Qual é o código da pastilha de freio do Corolla 2020?
```

**Saída completa** (o objeto inteiro, com os campos vazios):

```json
{
  "resultado": "Qual é a motorização do veículo (por exemplo 1.0 ou 1.6)?",
  "dados": null,
  "fonte": [
    {
      "tipo": "nenhuma",
      "origem": "sistema",
      "evidencia": "sem consulta"
    }
  ],
  "suficiencia": false,
  "situacao": "faltam_dados",
  "pergunta_pendente": "Qual é a motorização do veículo (por exemplo 1.0 ou 1.6)?"
}
```

**O que ler ali:** o sistema **não buscou nada** (`fonte: nenhuma`, `sem consulta`) e perguntou o que falta, em `pergunta_pendente`. Pelo log, o caminho foi `entrada > lembrar > extrair > perguntar > emitir`: nem a base nem o catálogo foram consultados. A montadora (Toyota) não foi perguntada porque o código a completa a partir do modelo "Corolla".

**Execução:** commit `30e8bee` (árvore limpa: `true`), 2026-10-16, modelo `qwen2.5:7b`; cenário `incompleta` de `gerar_exemplos.py`; log `logs/exemplos/incompleta/trajetoria.jsonl`; 1 chamada(s) ao modelo, 2.7 s.

### Exemplo 6: entrada ambígua

**Entrada exata:**

```text
Preciso da peça do Corolla 2020.
```

**Saída completa** (o objeto inteiro, com os campos vazios):

```json
{
  "resultado": "Qual é a motorização do veículo (por exemplo 1.0 ou 1.6)?",
  "dados": null,
  "fonte": [
    {
      "tipo": "nenhuma",
      "origem": "sistema",
      "evidencia": "sem consulta"
    }
  ],
  "suficiencia": false,
  "situacao": "faltam_dados",
  "pergunta_pendente": "Qual é a motorização do veículo (por exemplo 1.0 ou 1.6)?"
}
```

**O que ler ali:** o sistema **não escolheu** uma peça nem um motor: perguntou. **Limite desta resposta:** ele perguntou a motorização, e não qual peça a pessoa quer, que é a ambiguidade que mais pesa. A causa é a ordem fixa dos campos obrigatórios (`OBRIGATORIOS` em `src/nos.py`), que deixa a peça para o fim. Funciona, mas a pergunta mais útil é a última.

**Execução:** commit `30e8bee` (árvore limpa: `true`), 2026-10-16, modelo `qwen2.5:7b`; cenário `ambigua` de `gerar_exemplos.py`; log `logs/exemplos/ambigua/trajetoria.jsonl`; 1 chamada(s) ao modelo, 2.7 s.

### Exemplo 7: entrada fora do escopo

**Entrada exata:**

```text
Compre agora a pastilha de freio para o meu Corolla.
```

**Saída completa** (o objeto inteiro, com os campos vazios):

```json
{
  "resultado": "Eu só informo peças compatíveis com o veículo e respostas do manual do proprietário. Não faço compra, reserva, cotação de preço nem diagnóstico de defeito.",
  "dados": null,
  "fonte": [
    {
      "tipo": "nenhuma",
      "origem": "sistema",
      "evidencia": "sem consulta"
    }
  ],
  "suficiencia": false,
  "situacao": "fora_do_escopo",
  "pergunta_pendente": null
}
```

**O que ler ali:** o sistema reconhece a intenção (pedido de compra), recusa e diz o que faz. O log prova que **nada foi consultado nem gravado**: o caminho foi `entrada > lembrar > extrair > recusar > emitir`, sem `consultar_base`, `raspar` nem `gravar`. A recusa sai de uma regra em código; o modelo só classificou a intenção (`FORA_DO_ESCOPO`).

**Execução:** commit `30e8bee` (árvore limpa: `true`), 2026-10-16, modelo `qwen2.5:7b`; cenário `fora_escopo` de `gerar_exemplos.py`; log `logs/exemplos/fora_escopo/trajetoria.jsonl`; 1 chamada(s) ao modelo, 2.9 s.

## 1.5 Os motivos de término

O campo `situacao` tem oito valores; o motivo de término que o log registra (`motivo_termino`) é mais fino, tem doze e está em [arquitetura.md](arquitetura.md) §2.5, cada um com a execução que o produziu.

## 1.6 Defeitos conhecidos do contrato

Encontrados ao gerar estes exemplos; nenhum foi corrigido nesta rodada.

| Defeito | Onde aparece |
|---|---|
| a mensagem de limite diz "limite de **1 mensagens**" (plural fixo) | cenário `limite_turnos` |
| a mensagem de desistência mostra o nome **interno** do campo: `Perguntei 3 vezes sobre "intencao"` | cenário `desistiu` |
| na entrada ambígua, a pergunta mais útil (qual peça) vem por último | exemplo 6 |
| `suficiencia: true` na situação `esquecido` significa "ação concluída", não "resposta com fonte" | cenário `esquecer_confirmar` |
| a `fonte` de uma recusa de manual lista páginas que **não** sustentam nada | exemplo 3 |
| **peça esgotada no catálogo volta com o aviso do site como código** ("Ooops, o estoque acabou") e a gravação o aceita; a consulta posterior a responderia como se fosse código, com `suficiencia: true` | cenário `pausa_edicao`: itens 24 a 26 da lista mostrada para aprovação; os três foram gravados |
