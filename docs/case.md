# Tema: Assistente Informacional de Manutenção Automotiva

## Explanação do Problema

O problema acontece no setor de varejo automotivo, onde muitas vezes o tanto o propietário de um automóvel quanto o mecânico especializado não conseguem identificar de forma simplificada qual a peça ideal para substituição em um modelo de automóvel.

## Contexto

### Acionamento do Sistema

O sistema poderá ser acionado tanto pelo propietário quanto pelo mecânico, tendo como objetivo sanar dúvidas identificação de peças quanto apresentar informações disponibilizadas em manuais do automóvel. 

### input e output

Como input o sistema necessita do nome de modelo do veículo, ano de fabricação, carroceria e motorização, o usuário que irá ceder inicialmente essa informação e a partir destes dados, o sistema apresentará em formato de tabela o código de identificação da peça e uma lista de automóveis também compatível com tal peça, ou apresentará em formato de texto corrido um resumo de orientações a partir da informação extraída do manual do veículo.

### Situação Atual

Hoje, a consulta funciona principalmente através da leitura de manuais técnicos desenvolvidos pela montadora para cada modelo de automóvel. O que pode fazer com que propietários não atentos à ler com cuidado o manual comprar peças erradas.
Em quanto ao vendedor/mecânico, não havendo uma base de dados confiável, desenvolvida internamente, fica suscetível à realizar a compra na base do achismo.

### Regras do Domínio

A peça recomendada para a instalação no automóvel exige a leitura do manual. Muitos automóveis compartilham peças, então a base de dados explorada (Manuais) pode ser maior que apenas a base disponibilizada pelo fabricante para o veículo em específico. Uma das principais regras é respeitar o ano/modelo do veículo.

### O que dá Errado Hoje

A incerteza no momento de compra de peças de substituição em carros vendidos no mercado nacional, causa o aumento de custos e possível maior demora para realização de serviços em oficinas de pequeno/médio porte.


## Identificação do Usuário

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



## Como é a Interação

A interação será através de chat, é mais simples para acesso de ambos usuários à informação. O agente será acionado pelo usuário, portanto reativo. provavelmente haverá entorno de 3 à 4 interações até o sistema ter todos os dados necessários para inferir qual peça é a certa ao automóvel.
o retorno será uma tabela com o código da peça, modelo e ano de automóveis compatíveis com a peça. Em caso de erro o agente apresentará a desculpa de não ter encontrado a peça para o automóvel.

# Ganhos Esperados

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