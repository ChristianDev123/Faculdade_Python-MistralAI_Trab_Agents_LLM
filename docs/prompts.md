# Prompts: o que cada um faz, por que é assim e o que medimos

O sistema chama o modelo em **três** pontos. O resto (rotas, textos de resposta, motivos de término, parada para aprovação humana) é código ([grafo.md](grafo.md)). Cada prompt é um arquivo em `src/prompts/`, lido em tempo de execução; nenhum está dentro de f-string.

| Etapa (nó) | Arquivo | Técnica | Por que ela | Contrato de saída | Como é testada |
|---|---|---|---|---|---|
| **`extrair`**: classifica a intenção e preenche a ficha do veículo | `extracao.md` (+ regras de `procedural.md`, seção `extrair`) | **few-shot** (7 exemplos) com saída estruturada | A tarefa é classificar e extrair, e as fronteiras entre as intenções (comprar ≠ achar peça; diagnosticar ≠ manual) são convenções do case que o modelo não conhece: exemplos mostram a fronteira melhor que adjetivos. Cadeia de pensamento não é usada: a saída é uma ficha, não uma explicação, e 300 tokens de saída bastam | JSON Schema (`Extracao`: `intencao` em PECA, MANUAL, FORA_DO_ESCOPO, ESQUECER, INDEFINIDA; `modelo`, `ano`, `motorizacao`, `fabricante`, `nome_peca`, `duvida`), imposto por `response_format` | `avaliar_extracao.py`: 29 casos rotulados, 3 rodadas |
| **`ler_manual`**: decide se os trechos recuperados respondem à dúvida | `leitor_manual_pdf/tool_call_leitura_pdf.md` (+ `procedural.md`, seção `ler_manual`) | **geração ancorada** nos trechos, com um campo `pensamento` curto (cadeia de pensamento limitada a 2 frases) | O modelo precisa primeiro dizer se algum trecho trata do assunto e só então resumir; sem ancoragem ele completa com conhecimento próprio. O limite de 2 frases evita gastar os 600 tokens de saída raciocinando | JSON Schema (`LeituraManual`: `pensamento`, `trecho_original`, `resumo`, `sanada`) | `avaliar_rag.py manual` e `ablacao_prompts.py leitor`: 18 dúvidas com resposta e 14 sem |
| **`raspar`**: lê as peças de uma página do catálogo | código (`src/webscrapper.py`); **reserva** com o modelo: `webscrapper/tool_scrapping.md` | cartões `/peca/<código>/<slug>` **lidos em código**; só a página sem esse formato vai ao modelo, em lotes, com **one-shot** (um cartão de exemplo) e saída estruturada | O código da peça está no endereço do link: lê-lo é regra, não julgamento. O modelo local inventava o código quando não o via (§5). Fica como reserva para catálogo de layout desconhecido, e o que ele devolve só vale se o código estiver no texto | JSON Schema da reserva (`dados_peca`: lista de `Peca`); a saída do leitor em código é a mesma ficha | `avaliar_raspagem.py` (modos `auto` e `modelo`): confere cada peça contra o texto da página |

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
| **regra 5** (`resumo` ≤ 80 palavras…) | 16,0 | 15,0 | **+4,5** | 0 | 5 | 0 | **tirar melhora**, nas 2 rodadas (16/15 e 16/15); aplicada, ver §4.1 |
| regra 6 (`pensamento` ≤ 2 frases) | 12,0 | 12,0 | +1,5 | 1 | 3 | 0 | sem efeito mensurável |
| `proc_indice` (regra aprendida do índice) | 13,0 | 12,0 | +1,5 | 2 | 5 | 0 | sem efeito mensurável |

(Os veredictos mecânicos do script, "faz diferença" para toda variante em que alguma pergunta saiu, super-contam: com ruído de 1 pergunta, a leitura da última coluna é a que vale. As colunas "Saíram/Entraram" e as frações por pergunta estão em `logs/ablacao-prompts/leitor.json`.)

**Achados.**

1. **As regras 2 e 3 fazem o trabalho do prompt.** Sem a regra 2 o leitor responde 4,5 de 18; sem a 3, 8,5. Elas impedem que o modelo trate "formato diferente de parágrafo" ou "assunto só tocado por um trecho" como "sem resposta". É a mesma lição do diagnóstico do RAG ([rag.md](rag.md) §6.2): o prompt rígido responde 3/18, o permissivo, 10 a 11.
2. **A regra 5 prejudica.** Sem o limite de 80 palavras e a frase sobre o que falta, o leitor responde 16 de 18 (contra 11,5), **sem nenhuma falsa resposta nas 14 sem resposta**. Não investiguei a causa e não vou chutar. Foi a única mudança de prompt que a ablação recomendou, e foi **aplicada e confirmada em 3 rodadas** (§4.1).
3. **`proc_indice` não mostra efeito** (+1,5, dentro do ruído). A regra aprendida foi escrita depois de uma falha real (o índice do manual como "resposta"); a medição **não a sustenta nem a derruba**.
4. **0 falsas respostas** em todas as variantes e rodadas (14 de 14 recusadas): a amostra é pequena (14 perguntas, um manual, um modelo).

### 4.1 Mudança aplicada: o prompt sem a regra 5

A regra 5 (`resumo` em português, no máximo 80 palavras, só com o que os trechos dizem; se `sanada` for falso, uma frase sobre o que falta) foi removida de `tool_call_leitura_pdf.md`, e a regra 6 virou a 5 (a numeração da tabela acima é a antiga). O resto do prompt, inclusive "usando SOMENTE os trechos" e "Nunca complete com conhecimento próprio", ficou. Controle e variante rodaram na mesma sessão, com o mesmo contexto (8192), o mesmo modelo e `python avaliar_rag.py manual 3 <rótulo>`; os logs são `logs/rag-avaliacao/manual-com-regra5.json` (hash do prompt `4c304a9c2377`) e `manual-sem-regra5.json` (`6ea02d3b88d4`).

| | Rodada 1 | Rodada 2 | Rodada 3 | Falsas respostas (14 sem resposta) |
|---|---|---|---|---|
| **com** a regra 5 | 12 / fato 11 | 11 / fato 10 | 11 / fato 10 | 0, 0, 0 |
| **sem** a regra 5 | 16 / fato 15 | 16 / fato 15 | 16 / fato 15 | 0, 0, 0 |

Por pergunta, das 18 com resposta: **5 passaram a acertar nas 3 rodadas e nenhuma deixou de acertar**. Entraram "Como trocar a lâmpada do farol?", "O que devo fazer antes de desconectar a bateria?", "Quantos kPa suporta o pneu no máximo?", "É normal sair fumaça ou pó quando o airbag dispara?" e "Cuidados ao lavar o veículo com jato de alta pressão" (esta acertava 1 de 3). **Continuam errando nas 3 rodadas**: "Como substituir a bateria do veículo?", "Como desembaçar o vidro de trás?" e "O pó que sai do airbag é perigoso?". O resultado é estável: as 3 rodadas deram o mesmo número, ao contrário da base, que variou.

Limites: o teste é de um manual, 18 + 14 perguntas e um modelo; as 3 perguntas que seguem erradas não foram investigadas (hipótese não verificada: o trecho certo não está entre os 6 devolvidos, como nas falhas 4 e 5 antigas de [rag.md](rag.md) §3). A medição **sem** a regra 5 foi refeita com a árvore limpa (commit `b1880be`) e repetiu 16/15/0 nas 3 rodadas; o controle **com** a regra 5 tem `codigo_limpo: false` (só o script de avaliação alterado). As 10 perguntas pelo grafo, refeitas depois da mudança, deram 8 de 10 contra 6 de 10 antes ([rag.md](rag.md) §3); a melhora não é toda do prompt. Os exemplos de `logs/exemplos/` foram gerados com o prompt anterior, e o hash de cada log diz qual.

## 5. Raspagem (`raspar`)

### 5.1 O defeito medido, e a mudança

`python avaliar_raspagem.py 2` raspa o catálogo da Chevrolet ao vivo (Onix 2018, "palheta traseira"), sem gravar na base, e confere cada peça devolvida contra o **texto exato** da página. A página tinha 73.354 caracteres e 202 cartões. **Antes da mudança** (modelo lendo a página inteira, commit `a7104d3`, árvore limpa, 2026-10-18):

| | Rodada 1 | Rodada 2 |
|---|---|---|
| Peças devolvidas | 34 | 30 |
| Nome da peça está na página | 34/34 | 30/30 |
| **Código da peça está na página** | **13/34** | **13/30** |
| Código é um preço reformatado | 0 | 0 |
| Tempo | 57 s | 41 s |

Os nomes e as aplicações eram fiéis; os **códigos não**: 57% a 62% não existiam na página. A causa é o desenho: a página tem 34.591 tokens e o servidor entrega ao modelo no máximo 4.098 (§6), o fim da página, sem o prompt de sistema; sem o código à vista, o modelo escrevia um número plausível. Nenhuma frase do prompt conserta isso. Em rodadas anteriores o número de peças já havia sido 24, 54 e 54, e o de códigos reais ficou em 13.

O que a página mostra: **200 dos 202 cartões trazem o código no endereço do link** (`/peca/19376259/palheta-traseira-acdelco`), e em 194 o campo "Nº original GM" é igual a ele (os outros 2 são links de cupom). O código é dado regular; ler isso é regra.

**Mudança** (`src/webscrapper.py`):

1. **Leitor em código** (`ler_cartoes`) para o formato `### [nome](/peca/<código>/<slug>)`: nome, aplicações e código exatos, sem modelo.
2. **Reserva com o modelo** só para página sem cartões nesse formato (outro catálogo, ou o mesmo com o layout mudado): o texto é partido em **lotes de 5.000 caracteres** (~2.400 tokens), para o servidor nunca cortar o começo, e o modelo propõe as peças.
3. **Validação nos dois caminhos** (`codigo_esta_no_texto`): o código precisa ter 5 ou mais caracteres, algum dígito, e aparecer no texto como item próprio. Na reserva, peça que não passa é descartada e o `avisos` conta quantas (aparece na tela de aprovação).
4. **Tetos**: no máximo `MAX_PAGINAS = 3` páginas e `MAX_SEGUNDOS = 120`, conferidos entre páginas e entre lotes; quando o teto corta, o `avisos` diz. O `max_pagina` que o modelo lia da página (chegou a dizer 43) deixou de existir; o prompt da reserva perdeu a parte de paginação.

### 5.2 Depois da mudança (commit `b1880be` mais as edições listadas no carimbo; `codigo_limpo: false` até o commit)

| | Leitor em código (`auto`) | Reserva com o modelo (`modelo`) |
|---|---|---|
| Rodadas | 2 | 2 |
| Peças devolvidas | 198, 198 | 91, 111 |
| **Código da peça está na página** | **198/198, 198/198** | **91/91, 111/111** |
| Nome e aplicações na página | 198/198 | 91/91 e 111/111 |
| Código é preço reformatado | 0 | 0 |
| Códigos repetidos | 0 | 0 |
| Tempo | 5 s e 4 s | 126 s e 143 s |
| Avisos | nenhum | "o tempo máximo (120 s) acabou no meio da página 1" |

(Os logs são `logs/avaliacao-raspagem/resultado.json` e `resultado-modelo.json`.) Das 200 peças com endereço `/peca/`, 198 saem porque 2 repetem o código de outra.

**Leitura.** O leitor em código leva ~5 s (antes, 41 a 57 s) e entrega **todas** as peças da página com o código certo; o código inventado deixou de existir. A reserva com o modelo também deixou de inventar (100% dos códigos estão na página, porque o que não estiver é descartado), mas é lenta: 91 a 111 peças em 120 s, e o teto de tempo a corta, com aviso. Ela existe para o dia em que o catálogo mudar, não como caminho principal. Nas duas rodadas da reserva nenhuma peça foi descartada pela validação: com o prompt pedindo para copiar o código, o modelo passou a copiá-lo quando vê o card inteiro no lote.

**Validação ponta a ponta (fluxo real pelo grafo, `logs/validacao-raspagem/s1`):** "Quero o código da palheta traseira do meu Onix 2018 1.0 da Chevrolet." pausou em 8 s com 198 candidatas e `fonte` "198 peça(s) extraída(s) em código em 1 página(s)"; com `aprovar`, o sistema gravou 198 novas e respondeu com a lista. Em uma segunda conversa (`s2`) a mesma pergunta já foi respondida pela base local, sem nova raspagem. O banco foi restaurado depois.

### 5.3 O que a mudança não resolve

- **Relevância.** O catálogo devolve 202 cartões para "palheta traseira" (portas, tampas, painéis), e a pessoa aprova uma lista de 198 linhas, onde só 1 ou 2 são palheta. Antes eram 24 a 54 linhas com os mesmos pontos. Filtrar pelo nome da peça pedida, em código, é o próximo passo e ficou de fora por decisão.
- **O leitor em código é específico do formato do site.** Se o endereço deixar de ter `/peca/<código>/`, ele devolve 0 peças e o sistema cai na reserva, lenta mas validada. O catálogo da Volkswagen (outro layout) ainda não foi inspecionado.
- **Só o tempo entre páginas e lotes é conferido**; uma única navegação ou chamada ao modelo já longa passa do teto (`LLM_TIMEOUT` cobre a segunda).

## 6. O corte silencioso do servidor (achado desta medição)

Quando o prompt **passa do contexto**, o Ollama o **corta para metade do contexto (mais 2 tokens), descartando o começo**, sem erro: só um aviso no log do servidor (`truncating input prompt`). Com o contexto padrão de 4096 o prompt cortado fica com 2.050 tokens; com 8192, 4.098. Abaixo do contexto nada é cortado. Teste da agulha (`SENHA-INICIAL` no começo do texto, `SENHA-FINAL` no fim; o modelo deve devolver cada uma):

| Caracteres (tokens contados) | Contexto 4096 | Contexto 8192 |
|---|---|---|
| 2.000 e 5.000 (até 3.721) | acha as duas | acha as duas |
| 8.000 (5.868) | **perde a inicial** e a instrução de sistema (responde em frase, não só a senha) | acha as duas |
| 12.000 a 73.000 | perde a inicial | perde a inicial |

O que isso significa para cada etapa, conferido no log do servidor:

- **`extrair`** (1.087 a 1.131 tokens) e **`ler_manual`** (até 2.307 tokens nas 18 dúvidas): ficam abaixo de 4096, **nunca foram cortados**. Os resultados das §3 e §4 e de [rag.md](rag.md) não dependem do contexto. (Uma leitura minha anterior, de que o leitor passava do limite em 10 de 18 chamadas, estava errada: contei as chamadas com 2.040 tokens ou mais, não as cortadas.)
- **`raspar`** (antes da mudança da §5): a chamada tinha 34.591 tokens e **sempre era cortada**, nos dois contextos. O modelo recebia **o fim da página**: 12% com 8192, 6% com 4096, **sem o prompt de sistema** (que fica no começo). Hoje o texto vai ao modelo, na reserva, em lotes de ~2.400 tokens, que nunca passam do limite.

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
- A raspagem varia muito entre rodadas (24, 54, 54, 34, 30 peças); só a rodada limpa está no log. O número de peças depende do quanto da página o servidor entrega e do acaso do modelo; o de códigos reais (13) não muda.
- `erro_ferramenta` (término por falha de ferramenta) nunca foi observado, então não está testado.
