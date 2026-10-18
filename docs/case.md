# 1. Tema: Assistente Informacional de Manutenção Automotiva

# 2.1 O problema

**Problema em uma frase:** propietários e mecânicos não confirmam no balcão se uma
peça de reposição é compatível com o veículo específico (modelo, ano e motorização),
o que gera compra errada, devolução e atraso no conserto.

**Quem sofre com ele hoje:** o mecânico de uma oficina de bairro de pequeno porte, 
que depende de identificar a peça certa rapidamente para não perder o cliente para a 
oficina concorrente.

**Onde o sistema roda:** dentro do atendimento de balcão ou telefone via Discord da
loja de autopeças. no momento em que o mecânico já verificou o problema do veículo
ou desmontou a peça antiga e precisa da referência de reposição. Quem aciona é o
próprio mecânico ou o balconista em nome dele.

**O que existe antes e depois:** antes, a entrada é a descrição do mecânico (modelo,
ano, motorização, defeito). Depois, a saída, código de peça e
fornecedor, alimenta o pedido de compra feito pelo balconista (fora do escopo do
agente, que é só informativo) e a instalação na oficina.

**O que acontece hoje sem o sistema:** o balconista consulta catálogo impresso ou
sistema interno básico, ou liga para o distribuidor quando não tem certeza. Uma
consulta simples resolve em minutos; um caso ambíguo pode levar até dias esperando
confirmação do fornecedor.

**As regras do domínio:**
- Compatibilidade depende de modelo + versão + motorização, não só modelo e ano
  — é a mesma lógica que o próprio setor usa para prever demanda de peças
  (Sistema de Informações de Frota e Demanda do Sindipeças).
- Desde 2019 as seguradoras não são obrigadas a usar peça original em sinistro
  parcial, o que ampliou o uso de peça paralela no mercado e, com isso, o risco de
  retrabalho quando a compatibilidade é mal verificada.
- Peça de segurança (freio, suspensão, direção) errada não é só prejuízo comercial,
  é risco real ao veículo, e pesa mais que economizar tempo na resposta.

**O que dá errado hoje:**
- Mecânico não informa a motorização exata de cara.
- Ano de fabricação na fronteira entre duas gerações do modelo.
- Peça descontinuada com substituta indicada pelo fabricante, a troca não é 1:1.
- Peça sem substituta exata: o certo é dizer "não encontrei", nunca aproximar.
- Frota brasileira envelhecendo com idade média de ~10 anos e 9 meses aumenta a 
  proporção de veículos com peças já descontinuadas ou fora de
  linha, exatamente os casos mais difíceis de resolver.

# 2.2 Identificação do Usuário

## 2.2.1 Quem são

<table>
    <thead>
        <tr>
            <th>Perfil</th>
            <th>O que deseja</th>
            <th>O que sabe</th>
            <th>O que ele pode fazer</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>Propietário</td>
            <td>
                <ul>
                    <li>
                        Comprar de forma autônoma uma peça compatível com seu veículo;
                    </li>
                    <li>
                        Consultar informações no manual do propietário, como períodos de manutenção, lista de peças próximas de serem trocadas, manutenções preventivas necessárias à ser realizadas, e dicas de condução.
                    </li>
                </ul>
            </td>
            <td>
                <ul>
                    <li>
                        nome da peça
                    </li>
                    <li>
                        modelo e ano de fabricação
                    </li>
                    <li>
                        motorização, km percorridos.
                    </li>
                </ul>
            </td> 
            <td>descreve, consulta</td>
        </tr>
        <tr>
            <td>Mecânico</td>
            <td>
                <ul>
                    <li>
                        Identificar peças e fluidos compatíveis com o modelo do carro.  
                    </li>
                </ul>
            </td>
            <td>
                <ul>
                    <li>
                        nome da peça
                    </li>
                    <li>
                        modelo e ano de fabricação
                    </li>
                    <li>
                        possíveis veículos que compartilham peças.
                    </li>
                </ul>
            </td>
            <td>descreve, pergunta, consulta</td>
        </tr>
    </tbody>
</table>

## 2.2.2 Como é a Interação

A interação será através de chatbot, é mais simples para acesso de ambos usuários à informação. O agente será acionado pelo usuário, portanto reativo. provavelmente haverá entorno de 3 à 4 interações até o sistema ter todos os dados necessários para inferir qual peça é a certa ao automóvel ou sanar a dúvida do usuário.
o retorno será uma tabela com o código da peça, modelo e ano de automóveis compatíveis com a peça ou a resposta extraída de um manual. Em caso de erro o agente apresentará a desculpa de não ter encontrado a peça para o automóvel.


# 2.3 Workflow do Agente
```
    1. ENTRADA          O solicitante descreve sua dúvida no chat
    2. COLETA           À depender da dúvida o sistema pergunta os dados necessários para construir a resposta  [decide: MODELO]
    3.1 CONSULTA_SQL    Em caso de a dúvida ser compatibilidade de peças e                                      [decide: CODIGO]                                  
                        houver registro anterior já existente em base local,
                        resgata a dúvida a partir da base local
                            Em caso positivo -> segue para o passo 5
                            Em caso negativo -> segue para o passo 3.2     
    3.2 CONSULTA        À depender da dúvida do usuário o sistema tem duas formas de realizar consulta.         [decide: MODELO]
                            Em caso de compatibilidade de peças -> Webscrapping
                            Em caso de outras dúvidas consulta em Manual -> Agente especializado em leitura
    4. REGISTRO     Em caso de verificação de compatibilidade de peças,                                         [decide:MODELO]
                    registra em uma base em sqlite e consulta 
                    modelos de automóveis que aceitam a peça em questão 
    5. APRESENTAÇÃO     Apresentação das informações levantadas                                                 [decide: MODELO]
                            Em caso de verificação de compatibilidade de peça -> apresenta tabela de modelos que compartilham a mesma peça. 
                            Em caso de outras dúvidas -> apresenta um texto de até 400 tokens com a resposta.
```

# 2.4 O sistema

## 2.4.1 O que o sistema faz

Assistente informacional que ajuda mecânicos e proprietários a identificar peças
compatíveis com o veículo e a consultar o manual do proprietário. Recebe a dúvida em
texto livre, verifica primeiro se já foi respondida antes (cache local), senão
consulta o webscrapping de catálogo de peças ou o manual indexado, conforme o tipo de dúvida, e devolve o
código da peça com os modelos compatíveis ou um resumo do manual. Não executa compra
nem reserva — é só informativo.

## 2.4.2 Nível de autonomia pretendido

**Agente simples**, não roteador puro e não workflow. Não é workflow porque nem todo
passo é determinístico — o sistema decide, olhando o texto livre, o que falta
perguntar e qual fonte consultar (Webscrapper, manual ou base local). Não é só roteador porque, depois de
rotear, ainda decide sozinho como formatar a resposta e o que registrar no SQLite.

## 2.4.3 Ferramentas disponíveis

| Ferramenta | O que faz | Leitura/Escrita | Reversível? | Com quem se comunica |
|---|---|---|---|---|
| `executar_webscrapping` | Realiza extração de todo um site de webcatálogo de uma determinada montadora | Escriya | — | Sites de Catálogos |
| `buscar_manual` | Recupera trecho relevante do manual do veículo | Leitura | — | Manuais em PDF indexados |
| `registrar` | Grava no cache os modelos dados estruturados em json | Escrita | Sim (é cache, pode ser sobrescrito) | SQLite local |
| `resgatar` | Resgata dados à partir do cache local | Leitura | - | SQLite local |

# 2.5 A Justificativa do negócio

## 2.5.1 Por que um Agente e não um software comum?

Porque a dúvida chega em texto livre e de dois tipos bem diferentes (peça x manual),
e o sistema precisa decidir, a cada conversa, o que falta perguntar e qual fonte
consultar. Um formulário fixo resolveria se o usuário sempre informasse tudo de
início — o que não acontece (ver 2.2).

## 2.5.2 Ganhos Esperados

| Eixo | Linha de Base (medir) | Alvo | Ganho |
|---|---|---|---|
| Tempo por tarefa | até alguns dias em casos ambíguos (cronometrar 10 casos reais) | poucos minutos | ~50% de redução (estimativa a confirmar) |
| Erro e retrabalho | taxa de devolução por peça errada hoje (levantar no histórico da loja) | taxa menor | ~90% de redução em devoluções (estimativa a confirmar) |

## 2.5.3 Ganhos do usuário

Mecânico: menos tempo parado esperando confirmação. Proprietário: mais autonomia
pra não comprar peça errada. Loja: menos devolução.

## 2.5.4 Custos para manter o sistema

Custo por chamada de modelo (ver item 3, análise de modelos), custo de manter o
índice dos manuais atualizado, e custo de hospedar o SQLite e a API de peças.

# 2.6 O Verificador

Conjunto de 20 a 40 casos rotulados à mão (modelo + ano + motorização → código de
peça correto, conferido contra o catálogo real) + regra de negócio: a peça devolvida
tem que bater exatamente com os campos informados pelo usuário.

# 2.7 Critério de Sucesso

Acerta a peça correta em pelo menos 32 de 40 casos rotulados, e nunca devolve peça de
segurança (freio, suspensão, direção) com confiança baixa.

# 2.8 Dados

## 2.8.1 Origem

Peças: Webscrapping de catálogos online. Manuais: PDFs reais de manutenção. Casos de teste:
simulados, incluindo os três exigidos — divergência (motorização informada não bate
com o catálogo), registro inexistente (peça sem substituta) e caso que não deve
disparar registro no SQLite (dúvida de manual, não de peça).

# 2.9 Dado Sensível

Nenhum. O sistema lida só com dado de veículo (modelo, ano, motorização) — não com
dado pessoal, financeiro ou de saúde.

# 2.11 O maior risco

| Risco | Plano B |
|---|---|
| Acesso à API pública de peças pode não ter cobertura suficiente pra todos os modelos testados | Realizar Webscrapping |
| Em caso do webscrapping não ser possível por conta da forma de desenvolvimento das páginas web | Utilizar dados mocados |


# 2.12 O que o domínio ensinou (complemento da Parte 2)

> **RASCUNHO para revisão.** Cada item traz **como sabemos**: ou foi **observado no sistema rodando** (com o arquivo onde está a prova), ou é **conhecimento de balcão** que só quem atende confirma. O que está marcado com **[confirmar]** não foi verificado por medição nenhuma e deve ser corrigido, ou apagado.

## 2.12.1 O vocabulário que ninguém de fora entende

| Termo | O que quer dizer aqui | Como sabemos |
|---|---|---|
| **Nº original GM** | o código da peça no catálogo da Chevrolet, o número que o mecânico leva ao balcão. No site ele também é o trecho do endereço do link (`/peca/19376259/…`) | observado: em 194 dos 202 cartões de uma busca os dois são iguais (`docs/prompts.md` §5) |
| **Aplicações** | os carros em que a peça serve, escritos **por geração e carroceria** ("Onix A Hatch", "Corsa B Sedan", "Prisma B"), e não por ano | observado no catálogo; o sistema guarda o texto como está e **não converte o ano do usuário para a geração** (ver 2.12.6) |
| **"Compatível com"** | equivalências de outras marcas para a mesma peça (BOSCH, VALEO, DYNA); aparece em poucos cartões (2 de 202) | observado (`docs/prompts.md` §5) |
| **Lado esquerdo / lado direito** | a peça é uma para cada lado, com código diferente e **o mesmo nome**; o lado aparece como linha à parte no cartão (107 de 202) | observado. O sistema agora acrescenta o lado ao nome da peça ("… (Lado esquerdo)"); antes, na lista de aprovação as duas pareciam repetidas |
| **Esgotado** | o cartão traz o aviso "Ooops, o estoque acabou" no lugar do preço (12 de 202); o código existe mesmo assim | observado. O sistema não guarda preço nem disponibilidade |
| **Caderno "Manutenção e garantia"** | publicação à parte, a que o manual do proprietário remete para os períodos de revisão | observado: manual do Fox 2015, páginas 176, 211 e 219 (`docs/rag.md` §3) |
| **Genuína, original, paralela** | as três categorias de peça da seção 2.1 | fontes da Parte 1 (`docs/fontes.md`, itens 1 a 4) |

## 2.12.2 As regras que o sistema teve de aprender

1. **Quem pede a peça fala o modelo do carro, não a montadora.** "Corsa 2008", e não "Chevrolet Corsa". O catálogo, porém, é **por montadora**: o sistema completa a montadora a partir do modelo com uma lista curta escrita pelo grupo (`MODELO_FABRICANTE`, em `src/nos.py`: Fox, Gol, Corsa, Onix, Palio, Corolla, Civic e mais alguns). Modelo fora da lista gera a pergunta "qual a montadora?". *Como sabemos:* observado, casos 2, 3, 4 e 6 de `dados/casos_extracao.json`. **[confirmar]** se a lista cobre os modelos que aparecem no balcão.
2. **A motorização é parte da identidade da peça** (já estava na seção 2.1) **e nem sempre vem na primeira frase.** O sistema pergunta, uma coisa de cada vez, em vez de escolher uma. *Como sabemos:* observado, cenários `incompleta` e `ambigua` (`docs/io.md`).
3. **O manual vale para um ano exato.** O Fox 2015 e o Fox 2020 respondem diferente (o de 2020 tem Android Auto e Apple CarPlay; o de 2015 não menciona nenhum dos dois). Um sistema que busca nos dois ao mesmo tempo devolve a resposta do carro errado. Por isso a escolha do manual é uma regra em código, por modelo **e** ano, e um Fox 2018 recebe "não tenho o manual do Fox 2018", sem aproximação para o mais próximo. *Como sabemos:* medido, `docs/rag.md` §2. **[confirmar]** quais anos cada edição do manual cobre (um Fox 2016 a 2019 hoje fica sem manual).
4. **"Peça sem código" é "não encontrei", nunca "mais ou menos".** No cadastro, uma roda de liga leve do Corsa existe, mas sem código ("N/A"). A resposta certa é dizer que a peça existe e que não há código, e mandar confirmar no balcão ou com o distribuidor. Antes de corrigirmos, o sistema respondia "código N/A" como se fosse resposta. *Como sabemos:* observado e corrigido, pergunta 2 de `docs/rag.md` §3.
5. **Pedido de compra, reserva, preço e "onde comprar" estão fora do escopo**, mesmo quando a frase cita peça e veículo, assim como **diagnosticar defeito** ("meu carro está fazendo um barulho na roda, o que pode ser?"). *Como sabemos:* regras de `src/prompts/procedural.md` e casos 18 a 22 de `dados/casos_extracao.json`; o diagnóstico (caso 21) é o único caso em que o modelo local ainda erra a classificação (`docs/prompts.md` §3).
6. **Dado novo do veículo vale mais que o lembrado.** Quem disse "Fox 2015" e depois diz "Fox 2020" quer o 2020, e o sistema avisa que mudou ("Considerei ano = 2020 (antes: 2015)"). Se o **modelo** muda, a motorização antiga é descartada, porque não é mais a do mesmo carro. *Como sabemos:* observado, cenário `divergencia`.

## 2.12.3 As exceções que decidiram a arquitetura

| Exceção | O que ela mudou no sistema | Como sabemos |
|---|---|---|
| **A palavra aparece, a resposta não.** "Trocar a embreagem" aparece 28 vezes no manual, só no uso do pedal. Um índice ou sumário também "menciona" o assunto sem respondê-lo | a leitura do manual tem uma regra explícita (índice e sumário nunca respondem) e um conjunto de 14 perguntas sem resposta no manual, para medir a falsa resposta (0 em 14) | medido, `docs/rag.md` §6.3 |
| **A regra tem exceção escondida no mesmo parágrafo.** Rebocar o Fox é permitido, **exceto** com a transmissão sem lubrificante; lavar com jato de alta pressão pode, mas com distância dos pneus | eram as duas perguntas que o modelo local errava na leitura do manual; viraram o teste da leitura (hoje respondem, `docs/rag.md` §3) | medido, `docs/rag.md` §3 e §6.2 |
| **O catálogo traz centenas de peças para uma busca de uma.** A busca "palheta traseira" devolveu 202 cartões (portas, tampas, painéis, mola…) | a lista que a pessoa aprova antes de gravar ficava enorme; o sistema agora fica só com as peças que têm as palavras do pedido no nome (198 viram 1 para a palheta). **Não conhece sinônimo**: "limpador de para-brisa" não casa com "Palheta" | observado, `docs/prompts.md` §5.3 e §5.4 |
| **O código existe no endereço do link, mas o modelo o inventava.** Lendo a página inteira, o modelo local devolvia códigos que não estavam nela (57% a 62%) | a leitura passou a ser em código; o modelo é só reserva e o código devolvido é conferido contra o texto | medido, `docs/prompts.md` §5 |
| **Peça esgotada continua sendo peça.** O cartão mostra o aviso de estoque no lugar do preço, mas o código serve | o sistema não confunde "esgotado" com "inexistente" porque não guarda disponibilidade | observado |

## 2.12.4 O passo que parecia um e são vários

A seção 2.3 descreve "consulta, registro e apresentação". Na prática, **achar a peça** são cinco passos, um deles de uma pessoa:

1. **Descobrir o carro**: modelo, depois a montadora (o catálogo é por montadora), ano e motorização, perguntando só o que falta.
2. **Olhar a base local** (uma consulta estruturada, sem modelo): se o carro já foi pesquisado, a resposta sai daqui.
3. **Ir ao catálogo** (leitura externa, sem gravar nada).
4. **Pedir a aprovação de uma pessoa** antes de gravar na base: um código errado gravado vira resposta futura para todo mundo, e desfazer exige apagar linhas. A pessoa aprova, rejeita ou **aprova editando** (remove linhas, corrige um código). Se ninguém responde em 24 h, **nada é gravado**.
5. **Responder** com a lista, a fonte e os avisos (o que foi lembrado, o que mudou, o que foi descartado).

*Como sabemos:* `docs/grafo.md` e `docs/humano.md`. **[confirmar]** quem, na loja, deve ser essa pessoa: hoje quem conversa com o sistema também aprova (limite declarado em `docs/arquitetura.md` §2.6).

## 2.12.5 O que mudou em relação ao que escrevemos na Parte 1

| Seção da Parte 1 | O que dizia | O que é hoje | Por quê |
|---|---|---|---|
| 2.4.2 Nível de autonomia | "agente simples" | **roteador**: o modelo classifica a intenção, decide se os trechos do manual respondem e, na reserva da raspagem, propõe peças; toda rota, texto e término é código | `docs/arquitetura.md` §3: a menor autonomia que resolve |
| 2.4.3 `executar_webscrapping` | **Escrita** | **Leitura**; a escrita é um passo à parte (`gravar`), só depois da aprovação | gravar dado de catálogo de terceiro sem revisão cria resposta errada permanente |
| 2.3 Workflow | quatro etapas marcadas "decide: MODELO" | três pontos de modelo (`extrair`, `ler_manual` e a reserva do `raspar`); o resto é código | `docs/prompts.md` |
| 2.11 O maior risco: "dados mocados" se o scraping falhar | plano B | o scraping funcionou no catálogo da Chevrolet; o da Volkswagen **ainda não foi inspecionado** | `docs/prompts.md` §5.3 |
| 2.5.2 Ganhos esperados: "~50% de tempo" e "~90% de devoluções" | estimativas a confirmar | **continuam sem medição**: o que medimos é a qualidade das respostas do sistema, não o tempo nem a devolução na loja | `docs/prompts.md`, `docs/rag.md` |
| 2.9 Dado sensível: "nenhum" | só dado do veículo | **o veículo lembrado fica ligado ao usuário** (memória semântica), e há remoção de dados sob pedido, com varredura de todas as estruturas | `docs/memoria.md` |

## 2.12.6 O que ainda não sabemos do domínio (perguntas para quem atende no balcão)

- **[confirmar]** O balconista digita como no caso 5 (*"me ve a palheta traseria do corsa 2008 motor 1.4"*)? Os casos de teste foram escritos pelo grupo, não colhidos de quem usa; isso muda o resultado, e o enunciado avisa.
- **[confirmar]** Qual a taxa real de devolução por peça errada hoje? Sem esse número, o "~90%" da seção 2.5.2 é um palpite.
- **[confirmar]** Os catálogos da Chevrolet e da Volkswagen são as fontes que a loja aceita como verdade, ou o distribuidor tem a última palavra?
- **[confirmar]** Em quais anos a geração do carro muda (o "Onix A" e o "Onix B")? O catálogo fala em geração; quem pede fala em ano. Sem essa tabela o sistema não sabe dizer se uma peça "Onix A Hatch" serve num Onix 2018.
- **[confirmar]** A peça de segurança (freio, suspensão, direção) deve ter um caminho próprio, como diz o critério de sucesso da seção 2.7? Hoje o sistema trata todas as peças do mesmo jeito, e a aprovação humana é o único freio.
