# RAG como memória consultável

Código: [src/leitor_manual_pdf.py](../src/leitor_manual_pdf.py) (leitura do manual), [src/busca_textual.py](../src/busca_textual.py) (BM25), [src/registrador.py](../src/registrador.py) (consulta estruturada), [src/memoria.py](../src/memoria.py) (busca vetorial da memória episódica). Dados: [dados/perguntas_rag.json](../dados/perguntas_rag.json). Reprodução: `python avaliar_rag.py perguntas` e `python avaliar_rag.py manual 3`.

**Proveniência dos números.** Todas as medições abaixo são de 2026-10-16, com o modelo local `qwen2.5:7b` (Ollama), sobre o commit `97aea9b` **mais alterações ainda não commitadas** (o log da avaliação registra só o commit base). O modelo não é determinístico nem com `temperature=0`: o mesmo código deu 10, 11 e 12 respostas em rodadas diferentes. Por isso aparecem faixas.

## 1. As formas de recuperar, e as que o case usa

| Forma | Com o quê | O que ela responde no case |
|---|---|---|
| **consulta estruturada** | SQLite: `pecas_automoveis`, `webcatalogos`, `log_interacoes` | o **registro**: código de uma peça de um veículo (perguntas 1 e 2) |
| **busca textual** | BM25 próprio (~50 linhas, sem dependência), sobre os trechos do manual | o **termo**: dúvidas do manual do proprietário, que citam termos do próprio manual (3, 4, 5, 6, 10) |
| **busca vetorial** | ChromaDB, `all-MiniLM-L6-v2` (384 dimensões, cosseno), só na memória episódica, com corte de distância 0,12 | o **assunto repetido**: uma pergunta já respondida antes (7) |
| grafo | não implementado | a **relação** peça → veículos (8) |
| agregação | não implementada | os **temas recorrentes** (9) |

**"O RAG é vetorial ou é banco de dados?"** Os dois, mais a busca textual. Cada forma ficou onde o dado pede: SQL para o catálogo de peças, busca por termo para o manual, vetor só para reconhecer pergunta repetida.

**Por que o manual é busca textual, e não vetorial.** Foi uma decisão tomada por medição (seção 5): as dúvidas de manual usam os termos do manual ("argola", "tanque", "bateria"), e o único modelo de embedding disponível (`all-MiniLM-L6-v2`) é treinado em inglês: para "como abastecer o veículo" ele não trouxe nenhuma página de abastecimento entre os 15 primeiros resultados. A busca por termo acertou o trecho certo bem mais cedo (16 de 20 consultas entre os 5 primeiros, contra 13 de 20).

## 2. O corpus, e o que entra nele

| Documento | De onde vem | Quem mantém | Com que frequência muda |
|---|---|---|---|
| `Volkswagen_Fox_2015.pdf` (335 páginas, 4,7 MB) | manual de instruções do proprietário, editado pela Volkswagen (fechamento 22.08.2014, edição 09.2014) | o grupo copia o PDF para `databases/manuais/`; a Volkswagen o publica | uma vez por geração ou revisão do manual |
| `Volkswagen_Fox_2020.pdf` (300 páginas, 7,1 MB) | idem (fechamento 07.02.2020, edição 05.2020) | idem | idem |
| `pecas_automoveis` (SQLite) | catálogos web das montadoras, por scraping, com aprovação humana antes de gravar | o fluxo de aprovação ([humano.md](humano.md)) | cresce a cada raspagem aprovada; **preço e disponibilidade não são guardados** |
| `webcatalogos` (SQLite) | endereço e regra de busca de cada catálogo, definidos em `Registrador._default_data` | o grupo | raramente |

**Quando reconstruir o índice.** O corpus de manuais muda **por manual novo**, não por edição. Cada PDF é indexado uma vez, na primeira pergunta sobre ele, e o índice é reaproveitado. Na prática: indexar o manual de 2020 levou **~60 s** (300 páginas) e o do repositório, de 2015, já vem indexado. **O índice de 2020 não está versionado:** na primeira pergunta sobre um Fox 2020 há essa espera. A busca textual não precisa de reindexação própria: monta em memória, em 0,4 s, a partir dos trechos já cortados.

### O documento de outra versão (o "revogado")

O manual de 2020 faz o papel do documento que **não vale** para quem tem um Fox 2015: as respostas diferem. "Android Auto", "Apple CarPlay" e "App-Connect" aparecem 21, 16 e 17 vezes no manual de 2020 e **nenhuma** vez no de 2015.

| Cenário (pergunta: "O meu Fox tem Android Auto e Apple CarPlay?") | Resultado medido |
|---|---|
| **Corpus misturado**, sem controle de versão (os dois manuais na mesma busca) | os **6 de 6** trechos devolvidos vieram do manual de 2020. O dono de um Fox 2015 receberia um "sim" **errado**, porque nada na busca sabe que o documento não vale para o carro dele |
| **Sistema real**, dono de Fox 2015 (manual escolhido por modelo e ano) | recusou: "O manual não menciona Android Auto ou Apple CarPlay." |
| **Sistema real**, dono de Fox 2020 | respondeu a partir do manual de 2020 (páginas 141, 143, 144) |
| **Sistema real**, dono de Fox 2018 | `escolher_manual` devolve vazio: "Não tenho o manual do Fox 2018"; **não aproxima** para o mais próximo |

**Achado:** se o sistema não sabe qual versão vale para o veículo, o erro não vem da recuperação e nenhum ajuste de busca o conserta. A solução é **curadoria**: a versão está no nome do arquivo e a escolha do manual é uma regra em código (`escolher_manual`), antes de qualquer busca. **Limite declarado:** a regra exige modelo e ano no nome do PDF; um Fox 2016 a 2019, que o manual de 2015 ou o de 2020 pode cobrir, hoje fica sem manual. Dizer quais anos cada edição cobre é decisão de quem conhece o domínio.

## 3. As dez perguntas, e o corte

O conjunto está em [dados/perguntas_rag.json](../dados/perguntas_rag.json), cada pergunta com o trecho que a responde. **Foram escritas a partir do case e dos testes do grupo, não coletadas de usuários reais**, e precisam de revisão de quem conhece o balcão: o enunciado avisa que perguntas vindas de quem usa mudam o resultado.

| # | Pergunta | Forma | A resposta está em | Exceção? |
|---|---|---|---|---|
| 1 | Qual o código da palheta traseira do Corsa 2008 1.4 da Chevrolet? | consulta estruturada | `pecas_automoveis`, linha 2: código 93356933 | |
| 2 | Qual o código da roda de liga leve do Corsa 2008 1.4 da Chevrolet? | consulta estruturada | `pecas_automoveis`, linha 7: a peça existe, o código é "N/A" | **sim:** peça sem código, que o case manda tratar como "não encontrei", nunca aproximar |
| 3 | Qual a capacidade do tanque de combustível do meu Fox 2015? | busca textual | manual 2015, p. 197: "aproximadamente 50 litros, dos quais aproximadamente 7 litros de reserva" | |
| 4 | O meu Fox 2015 pode ser rebocado se a transmissão estiver sem lubrificante? | busca textual | manual 2015, p. 313: "Quando o veículo não pode ser rebocado? Se, devido a um dano, a transmissão do veículo não contiver mais lubrificante" | **sim:** a regra geral permite rebocar com as rodas dianteiras levantadas |
| 5 | Posso lavar o meu Fox 2015 com lavador de alta pressão? | busca textual | manual 2015, p. 228: "Manter distância suficiente entre o bico do jato e os pneus" | **sim:** pode, com distância e sem jato circular nos pneus |
| 6 | Quais são os períodos de manutenção do meu Fox 2015? | busca textual | **não está no corpus:** o manual só remete ao caderno "Manutenção e garantia" (pp. 176, 211, 219) | |
| 7 | Quantos litros cabem no tanque do meu Fox 2015? | busca vetorial (episódica) | a mesma da pergunta 3, se ela foi gravada | |
| 8 | Que carros usam a palheta traseira ACDelco de código 93356933? | grafo | `carros_compatíveis` da linha 2, uma lista em texto numa coluna | |
| 9 | Quais são as dúvidas de manual mais perguntadas? | agregação | `log_interacoes` (um `GROUP BY`) | |
| 10 | O meu Fox 2020 tem Android Auto e Apple CarPlay? | busca textual | manual 2020, pp. 141, 143, 144 | |

A classificação **não concentrou tudo em "assunto"**: 2 consultas estruturadas, 5 buscas textuais, 1 vetorial, 1 relação e 1 agregação. As perguntas 8 e 9 não têm rota no grafo hoje (o grafo só entende `PECA` e `MANUAL`); estão no conjunto para registrar a lacuna.

### Resultado das dez no grafo real

Execução de **2026-10-18**, commit `b1880be`, árvore limpa, `qwen2.5:7b`, contexto do Ollama em 8192, prompt do leitor **sem a regra 5** (`python avaliar_rag.py perguntas`, um usuário, uma conversa por pergunta). Os logs estão em `logs/rag-avaliacao/q1` a `q10` (cada `trajetoria.jsonl` guarda as duas execuções, a de 2026-10-16 e esta, cada uma começando por um evento `inicio` com commit e hash dos prompts) e o resumo em `logs/rag-avaliacao/resultado.json`.

| # | Resultado | Situação | Fonte |
|---|---|---|---|
| 1 | **ok:** "Palheta traseira ACDelco — código 93356933" | respondido | base local |
| 2 | **ok:** "Encontrei 'Roda de liga leve' ... mas sem código cadastrado. Sem o código não indico a peça" | sem_base | base local |
| 3 | **ok:** "aproximadamente 50 litros" (páginas 195 a 197) | respondido | manual |
| 4 | **ok:** "não pode ser rebocado se a transmissão estiver sem lubrificante" (páginas 158, 312, 313, 317) | respondido | manual |
| 5 | **ok pelo critério automático, resposta fraca:** "é possível lavar com lavador de alta pressão, mas é necessário seguir as orientações de segurança e utilizar a pressão e distância corretas" | respondido | manual |
| 6 | **ok:** recusou, por ser fora do corpus | sem_base | manual |
| 7 | **ok:** respondeu 50 litros, **lendo o manual de novo**, não pela memória | respondido | manual |
| 8 | fora da cobertura: perguntou a motorização | faltam_dados | — |
| 9 | fora da cobertura: perguntou se é peça ou manual | faltam_dados | — |
| 10 | **ok:** respondeu a partir do manual de 2020 (66 s: inclui a indexação do manual) | respondido | manual |

**8 de 10; 8 de 8 entre as que o grafo cobre.** Na execução anterior (2026-10-16, commit `97aea9b`, prompt do leitor com a regra 5) foram **6 de 10** (6 de 8): as perguntas 4 e 5 falharam, com "o manual não especifica". O defeito encontrado na pergunta 2 foi **corrigido** no meio desta frente: antes, o sistema respondia "Roda de liga leve — código N/A" com `suficiencia=True`; agora uma peça sem código vira `sem_base`.

**Não atribuo a melhora de 6 para 8 só ao prompt.** Entre as duas execuções o commit mudou de `97aea9b` para `b1880be`, que inclui a busca textual (BM25, `k=6`) e outras mudanças da memória. A atribuição ao prompt vem da medição isolada da §6.2.1 (mesmas 32 perguntas, 3 rodadas, só a regra 5 diferente: de 11 para 15 com o fato). Cada pergunta do conjunto roda uma vez, então 8 de 10 é uma faixa, não um número.

**O diagnóstico das falhas 4 e 5 da execução anterior** (leitura, não busca): na 4 o trecho com a resposta era o **1º** do ranking; na 5 era o 2º, o 5º e o 8º. O modelo de 7 bilhões de parâmetros, com a frase "a transmissão não contiver mais lubrificante" na frente, concluía que o manual não especifica. Hoje as duas respondem. **A resposta da 5 é genérica** ("distância corretas"), sem dizer o que o manual diz (manter distância dos pneus, sem jato circular nelas): passa no critério automático, não numa leitura crítica. A 5 ainda depende de um trecho fragmentado, porque o PDF tem duas colunas e a extração intercala as linhas. Não medi com o `gpt-oss-120b`.

**A pergunta 7 não foi reaproveitada da memória**, por escolha de projeto: o corte de similaridade é 0,12 e esta paráfrase ficou mais longe (seção 6 de [memoria.md](memoria.md)).

### O corte (busca vetorial) e a estratégia para a busca textual

O corte e o `k` valem para qualquer busca que parta o documento. A busca textual também precisa de trechos, então a decisão existe.

- **Estratégia:** `RecursiveCharacterTextSplitter`, 800 caracteres, **sem sobreposição**, separando por parágrafo, depois linha, depois espaço.
- **Por que:** o PDF não tem estrutura aproveitável. O extrator entrega texto corrido, com hifenização ("veí- culo") e duas colunas intercaladas, então cortar por título ou por artigo, que seria o ideal para um regulamento, não é possível. 800 caracteres são ~230 tokens: seis trechos cabem na janela de leitura (~1,4 mil tokens) com folga.
- **Medido no índice atual:** 1.172 trechos; mediana de 770 caracteres; 23 com menos de 80 e 80 com menos de 200 (7%).
- **O que se perde:** sem sobreposição, uma frase cortada na fronteira entre dois trechos pode perder o contexto. Não foi medido o quanto isso custa.
- **Páginas ignoradas:** as de capa e índice. Medido nos PDFs: manual 2015, índice nas páginas 4-5, conteúdo a partir da 6; manual 2020, índice nas 6-8, conteúdo a partir da 9. O filtro antigo (`página > 5` para os dois) deixava o índice do manual de 2020 entrar na busca.

## 4. O `k`

**`k = 6`.** Medido com o prompt de leitura anterior e busca textual: com 15 trechos, 5 das 20 leituras tiveram o JSON cortado pelo teto de saída e só 3 de 18 dúvidas foram respondidas; com 6 trechos, 6 de 18 e 1 corte. Com o prompt atual, 6 trechos dão 10 a 12 de 18. **Não comparei `k = 6` com `k = 15` sob o prompt atual**, então o valor está justificado pela medição anterior e pelo custo (mais trechos, mais contexto e mais saída para o modelo de 7B), não por um teste direto de hoje.

`k` alto esconde defeito de índice e enche a janela; `k` baixo perde a resposta. Para o `gpt-oss-120b`, com janela maior e leitura mais forte, o valor ótimo provavelmente é outro.

## 5. Onde a recuperação entra no laço

Escolha: **etapa decidida por código, não ferramenta do agente.** O nó `ler_manual` é alcançado por uma aresta condicional que o **código** decide (`rota_pos_base`): intenção `MANUAL`, dados completos e a memória episódica sem resposta. O modelo não decide quando buscar.

**Por que mudou.** Antes, `read_manual_pdf` era uma ferramenta que o modelo escolhia chamar; nos testes ele respondia sem consultar, escrevia a chamada como texto e gastava voltas. Hoje o conhecimento fica disponível pela regra, e o modelo só lê o que foi buscado. O custo é perder a flexibilidade de o modelo buscar duas vezes com consultas diferentes.

**Chamadas de recuperação por execução (medido, avaliação das dez perguntas):**

| Tipo de pergunta | Buscas | Chamadas ao modelo |
|---|---|---|
| peça já na base | 1 SQL | 1 (a extração) |
| manual, memória episódica sem resposta | 1 vetorial (episódica) + 1 BM25 | 2 (extração + leitura) |
| manual repetido, memória responde | 1 vetorial (episódica) | 1 |
| fora do escopo, pedido incompleto | 0 | 1 |

**Buscas inúteis.** A busca na memória episódica rodou nas 6 perguntas de manual da avaliação (3, 4, 5, 6, 7, 10) e **não acertou em nenhuma** (0 de 6): como o conjunto não repete pergunta, ela é custo puro nesta avaliação (cerca de 7 s na primeira vez, para carregar o modelo de embedding, e ~1 s depois). No teste de repetição do fluxo (mesma pergunta em outra conversa) ela acertou e poupou a leitura. Quanto ela vale depende de quanto as pessoas repetem perguntas, que **não foi medido** com usuários reais.

## 6. Medição da busca e da leitura

### 6.1 Só a busca: o trecho certo está entre os `k` primeiros?

20 consultas (10 assuntos, 2 formulações cada) com página-gabarito conferida no texto do PDF. "Acerto @5" = algum dos 5 primeiros trechos vem de uma página que contém a resposta.

| Método | @5 | @10 | @15 | MRR |
|---|---|---|---|---|
| A. busca vetorial atual (MiniLM, 800/0) | 13/20 | 16/20 | 16/20 | 0,58 |
| B. BM25 sobre os mesmos trechos | 16/20 | 16/20 | 16/20 | 0,66 |
| C. BM25 com a hifenização corrigida | 16/20 | 16/20 | 16/20 | 0,66 |
| D. híbrido (vetorial + BM25) | 14/20 | 15/20 | 16/20 | 0,61 |

Pôr "do meu Fox 2015" na consulta derruba a busca vetorial de 16 para 12 acertos entre os 10 primeiros; a textual quase não muda (16 e 16). Por isso a consulta **tira o veículo** (`Bm25.buscar(..., ignorar=veículo)`). A correção de hifenização não mudou nada neste conjunto, mas a tokenização a mantém.

### 6.2 A cadeia inteira: busca mais leitura pelo modelo

18 dúvidas com resposta no manual e 14 sem. Critério de acerto: a dúvida foi dada como respondida (`sanada`) e o resumo contém o fato esperado (conferido por expressão regular, grosseira). Prompt de leitura permissivo.

| Variante | Respondeu | Com o fato | Recusou o que não está no manual |
|---|---|---|---|
| **antes:** vetorial, com veículo, k=15 (prompt rígido) | 3/18 | 3/18 | 2/2 |
| vetorial, com veículo, k=15 | 5-6/18 | 5-6/18 | 2/2 |
| vetorial, sem veículo, k=15 | 9/18 | 9/18 | 2/2 |
| busca textual, sem veículo, **k=6** | 13-14/18 | 13/18 | 2/2 |
| híbrido, sem veículo, k=8 | 13/18 | 13/18 | 2/2 |

(Esta tabela vem do experimento de laboratório, com o leitor simulado fora do sistema, e só tinha 2 perguntas sem resposta.) **No sistema real, com o código final**, em 5 rodadas: **10 a 11 de 18 respondidas, 9 a 10 com o fato esperado, 14 de 14 recusadas e 0 falsas respostas** (`python avaliar_rag.py manual 3`: 11, 11, 11). A diferença para o laboratório (13-14) não é erro de contagem: no sistema real o prompt do leitor e a pergunta são os de produção, e o modelo varia entre rodadas. A faixa honesta do sistema real é a segunda. Remedido em 2026-10-18 como base da ablação do leitor ([prompts.md](prompts.md) §4, contexto do Ollama em 8192, 2 rodadas): 11 e 12 respondidas, 10 e 11 com o fato, 14 de 14 recusadas, 0 falsas: a mesma faixa. O servidor não corta o prompt do leitor (até 2.307 tokens, [prompts.md](prompts.md) §6).

### 6.2.1 O prompt do leitor sem a regra 5 (2026-10-18)

A ablação das regras do prompt ([prompts.md](prompts.md) §4) mostrou que a regra 5 (resumo com no máximo 80 palavras e uma frase sobre o que falta) prejudicava a leitura. Ela foi removida e a medição repetida em 3 rodadas, contra a versão anterior na mesma sessão (`python avaliar_rag.py manual 3 <rótulo>`, logs `manual-com-regra5.json` e `manual-sem-regra5.json`):

| Prompt do leitor | Respondeu | Com o fato | Recusou o que não está no manual | Falsas respostas |
|---|---|---|---|---|
| com a regra 5 (anterior) | 12, 11, 11 de 18 | 11, 10, 10 | 14 de 14 | 0 |
| **sem a regra 5 (atual)** | **16, 16, 16 de 18** | **15, 15, 15** | **14 de 14** | **0** |

5 perguntas passaram a acertar, nenhuma deixou de acertar, e as 14 sem resposta (inclusive as do grupo "termo presente, resposta ausente") continuam recusadas. **A faixa honesta do sistema real passa a ser 16 de 18 respondidas e 15 com o fato** (antes, 10 a 12 e 9 a 11); a tabela acima e o parágrafo anterior descrevem o prompt antigo. Seguem erradas, nas 3 rodadas, "Como substituir a bateria do veículo?", "Como desembaçar o vidro de trás?" e "O pó que sai do airbag é perigoso?". A medição **sem** a regra 5 foi refeita com a árvore limpa (commit `b1880be`, `codigo_limpo: true`) e deu o mesmo, 16/15/0 nas 3 rodadas (`manual-sem-regra5.json`); o controle **com** a regra 5 (`manual-com-regra5.json`) tem o carimbo sujo, só pelo script de avaliação. As 10 perguntas pelo grafo foram refeitas na §3.

### 6.3 Falsa resposta, o risco que o prompt permissivo poderia ter piorado

O prompt aceita passos, listas e advertências como resposta, e isso poderia levar o modelo a "sanar" dúvidas que o manual não responde. Foram **14 perguntas** sem resposta no manual, em três grupos:

| Grupo | Exemplos | Recusou |
|---|---|---|
| assunto ausente | preço do carro, receita de bolo, Copa de 2014, piloto automático, IPVA, financiamento | 8/8 |
| **termo presente, resposta ausente** | "como trocar a embreagem" (a palavra aparece 28 vezes, só no uso do pedal), "como trocar as pastilhas" (aparece 28 vezes, só em advertência de desgaste) | 4/4 |
| caderno externo | períodos de manutenção, intervalo de revisão | 2/2 |

**0 falsas respostas em 14**, em todas as rodadas. O segundo grupo é o teste duro (o termo existe, a resposta não) e passou. **A amostra é pequena** (14 perguntas, um manual, um modelo): é evidência, não garantia.

## 7. O que ficou de fora, e os limites

- **Uma única fonte de medição:** 18 + 14 perguntas, um manual, o modelo `qwen2.5:7b`. Não foram medidos o `gpt-oss-120b` nem o manual de 2020 em volume. **Um indício de que o de 2020 é mais difícil:** no cenário `divergencia` ([io.md](io.md)) a capacidade do tanque do Fox 2020, que está numa tabela de "Capacidades" (p. 277, "aproximadamente 50 litros"), **não foi trazida** e o sistema recusou. É uma recusa honesta, mas a resposta existe.
- **Embedding multilíngue não foi testado.** Foi descartado por custo (471 MB de download por modelo, ~2 min para reindexar por manual) antes de medir. Como o mesmo modelo sustenta a memória episódica, trocá-lo exigiria remedir o corte de 0,12.
- **A busca textual falha com sinônimos** ("revisão" contra "manutenção") e o gabarito quase não testa isso.
- **Extração do PDF em duas colunas:** a leitura intercala linhas de colunas diferentes, o que atrapalha o modelo (pergunta 5). Extrair por layout exigiria reindexar.
- **O scraper aceita qualquer texto como código de peça.** As peças esgotadas do catálogo da Chevrolet vêm com o aviso "Ooops, o estoque acabou" no lugar do código (3 de 26 candidatas, nas três raspagens da rodada de 2026-10-16) e seguem para a aprovação e, aprovadas, para a base. Falta validar a forma do código antes de mostrar a lista; ver [arquitetura.md](arquitetura.md) §4.
- **Perguntas 8 e 9** não têm rota no grafo; uma consulta estruturada por código de peça e uma agregação sobre `log_interacoes` resolveriam, e ficam como próximos passos.
- **Anos cobertos por cada manual** (seção 2): decisão de domínio pendente.
