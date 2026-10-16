# Memória e esquecimento

Código: [src/memoria.py](../src/memoria.py), nós `lembrar`, `memorizar`, `confirmar_esquecimento` e `esquecer` em [src/nos.py](../src/nos.py), migrações em [src/registrador.py](../src/registrador.py), remoção em [src/esquecer.py](../src/esquecer.py) e verificação em [verificar_remocao.py](../verificar_remocao.py). Desenho do grafo em [grafo.md](grafo.md).

## 1. Os dois níveis, e o que ocupa cada célula neste case

| | Curto prazo | Longo prazo |
|---|---|---|
| **O que é** | a janela da execução corrente | o que atravessa execuções |
| **Conteúdo aqui** | prompt de sistema, as últimas mensagens da conversa, os trechos do manual recuperados | semântica (veículo do usuário), episódica (dúvidas de manual respondidas), procedural (regras escritas por uma pessoa) |
| **Persistido como** | **checkpoint** em `databases/checkpoints.sqlite`, endereçado por `thread_id` | tabela `memoria_semantica`, tabela `log_interacoes` mais índice por similaridade, e o texto `src/prompts/procedural.md` |
| **Ciclo de vida** | a conversa | acumula até a contradição ou a remoção |

### O que precisa estar no checkpoint para retomar sem repetir efeito colateral

O estado do grafo: `veiculo`, `intencao`, `nome_peca`, `duvida`, `turno`, `mensagens`, `candidatas`, `aprovacao` (com o carimbo de tempo da pausa) e a aprovação pendente em si. Os resultados brutos das ferramentas **não** entram. O que garante não repetir efeito: toda escrita é idempotente pela chave de conteúdo (`ja_existia`), então uma queda entre `gravar` e o checkpoint seguinte resulta em `ja_existia`, não em linha duplicada.

### Ordem de descarte quando o contexto não cabe

Orçamento declarado: `JANELA_TOKENS = 3000` por chamada (estimativa de caracteres ÷ 3,5). A chamada do manual, medida no servidor, usou **1.690 tokens** para 4.457 caracteres, então hoje há folga.

| Chamada | Sai primeiro | Nunca sai |
|---|---|---|
| `extrair` | as mensagens mais antigas (do atendente e do usuário, juntas); só as últimas 6 são enviadas | prompt de sistema com exemplos e regras aprendidas; a última mensagem do usuário |
| `ler_manual` | o trecho menos parecido com a dúvida (do fim da lista) | prompt, a dúvida, o trecho mais parecido |

Cortar histórico é seguro porque o veículo e a intenção ficam no **estado explícito**, não na janela. Sem essa decisão, o sistema truncaria no fim, que é onde está o mais recente.

**Prova (execução real, `JANELA_TOKENS=1300`, conversa de 5 mensagens do usuário):** a partir da 4ª, de 7 e depois 9 mensagens na conversa só 6 foram enviadas, e a extração continuou correta (Gol, 2012, 1.6, Volkswagen) porque os dados vieram do estado.

## 2. Fronteira entre as três estruturas, no case

| | checkpoint (Aula 05) | memória (Aula 08) | RAG (Aula 07) |
|---|---|---|---|
| escopo | uma conversa | todas as conversas | nenhum: é externo |
| propósito | **retomar** | **lembrar** | **consultar** |
| neste case | estado do grafo | veículo do usuário, dúvidas já respondidas, regras | manuais em PDF |
| forma | estado íntegro | fragmento selecionado | documento de terceiro |
| leitura | uma vez, no início | por chave (semântica) e por relevância (episódica) | por relevância, quando a dúvida exige |
| quem escreve | o sistema | o sistema (e uma pessoa, no procedural) | ninguém: corpus curado |

`pecas_automoveis` e `webcatalogos` **não são memória**: são conhecimento do mundo (compatibilidade de peças e endereços de catálogo), sem dono, gravados com aprovação humana. Entram no RAG como consulta estruturada.

**O que a recuperação por relevância traz que serializar tudo não traria:** a resposta que outra conversa, de outro usuário, já deu à mesma pergunta; serializar todos os checkpoints seria um arquivo morto em que não se acha "uma pergunta parecida". **O que ela deixa para trás:** a redação exata das conversas, os candidatos que não foram escolhidos e o contexto de cada turno.

## 3. As três memórias

| Tipo | O que guarda | Estrutura | Quem escreve | Quem lê | Volume por execução |
|---|---|---|---|---|---|
| **semântica** | o veículo do usuário: modelo, ano, motorização, montadora | chave-valor: `memoria_semantica`, chave `(user_id, 'veiculo')`; só se acrescenta | `memorizar`, depois de um turno `respondido` | `lembrar`, no turno 1 | ≤ 1 linha (~150 B) |
| **episódica** | dúvidas de manual sanadas, com a resposta | tabela `log_interacoes` (dado) e coleção `memoria_episodica` no Chroma (índice derivado) | `registrar_duvida`, só se a dúvida foi sanada | `consultar_base`, para dúvida de manual | ≤ 1 linha (~1 KB) e 1 vetor (384 números) |
| **procedural** | regras de "como fazer" | texto em `src/prompts/procedural.md`, uma seção por prompt (`## extrair`, `## ler_manual`), injetada só no prompt que a nomeia | **uma pessoa**, por commit | os dois prompts, sempre | 0 |

- **Buscar fato semântico por similaridade seria caro e impreciso quando uma chave resolve**, por isso o veículo é chave-valor.
- **A episódica tem duas peças, mas uma só fonte de verdade:** a tabela guarda a pergunta e a resposta; o índice guarda **só o vetor, o id da linha e modelo/ano**. Nem o texto da pergunta nem o `user_id` vão para o Chroma. Isso nasceu de um achado da validação (seção 6).
- **`lembrar` declara o que usou:** "Usei o veículo que você informou antes (Corsa 2008 1.4). Se mudou, é só dizer." O que o usuário disser depois vale mais (reducer `mesclar`). Se ele trocar de modelo, o ano e a motorização do carro anterior são descartados (`LIMPAR`) e isso também é declarado.
- **Procedural hoje tem 3 regras**, tiradas dos erros vistos nos testes: duas para `extrair` (pedido de compra é fora do escopo; mensagem sem pedido é indefinida) e uma para `ler_manual` (índice de manual não responde dúvida). Nenhuma pode citar um usuário. O arquivo tem uma seção por prompt e cada seção vai só para o prompt que a nomeia. A separação nasceu da suspeita de que as regras de classificar intenção atrapalhavam a leitura do manual; o teste não mostrou diferença além do ruído (10 de 18 sem regras, 10 com só a do índice, 11 a 12 com as três), então ficou por clareza, não por ganho medido.

## 4. Política de escrita

| Opção | Uso |
|---|---|
| o **código** extrai por regra | semântica e episódica: gravam o que já foi validado no estado, **depois** de `respondido` |
| o **humano** corrige | procedural: só por commit revisado |
| o **agente** decide | nenhuma |

- **Volume:** turnos que perguntam, recusam ou dão erro gravam **0**; um turno respondido grava até ~2,5 KB (estimativa).
- **Idempotência derivada do conteúdo, com `ja_existia` no retorno:** a chave é o hash dos campos da linha, normalizados (sem diferenciar maiúsculas ou espaços). O horário não entra na chave de `log_interacoes`, para a mesma dúvida respondida em horas diferentes ser a mesma linha. No veículo, repetir a declaração igual à mais recente devolve `ja_existia`; trocar e voltar grava de novo, porque a leitura pega o mais recente. O vetor usa o id da linha, então repetir apenas atualiza.
- **Não entra na memória:** mensagens cruas, preços, o que não foi `respondido`, qualquer dado pessoal além do `user_id` e as peças do catálogo (que ficam em `pecas_automoveis`).
- **A linha antiga que já existia** em `log_interacoes` (uma resposta negativa, "o manual não contém o cronograma", gravada em testes anteriores) recebeu o dono `legado` na migração, com data aproximada, e **não foi indexada**. É o exemplo concreto de memória envenenada: sai com `python src/esquecer.py --episodio 1`.

## 5. Esquecimento

| Causa | Decisão | Razão |
|---|---|---|
| **contradição** | **implementada** | semântica: só se acrescenta e a leitura pega o `max(created_at)`; o fato antigo fica. Episódica: entre perguntas equivalentes, a mais recente vence |
| **decaimento** | **não implementada** | o volume é pequeno (~2,5 KB por execução, na ordem de 2,5 MB para mil execuções) e o conteúdo não envelhece com o tempo: muda por declaração (coberto pela contradição) ou por troca de manual (a versão está no nome do arquivo) |
| **remoção** | **implementada**, por privacidade (`user_id` mais texto livre) e recuperação de incidente | um episódio envenenado sai pelo id, sem reconstruir o índice inteiro: vale para as duas razões e a memória envenenada não dura até uma janela de manutenção |

**Prova da contradição (execução real):** o usuário declarou Corsa 2008 1.4 e, em outra conversa, Onix 2018 1.0. A memória ficou com **2 declarações** (nada foi apagado) e a leitura seguinte devolveu o Onix. A resposta declarou "Considerei modelo = Onix (antes: Corsa)", e o mesmo para ano e motorização.

### Cobertura da remoção

O titular pode pedir pelo chat ("apague todos os meus dados"): o sistema conta o que será apagado, **para e pede confirmação** (`interrupt`), e só então apaga. Quem administra usa `python src/esquecer.py <user_id>`.

| Estrutura | O que há nela | Como sai |
|---|---|---|
| `memoria_semantica` (SQLite) | o veículo | `DELETE WHERE user_id` |
| `log_interacoes` (SQLite, ganhou `user_id`) | dúvidas e respostas | `DELETE WHERE user_id` |
| índice episódico (Chroma) | vetor, id da linha, modelo/ano | `delete` pelos ids das linhas do usuário, sem reindexar |
| **checkpoint** | mensagens e argumentos de cada passo | `delete_thread` de todo `thread_id` que começa com `<user_id>:` |
| **logs** | a fala do usuário e a resposta, por passo | remove `logs/<user_id>/` |
| **procedural** | nenhuma linha pode citá-lo | a varredura confirma; se achar, exige edição humana |
| compactação | páginas livres dos SQLite | `VACUUM` em `db.sqlite` e em `checkpoints.sqlite` |

- **A conversa em andamento é apagada por último e fora do grafo**: se o nó apagasse o próprio checkpoint, o framework o recriaria no passo seguinte. A CLI o remove depois que o grafo termina, e o log desta conversa é silenciado para a pasta não ser recriada.
- **O registro da remoção não tem dado pessoal:** `logs/_remocoes.jsonl` guarda só o hash do identificador e as contagens.
- **Fora da cobertura, declarado:** `pecas_automoveis` e `webcatalogos` (sem dado de pessoa), o índice dos manuais (documento de terceiro), as linhas com dono `legado` (não pertencem a um titular) e os logs de demonstração (identificadores sintéticos).

### Verificação independente

`python verificar_remocao.py <user_id>` não usa o código que apaga: varre todas as colunas de todas as tabelas de todos os SQLite (inclusive o checkpoint e o banco interno do Chroma), os **bytes brutos** de todos os arquivos de `databases/` (pega o que um `DELETE` deixa em páginas livres), os arquivos e os nomes em `logs/` e os prompts.

**Roteiro executado (usuário `usuario-teste-7f3a`):**

| Passo | Resultado |
|---|---|
| 1. gravar: uma conversa com peça e uma dúvida de manual | memória semântica e episódica preenchidas |
| 2. o comportamento mudou | conversa nova sem veículo respondeu sem perguntar nada; a pergunta repetida (outra grafia) foi respondida pela memória, similaridade 0,985, **1 chamada ao modelo** |
| 3. varredura antes | 18 ocorrências (checkpoint, `memoria_semantica`, `log_interacoes`, logs e bytes brutos); **nenhuma no Chroma** |
| 4. pedir a remoção e confirmar | `2 fato(s) do veículo, 1 dúvida, 1 item do índice, 4 conversa(s), 4 arquivo(s) de log` |
| 5. varredura depois | **0 ocorrências** |
| 6. o comportamento voltou | conversa nova perguntou o modelo; a mesma pergunta de manual não foi mais respondida pela memória |
| 7. cancelar | o pedido foi cancelado em outra execução e nada foi apagado (`esquecimento_recusado`) |

**Recuperação de incidente (execução real):** `python src/esquecer.py --episodio 2` removeu a linha e o vetor (`{'linhas': 1, 'vetores': 1}`); a pergunta seguinte voltou a ler o manual.

### O que a varredura achou na primeira versão

Na primeira versão a remoção apagava os vetores do Chroma e, mesmo assim, a varredura achou **resíduo**: o banco interno do Chroma (tabela `embeddings_queue`) guardava o texto da pergunta e o `user_id` das operações já apagadas, e o Chroma 1.5.9 (motor em Rust) não oferece como limpar esse log por fora. A correção foi de desenho: o Chroma passou a receber só o vetor, o id da linha e modelo/ano. Sem texto e sem identificador, o resíduo que sobra no log dele não identifica ninguém. Também passou a rodar `VACUUM` nos SQLite próprios, porque `DELETE` deixa os dados em páginas livres.

**Declaração honesta:** o vetor de uma pergunta apagada continua no log interno do Chroma até ele o compactar. Ele é só um vetor numérico com o id de uma linha que já não existe; não carrega texto nem identificador, mas não é zero.

## 6. Como a similaridade foi escolhida

O modelo de embedding (`all-MiniLM-L6-v2`) é centrado em inglês, e as perguntas são em português. A distância de cosseno entre a pergunta-base "Quais são os períodos de manutenção do meu Fox 2015?" e variações:

| Grupo | Distâncias | Observação |
|---|---|---|
| mesma pergunta (grafia, acentos, pontuação) | 0,000 a 0,088 | |
| paráfrases da mesma dúvida | 0,194 a 0,443 | **misturam-se** com o grupo seguinte |
| outras dúvidas do mesmo carro | 0,238 a 0,383 | "pressão dos pneus" ficou em 0,238 |

O corte ficou em **0,12** (`LIMIAR_EPISODIO`): acima de toda variação de grafia e abaixo da dúvida diferente mais próxima. O custo é assumido: **paráfrases não são reaproveitadas** (na validação, "Quando devo levar o Fox 2015 para revisar?" ficou a 0,305 e o manual foi lido). Prefere-se reler o manual a servir a resposta de outra pergunta. A amostra é pequena (14 pares, uma pergunta-base); um modelo de embedding multilíngue mudaria isso.

## 7. A conversa, e o que sobra dela

**O que identifica uma conversa.** O `thread_id` é `<user_id>:<sessão>`: o usuário do Discord da loja e a conversa. Mesma chave, mesma conversa; chave nova, histórico vazio. **Duas conversas abertas ao mesmo tempo pela mesma pessoa** têm `thread_id` diferentes (históricos separados) mas **a mesma memória de longo prazo**: se as duas gravarem um veículo, vale o de maior `created_at`.

**Onde o checkpoint é gravado.** Em arquivo (`databases/checkpoints.sqlite`, fora do git), então a conversa e a aprovação pendente sobrevivem ao fim do processo. Limitação: o arquivo é local.

**O que acontece quando a janela enche.** A política da seção 1: sai a mensagem mais antiga primeiro; o que se perde é a redação antiga, não os dados, que estão no estado.

**O que passa da conversa para a memória de longo prazo.** O veículo (semântica) e a dúvida de manual respondida (episódica). **Nada mais.**

## 8. Limites e pendências

- **A busca no manual foi corrigida** (busca textual no lugar da vetorial; ver [rag.md](rag.md)) e o ciclo episódico completo passou a ser exercitado pelo grafo: uma dúvida sanada é gravada (linha e vetor) em `registrar_duvida` e, em outra conversa, a mesma pergunta é respondida pela memória com 1 chamada ao modelo (similaridade 0,955). **Parafrasear a pergunta não reaproveita a memória** (corte de 0,12), por escolha de projeto.
- **Primeiro acesso lento:** carregar o modelo de embedding custa ~7 s por processo na primeira consulta de manual, por causa da busca na memória episódica (a busca no manual em si não o carrega).
- **Perfil do veículo pode ficar velho** (o usuário trocou de carro sem avisar): o sistema declara que o usou e o usuário corrige; não há expiração.
- **A leitura da episódica é global:** a resposta de uma dúvida de manual serve a qualquer usuário (o conteúdo vem do manual). O `user_id` fica só na tabela, para a remoção.
