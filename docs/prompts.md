# Prompts: o que cada um faz, por que é assim e o que medimos

O sistema chama o modelo em **três** pontos. O resto (rotas, textos de resposta, motivos de término, parada para aprovação humana) é código ([grafo.md](grafo.md)). Cada prompt é um arquivo em `src/prompts/`, lido em tempo de execução; nenhum está dentro de f-string.

| Etapa (nó) | Arquivo | Técnica | Por que ela | Contrato de saída | Como é testada |
|---|---|---|---|---|---|
| **`extrair`**: classifica a intenção e preenche a ficha do veículo | `extracao.md` (+ regras de `procedural.md`, seção `extrair`) | **few-shot** (7 exemplos) com saída estruturada | A tarefa é classificar e extrair, e as fronteiras entre as intenções (comprar ≠ achar peça; diagnosticar ≠ manual) são convenções do case que o modelo não conhece: exemplos mostram a fronteira melhor que adjetivos. Cadeia de pensamento não é usada: a saída é uma ficha, não uma explicação, e 300 tokens de saída bastam | JSON Schema (`Extracao`: `intencao` em PECA, MANUAL, FORA_DO_ESCOPO, ESQUECER, INDEFINIDA; `modelo`, `ano`, `motorizacao`, `fabricante`, `nome_peca`, `duvida`), imposto por `response_format` | `avaliar_extracao.py`: 29 casos rotulados, 3 rodadas |
| **`ler_manual`**: decide se os trechos recuperados respondem à dúvida | `leitor_manual_pdf/tool_call_leitura_pdf.md` (+ `procedural.md`, seção `ler_manual`) | **geração ancorada** nos trechos, com um campo `pensamento` curto (cadeia de pensamento limitada a 2 frases) | O modelo precisa primeiro dizer se algum trecho trata do assunto e só então resumir; sem ancoragem ele completa com conhecimento próprio. O limite de 2 frases evita gastar os 600 tokens de saída raciocinando | JSON Schema (`LeituraManual`: `pensamento`, `trecho_original`, `resumo`, `sanada`) | `avaliar_rag.py manual` e `ablacao_prompts.py leitor`: 18 dúvidas com resposta e 14 sem |
| **`raspar`**: extrai as peças de uma página do catálogo | `webscrapper/tool_scrapping.md` | **one-shot** (um cartão de exemplo em markdown) com saída estruturada | O modelo precisa reconhecer o cartão de peça num markdown de ~73 mil caracteres; um exemplo do formato real vale mais que a descrição | JSON Schema (lista de `Peca` e `max_pagina`) | `avaliar_raspagem.py`: confere cada peça devolvida contra o texto que o modelo recebeu |

Nenhum modelo decide rota: `extrair` só devolve a ficha, `ler_manual` só devolve `sanada`, e quem decide o próximo nó é função Python. Por isso a avaliação dos prompts é a avaliação desses três contratos.

## 1. Organização e versionamento

```
src/prompts/
├── extracao.md                                  # prompt do nó extrair
├── procedural.md                                # regras aprendidas, escritas por uma pessoa (memoria.md §procedural)
├── leitor_manual_pdf/tool_call_leitura_pdf.md   # prompt do nó ler_manual
├── webscrapper/tool_scrapping.md                # prompt do nó raspar
└── system_prompt.py                             # carregador
```

Cada execução grava no `log` de início o **hash (12 caracteres do SHA-256) de cada arquivo de `src/prompts/`** e o carimbo do código (`commit`, `codigo_limpo`, `arquivos_alterados`; `src/trajetoria.py`). Com o commit e o hash, qualquer resultado deste documento se liga à versão exata do prompt. O git guarda o histórico; o hash prova qual versão rodou. `procedural.md` nunca é escrito pelo sistema: só uma pessoa, por commit revisado.

## 2. Condições das medições

- Modelo: `qwen2.5:7b` local (Ollama 0.32), `temperature=0`. Árvore: todos os números de extração/leitor/raspagem foram gerados em 2026-10-18, sobre o commit `a5113fe`.
- **Contexto do Ollama: 8192** (o padrão é 4096). Isso só importa para a raspagem (§6): os prompts da extração (cerca de 1.100 tokens) e do leitor (até 2.307) cabem nos dois contextos, então a linha de base da extração e a leitura valem nos dois.
- A linha de base da extração (`logs/avaliacao-extracao/resultado.json`) foi gerada com a árvore limpa (`codigo_limpo: true`). **As ablações e a raspagem têm `codigo_limpo: false`**: o carimbo lista `ablacao_prompts.py` e `avaliar_raspagem.py`, scripts de avaliação que foram editados depois (o relatório de entradas e saídas; a checagem de preço reformatado). Nenhum arquivo de `src/` mudou entre as medições.

## 3. Extração (`extrair`)

### 3.1 O conjunto

29 casos (`dados/casos_extracao.json`), cada um com a conversa, o resultado esperado e **o motivo de existir**: peça completa (6), peça incompleta (2), várias mensagens (2), manual (7), fora do escopo (5), esquecer (3), indefinida (4). Os rótulos foram revisados por uma pessoa antes da medição. Um caso "acerta" quando a intenção **e** todos os campos esperados batem (`avaliar_extracao.py`).

**Vazamento.** Alguns casos são quase cópia dos 7 exemplos do prompt (similaridade ≥ 0,80, `difflib`): 8 deles (ids 1, 9, 11, 12, 17, 18, 23, 26). Acertar esses não prova nada, então a medida que vale é a dos **21 casos que o prompt nunca viu** (`heldout`).

### 3.2 Linha de base (3 rodadas, árvore limpa)

| | Todos | Fora do prompt |
|---|---|---|
| Intenção correta | 28/29 | 20/21 |
| Ficha completa correta | 28/29 | 20/21 |

As 3 rodadas deram **o mesmo resultado** (nenhum caso instável). Por grupo: peça completa 18/18, incompleta 6/6, várias mensagens 6/6, manual 21/21, esquecer 9/9, indefinida 12/12, fora do escopo 12/15. O único erro, em todas as rodadas, é o **caso 21** ("Meu carro está fazendo um barulho estranho na roda, o que pode ser?", esperado FORA_DO_ESCOPO por ser diagnóstico de defeito): o modelo classifica como MANUAL.

### 3.3 Ablação: uma frase por vez (21 variantes × 2 rodadas)

`python ablacao_prompts.py extracao 2` (1.269 s). Cada variante é o prompt atual **menos uma frase** (ou um exemplo, ou uma regra aprendida); o texto é trocado em memória, nada em `src/prompts/` é alterado. "Saiu" é um caso que a base acertava e a variante deixou de acertar; "entrou", o contrário.

| Variante (o que foi tirado) | Caracteres | Saíram | Entraram | Veredito do script |
|---|---|---|---|---|
| `papel`: "Você NÃO responde ao usuário…" | 88 | – | – | sem efeito |
| `conversa_inteira`: "Use a conversa inteira… mantenha a intenção anterior" | 138 | 5 | 21 | faz diferença |
| `manual_exemplos`: a lista entre parênteses de MANUAL | 102 | – | – | sem efeito |
| `fora_lista`: "comprar, reservar, saber preço…, diagnosticar defeito" | 70 | – | – | sem efeito |
| `modelo_sem_montadora`: "só o modelo, sem a montadora" | 77 | 3 | 21 | faz diferença |
| `fabricante`: "somente se o usuário a disse" | 59 | – | – | sem efeito |
| `nome_peca` | 115 | – | 21 | melhora |
| `duvida` | 107 | – | 21 | melhora |
| `regra_null`: "null para tudo o que o usuário não disse" | 86 | – | 21 | melhora |
| `regra_correcao`: "vale o mais recente" | 54 | – | 21 | melhora |
| `regra_json`: "Responda só com o JSON do schema" | 36 | – | 21 | melhora |
| `ex_peca` (exemplo da palheta do Corsa) | 218 | – | – | sem efeito |
| `ex_manual` (os dois exemplos de MANUAL) | 450 | 5 | – | faz diferença |
| `ex_fora` ("Compre agora a pastilha…") | 209 | 5 | 21 | faz diferença |
| `ex_conversa` (conversa de 3 mensagens) | 232 | 5 | – | faz diferença |
| `ex_indefinida` ("oi, bom dia") | 144 | 5 | 21 | faz diferença |
| `ex_esquecer` ("Apague todos os meus dados") | 168 | 5 | – | faz diferença |
| **`zero_shot`**: todos os exemplos | 1.433 | – | – | sem efeito |
| `proc_compra` (regra aprendida de compra) | – | – | 21 | melhora |
| `proc_cumprimento` (regra aprendida de cumprimento) | – | – | 21 | melhora |
| `proc_todas` (as duas regras aprendidas) | – | 5 | – | faz diferença |

**O que os dados dizem, e o que não dizem.**

1. **Só três casos se mexem em toda a ablação**: 3, 5 e 21. Os outros 26 não mudam com nenhuma das 21 variantes. Isso vale em dois sentidos. Para frases que têm casos dedicados (ver a tabela da §3.4), "nada mudou" é evidência de que o modelo **não precisa delas para esses casos**. Mas o conjunto é pequeno e o modelo é capaz de acertar sem a frase por outras pistas (o schema, os exemplos restantes): não prova que a frase é inútil em geral.
2. **O caso 5** ("me ve a palheta traseria do corsa 2008 motor 1.4", com erro de digitação e português de balcão) é o único que depende do prompt de forma consistente: 7 das 21 variantes o perdem. Mas **o efeito não é aditivo**: tirar qualquer um dos exemplos de MANUAL, de conversa ou de esquecer o derruba, e tirar **todos** os exemplos (`zero_shot`) não o derruba. Não dá para atribuir esse acerto a uma frase; é um caso na fronteira do modelo.
3. **O "melhora" do caso 21 não é mérito de remover a frase.** O caso 21 passa a acertar em 11 das 21 variantes, inclusive ao tirar frases que nada têm a ver com diagnóstico (`regra_json`, `fabricante`...). O modelo trata o caso 21 como cara ou coroa e qualquer perturbação do prompt o vira. Não vou tirar `nome_peca`, `duvida` ou `regra_null` com base nisso.
4. `modelo_sem_montadora` custa o caso 3 ("VW Fox 2015 1.6", esperado `fabricante` "Volkswagen"): é a única frase cuja perda aparece em um caso que combina com ela (a montadora abreviada junto do modelo). Não inspecionei qual campo errou, então é uma hipótese, não uma prova.
5. `proc_todas` perde o caso 5, mas `proc_compra` e `proc_cumprimento` isoladas não: de novo, não aditivo.

### 3.4 Regra da frase: decisão para o prompt de extração

> "Se você apagar uma frase e não souber dizer o que ela impedia, ela não estava fazendo nada."

| Frase | O que impedia (medido) | Decisão |
|---|---|---|
| `modelo_sem_montadora` | perda do caso 3 (montadora abreviada); campo errado não inspecionado | **fica**: a perda tem um caso que combina com a frase |
| `conversa_inteira`, exemplos de MANUAL, conversa, esquecer (e `ex_fora`, `ex_indefinida`) | perda do caso 5; não aditivo | **ficam**: o efeito é real mas instável; o custo é 1.433 caracteres no total |
| `regra_correcao` (caso 10), `regra_null` (casos 7, 17, 29), `fabricante` (2, 3, 4, 6), `fora_lista` (18 a 22), `manual_exemplos` (11 a 16), `nome_peca` (1, 7, 8), `duvida` (11 a 17), `regra_json`, `ex_peca`, `papel`, `proc_compra`, `proc_cumprimento` | **não consegui dizer**: cada uma tem caso dedicado (entre parênteses) e o caso continua certo sem a frase. `regra_json` é redundante com o schema que o servidor impõe; `papel` descreve um limite (não responder ao usuário) que o contrato já impede | **candidatas a corte, não cortadas**. Cada remoção foi medida **sozinha**; a remoção conjunta não foi medida, e o efeito dos exemplos já mostrou que não é aditivo. Proposta: cortar `regra_json` e `papel` (redundantes com o contrato), medir de novo e só então olhar as demais |

Nada em `src/prompts/` foi alterado por esta ablação, então não há "frase que voltou": todas estão onde estavam.

**Revisão da regra de decisão, declarada.** A regra inicial julgava só a média de acertos fora do prompt (queda de 0,5 ou mais = "faz diferença"). Depois de ver dados parciais, notei que isso escondia trocas (`conversa_inteira` perdia o caso 5 e ganhava o 21, com a média intacta). Passei a comparar **caso a caso** e a listar quem entrou e quem saiu. A revisão foi feita depois de ver parte dos números; as duas leituras estão neste documento (a coluna "Saíram/Entraram" mostra tudo) para que se possa refazer o veredito.

## 4. Leitura do manual (`ler_manual`)

`python ablacao_prompts.py leitor 2` (1.621 s): 8 variantes + a base, 2 rodadas, 18 dúvidas com resposta e 14 sem. Acerto = `sanada` verdadeiro **e** o fato esperado no resumo (expressão regular, grosseira). O modelo **varia entre rodadas**, mesmo com `temperature=0`: a própria base fez 12/11 e 11/10 (respondeu/fato). Portanto **uma diferença de 1 pergunta é ruído**.

| Variante (o que foi tirado) | Respondeu | Com o fato | Δ fato | Saíram | Entraram | Falsas | Leitura |
|---|---|---|---|---|---|---|---|
| **base** | 11,5/18 | 10,5/18 | – | – | – | 0 | – |
| `nunca_conhecimento_proprio` | 9,5 | 9,0 | −1,5 | 3 | 1 | 0 | abaixo da base nas 2 rodadas; efeito pequeno |
| regra 1 (formato da mensagem) | 10,0 | 9,5 | −1,0 | 2 | 1 | 0 | ruído |
| **regra 2** (sanada em qualquer formato) | 4,5 | 4,5 | **−6,0** | 7 | 0 | 0 | **faz diferença, nítida** |
| **regra 3** (`sanada` falso só se nenhum trecho trata) | 8,5 | 8,0 | **−2,5** | 4 | 0 | 0 | **faz diferença** |
| regra 4 (`trecho_original` literal) | 10,5 | 9,5 | −1,0 | 2 | 1 | 0 | ruído |
| **regra 5** (`resumo` ≤ 80 palavras…) | 16,0 | 15,0 | **+4,5** | 0 | 5 | 0 | **tirar melhora**, nas 2 rodadas (16/15 e 16/15) |
| regra 6 (`pensamento` ≤ 2 frases) | 12,0 | 12,0 | +1,5 | 1 | 3 | 0 | sem efeito mensurável |
| `proc_indice` (regra aprendida do índice) | 13,0 | 12,0 | +1,5 | 2 | 5 | 0 | sem efeito mensurável |

(Os veredictos mecânicos do script, "faz diferença" para toda variante em que alguma pergunta saiu, super-contam: com ruído de 1 pergunta, a leitura da última coluna é a que vale. As colunas "Saíram/Entraram" e as frações por pergunta estão em `logs/ablacao-prompts/leitor.json`.)

**Achados.**

1. **As regras 2 e 3 fazem o trabalho do prompt.** Sem a regra 2 o leitor responde 4,5 de 18; sem a 3, 8,5. Elas impedem que o modelo trate "formato diferente de parágrafo" ou "assunto só tocado por um trecho" como "sem resposta". É a mesma lição do diagnóstico do RAG ([rag.md](rag.md) §6.2): o prompt rígido responde 3/18, o permissivo, 10 a 11.
2. **A regra 5 prejudica.** Sem o limite de 80 palavras e a frase sobre o que falta, o leitor responde 16 de 18 (contra 11,5), **sem nenhuma falsa resposta nas 14 sem resposta**. Não investiguei a causa e não vou chutar. Esta é a **ação que a ablação recomenda**, mas **não a apliquei**: mudar o prompt muda as medições de `rag.md`. Proposta: tirar a regra 5, medir em 3 rodadas (e conferir de novo as 14 sem resposta) e commitar junto.
3. **`proc_indice` não mostra efeito** (+1,5, dentro do ruído). A regra aprendida foi escrita depois de uma falha real (o índice do manual como "resposta"); a medição **não a sustenta nem a derruba**.
4. **0 falsas respostas** em todas as variantes e rodadas (14 de 14 recusadas): a amostra é pequena (14 perguntas, um manual, um modelo).

## 5. Raspagem (`raspar`)

`python avaliar_raspagem.py 2`: raspa o catálogo da Chevrolet ao vivo (Onix 2018, "palheta traseira"), sem gravar na base, e confere cada peça devolvida contra o **texto exato** que o modelo recebeu. A página muda, então os números são de **2026-10-18**.

| | Rodada 1 | Rodada 2 |
|---|---|---|
| Página enviada | 73.354 caracteres, 202 cartões de peça | idem |
| Peças devolvidas pelo modelo | 54 | 54 |
| Nome da peça está na página | 54/54 | 54/54 |
| Carros compatíveis estão na página | 54/54 (todos) | 54/54 |
| **Código da peça está na página** | **13/54** | **13/54** |
| Código com forma de código (3 a 20 caracteres alfanuméricos) | 51/54 | 51/54 |
| Código repetido entre peças | 0 | 0 |
| Tempo | 75 s | 73 s |

**Leitura.** Os nomes e as aplicações são fiéis ao texto; os **códigos não**: 41 dos 54 (76%) não existem na página. O cartão de exemplo do prompt mostra um código de 8 dígitos ("Nº original GM: 98551033"), e o modelo devolve números de 3 a 6 dígitos que parecem código mas que ele **inventou**. A medição anterior (contexto 4096, não guardada no log) já mostrava o mesmo: 8 de 24 códigos na página e 15 de 24 eram **preços reformatados** ("2.097,65" virando "2097.65"). A checagem `codigo_e_preco_da_pagina` existe por isso e deu 0 desta vez.

**Por que, e o que isso exige do prompt.** A página tem 34.591 tokens contando o prompt; o servidor entrega ao modelo **no máximo 4.098** (12%; com o padrão 4096, 2.050, ou 6%), **o fim da página**. O modelo vê uma fração dos cartões e, sem o código à vista, preenche o campo com algo plausível. Isso é uma falha do **desenho** (enviar a página inteira a um modelo pequeno e pedir tudo), não de uma frase do prompt: nenhuma ablação de frase a conserta. A correção tem opções que não apliquei (mudam o código, não o prompt):

- extrair os cartões em código (`### [nome](/peca/CODIGO/slug)` e "Nº original GM" são regulares) e usar o modelo só onde há ambiguidade;
- validar o código devolvido contra o texto da página antes de gravar (a mesma checagem do avaliador);
- limitar o número de páginas e o tempo total (hoje não há teto).

A gravação do scraper é protegida pela aprovação humana ([humano.md](humano.md)): um código inventado só entra na base se quem aprova não perceber.

## 6. O corte silencioso do servidor (achado desta medição)

Quando o prompt **passa do contexto**, o Ollama o **corta para metade do contexto (mais 2 tokens), descartando o começo**, sem erro: só um aviso no log do servidor (`truncating input prompt`). Com o contexto padrão de 4096 o prompt cortado fica com 2.050 tokens; com 8192, 4.098. Abaixo do contexto nada é cortado. Teste da agulha (`SENHA-INICIAL` no começo do texto, `SENHA-FINAL` no fim; o modelo deve devolver cada uma):

| Caracteres (tokens contados) | Contexto 4096 | Contexto 8192 |
|---|---|---|
| 2.000 e 5.000 (até 3.721) | acha as duas | acha as duas |
| 8.000 (5.868) | **perde a inicial** e a instrução de sistema (responde em frase, não só a senha) | acha as duas |
| 12.000 a 73.000 | perde a inicial | perde a inicial |

O que isso significa para cada etapa, conferido no log do servidor:

- **`extrair`** (1.087 a 1.131 tokens) e **`ler_manual`** (até 2.307 tokens nas 18 dúvidas): ficam abaixo de 4096, **nunca foram cortados**. Os resultados das §3 e §4 e de [rag.md](rag.md) não dependem do contexto. (Uma leitura minha anterior, de que o leitor passava do limite em 10 de 18 chamadas, estava errada: contei as chamadas com 2.040 tokens ou mais, não as cortadas.)
- **`raspar`**: a chamada tem 34.591 tokens e **sempre é cortada**, nos dois contextos. O modelo recebe **o fim da página**: 12% com 8192, 6% com 4096, **sem o prompt de sistema** (que fica no começo). É o problema da §5.

Recomendação: registrar o contexto do Ollama junto de cada medição (`ablacao_prompts.py` já grava `contexto_ollama` a partir da variável `CONTEXTO_OLLAMA`) e tratar o corte como defeito do desenho da raspagem, não do prompt.

## 7. Como reproduzir

```bash
export AI_MODEL=qwen2.5:7b CONTEXTO_OLLAMA=8192          # com o Ollama iniciado com OLLAMA_CONTEXT_LENGTH=8192
python avaliar_extracao.py 3                              # linha de base da extração
python ablacao_prompts.py extracao 2                      # logs/ablacao-prompts/extracao.json (~21 min)
python ablacao_prompts.py leitor 2                        # logs/ablacao-prompts/leitor.json (~27 min)
python avaliar_raspagem.py 2                              # logs/avaliacao-raspagem/resultado.json (precisa de internet e Chromium)
```

Cada resultado leva `commit`, `codigo_limpo`, `arquivos_alterados`, data e modelo. Um resultado só vale para o commit que ele diz **e só se `codigo_limpo` for `true`**; os de ablação e raspagem desta data têm `false` pelos motivos da §2.

## 8. Limites

- 29 casos de extração e 32 de leitura: poucos, de um autor, um manual, um modelo. O conjunto de extração praticamente não discrimina frases (3 casos se movem).
- A ablação tira **uma frase por vez**: não vê interações entre frases (já vimos que o efeito dos exemplos não é aditivo).
- O leitor varia entre rodadas: 2 rodadas por variante distinguem diferenças de 3 ou mais perguntas, não de 1.
- A regra de decisão da extração foi revista depois de ver dados parciais (§3.4).
- O stamp das ablações e da raspagem mostra `codigo_limpo: false`.
- A raspagem varia no contexto: 54 peças com 8192; a medição anterior com 4096 devolveu 24. O número de peças depende do quanto da página o servidor entrega.
- `erro_ferramenta` (término por falha de ferramenta) nunca foi observado, então não está testado.
