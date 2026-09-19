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

## 2.4.2 Nível de autonomia pretendido

## 2.4.3 Ferramentas disponíveis

<table>
    <thead>
        <tr>
            <th>Ferramenta</th>
            <th>O que faz</th>
            <th>Leitura/Escrita?</th>
            <th>Reversível?</th>
            <th>Com quem se comunica</th>
        </tr>
    </thead>
    <tbody>
    </tbody>
<table>

# 2.5 A Justificativa do negócio

## 2.5.1 Por que um Agente e não um software comum? 

## 2.5.2 Ganhos Esperados

<table>
    <thead>
        <tr>
            <th>Eixo</th>
            <th>Linha de Base</th>
            <th>Alvo</th>
            <th>Ganho</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>Tempo por Tarefa</td>
            <td>Dias</td>
            <td>Espera-se reduzir o tempo necessário para identificar qual peça é compatível com o veículo</td>
            <td>~50% de Redução em Tempo identificando peça para o modelo de automôvel</td>
        </tr>
        <tr>
            <td>Erro e retrabalho</td>
            <td>taxa antes × depois</td>
            <td>Mecânico, Consumidor</td>
            <td>Redução em 90% de peças devolvidas por conta de compra errada.</td>
        </tr>
    </tbody>
</table>

## 2.5.3 Ganhos do usuário

## 2.5.4 Custos para manter o sistema


# 2.6 O Verificador

# 2.7 Critério de Sucesso

# 2.8 Dados

## 2.8.1 Origem

# 2.9 Dado Sensível

# 2.10 Conceitos Futuros

- [x] **RAG** - Leitura de manuais em pdf com cerca de 200 páginas.
- [ ] **MCP**
- [x] **LangChain** — Necessário realizar a orquestração entre os agentes de formulação de resposta e consulta de base de dados. 
- [x] **Multiagente** — Haverá 3 fontes de dados (sqlite, manuais em pdf e API's públicas), logo, faz-se necessário o uso de multi-agentes.

# 2.11 O maior risco
(tabela de riscos e possíveis problemas inerentes ao modelo)

# 3 Análise de Modelos