# 1. Tema: Assistente Informacional de Manutenção Automotiva

### 2.1 O problema

**Problema em uma frase:** consumidores e mecânicos não confirmam no balcão se uma
peça de reposição é compatível com o veículo específico (modelo, ano e motorização),
o que gera compra errada, devolução e atraso no conserto.

**Quem sofre com ele hoje:** o mecânico de uma oficina de bairro de pequeno porte, 
que depende de identificar a peça certa rapidamente para não perder o cliente para a 
oficina concorrente.

**Onde o sistema roda:** dentro do atendimento de balcão, telefone ou WhatsApp da
loja de autopeças. no momento em que o mecânico já verificou o problema do veículo
ou desmontou a peça antiga e precisa da referência de reposição. Quem aciona é o
próprio mecânico ou o balconista em nome dele.

**O que existe antes e depois:** antes, a entrada é a descrição do mecânico (modelo,
ano, defeito, às vezes foto da peça antiga). Depois, a saída, código de peça e
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
- Existem três categorias de peça, com implicação direta de confiabilidade: **genuína**
  (fabricada pela montadora, vendida em concessionária), **original** (fornecedor
  homologado, marca própria, vendida no varejo) e **paralela/genérica** (terceiros,
  sem homologação da montadora, mais barata e com variação de qualidade).
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

## 2.1.2 Contexto

### 2.1.2.1 Acionamento do Sistema

O sistema poderá ser acionado tanto pelo propietário quanto pelo mecânico, tendo como objetivo sanar dúvidas identificação de peças quanto apresentar informações disponibilizadas em manuais do automóvel. 

### 2.1.2.2 input e output

Como input o sistema necessita do nome de modelo do veículo, ano de fabricação, carroceria e motorização, o usuário que irá ceder inicialmente essa informação e a partir destes dados, o sistema apresentará em formato de tabela o código de identificação da peça e uma lista de automóveis também compatível com tal peça, ou apresentará em formato de texto corrido um resumo de orientações a partir da informação extraída do manual do veículo.

### 2.1.2.3 Situação Atual

Hoje, a consulta funciona principalmente através da leitura de manuais técnicos desenvolvidos pela montadora para cada modelo de automóvel. O que pode fazer com que propietários não atentos à ler com cuidado o manual comprar peças erradas.
Em quanto ao vendedor/mecânico, não havendo uma base de dados confiável, desenvolvida internamente, fica suscetível à realizar a compra na base do achismo.

### 2.1.2.4 Regras do Domínio

A peça recomendada para a instalação no automóvel exige a leitura do manual. Muitos automóveis compartilham peças, então a base de dados explorada (Manuais) pode ser maior que apenas a base disponibilizada pelo fabricante para o veículo em específico. Uma das principais regras é respeitar o ano/modelo do veículo.

### 2.1.2.5 O que dá Errado Hoje

A incerteza no momento de compra de peças de substituição em carros vendidos no mercado nacional, causa o aumento de custos e possível maior demora para realização de serviços em oficinas de pequeno/médio porte.


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
                        motorização, carroceria do veículo, km percorridos.
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

A interação será através de chat, é mais simples para acesso de ambos usuários à informação. O agente será acionado pelo usuário, portanto reativo. provavelmente haverá entorno de 3 à 4 interações até o sistema ter todos os dados necessários para inferir qual peça é a certa ao automóvel ou sanar a dúvida do usuário.
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
                            Em caso de compatibilidade de peças -> API
                            Em caso de outras dúvidas consulta em Manual -> Agente especializado em leitura
    4. REGISTRO     Em caso de verificação de compatibilidade de peças,                                         [decide: MODELO]
                    registra em uma base em sqlite e consulta 
                    modelos de automóveis que aceitam a peça encontrada 
    5. APRESENTAÇÃO     Apresentação das informações levantadas                                                 [decide: MODELO]
                            Em caso de verificação de compatibilidade de peça -> apresenta tabela de modelos que compartilham a mesma peça. 
                            Em caso de outras dúvidas -> apresenta um texto de até 400 tokens com a resposta.
```

# 2.4 O sistema

## 2.4.1 O que o sistema faz

Assistente informacional que ajuda mecânicos e proprietários a identificar peças
compatíveis com o veículo e a consultar o manual do proprietário. Recebe a dúvida em
texto livre, verifica primeiro se já foi respondida antes (cache local), senão
consulta a API de peças ou o manual indexado, conforme o tipo de dúvida, e devolve o
código da peça com os modelos compatíveis ou um resumo do manual. Não executa compra
nem reserva — é só informativo.

## 2.4.2 Nível de autonomia pretendido

**Agente simples**, não roteador puro e não workflow. Não é workflow porque nem todo
passo é determinístico — o sistema decide, olhando o texto livre, o que falta
perguntar e qual fonte consultar (API ou manual). Não é só roteador porque, depois de
rotear, ainda decide sozinho como formatar a resposta e o que registrar no SQLite.

## 2.4.3 Ferramentas disponíveis

| Ferramenta | O que faz | Leitura/Escrita | Reversível? | Com quem se comunica |
|---|---|---|---|---|
| `consultar_cache` | Verifica se a dúvida já foi resolvida antes | Leitura | — | SQLite local |
| `consultar_api_pecas` | Busca peça compatível por modelo/ano/motorização | Leitura | — | API pública de catálogo |
| `buscar_manual` | Recupera trecho relevante do manual do veículo | Leitura | — | Manuais em PDF indexados |
| `registrar_peca` | Grava no cache os modelos que aceitam a peça encontrada | Escrita | Sim (é cache, pode ser sobrescrito) | SQLite local |

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

Peças: API pública real. Manuais: PDFs reais de manutenção. Casos de teste:
simulados, incluindo os três exigidos — divergência (motorização informada não bate
com o catálogo), registro inexistente (peça sem substituta) e caso que não deve
disparar registro no SQLite (dúvida de manual, não de peça).

# 2.9 Dado Sensível

Nenhum. O sistema lida só com dado de veículo (modelo, ano, motorização) — não com
dado pessoal, financeiro ou de saúde.

# 2.11 O maior risco

| Risco | Plano B |
|---|---|
| Acesso à API pública de peças pode não ter cobertura suficiente pra todos os modelos testados | Usar uma base simulada pequena, com os casos difíceis nomeados, pra demonstração |