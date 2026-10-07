# Contrato de Entrada e Saída

Este documento define o contrato de entrada e saída do **Assistente Informacional de Manutenção Automotiva**. O sistema recebe dúvidas em texto livre, decide quais informações ainda são necessárias, consulta as fontes disponíveis e retorna uma resposta estruturada em JSON.

O contrato está alinhado ao funcionamento descrito no projeto: o agente atende mecânicos e proprietários, identifica peças compatíveis ou consulta informações do manual do proprietário, podendo consultar cache local, catálogo de peças ou manuais indexados. O sistema possui caráter informativo e não realiza compras ou reservas.

> **Observação:** os exemplos desta documentação representam o formato esperado do contrato. Os campos `commit`, `data_execucao` e `log` devem ser preenchidos a partir de execuções reais do sistema antes da entrega final. Eles não foram inventados porque essas informações não constam no material fornecido.

---

## 1.1 Entrada

### Texto livre como entrada principal

A entrada principal do sistema é uma **mensagem textual livre**, escrita pelo usuário em linguagem natural.

Isso é importante porque o sistema não pressupõe que o usuário saiba antecipadamente quais campos são necessários para responder à dúvida. Por exemplo, o usuário pode informar apenas:

```text
Preciso do código da pastilha de freio do Corolla 2020.
```

Nesse caso, o sistema pode identificar que faltam informações relevantes, como a motorização ou versão, antes de consultar a fonte.

O projeto estabelece que a interação ocorre por chatbot e que o agente pode realizar aproximadamente três ou quatro interações até obter os dados necessários para construir a resposta. A entrada inicial, portanto, não deve ser tratada como um formulário fixo. 

O sistema deve aceitar mensagens como:

```text
Qual pastilha de freio serve no Corolla 2020?
```

ou:

```text
Tenho um Corolla 2020 2.0 e preciso saber qual pastilha de freio devo comprar.
```

ou ainda:

```text
No manual do meu carro, quando devo trocar o óleo?
```

Essas mensagens representam consultas diferentes que precisam ser classificadas e tratadas pelo agente.

### Metadados da execução

Além do texto digitado pelo usuário, a aplicação pode receber metadados técnicos necessários para identificar a conversa ou a execução. Esses dados não fazem parte da mensagem em linguagem natural.

Exemplo:

```json
{
  "thread_id": "discord-canal-123",
  "user_id": "usuario-456",
  "message": "Tenho um Corolla 2020 2.0 e preciso saber qual pastilha de freio devo comprar."
}
```

O `thread_id` identifica a conversa e pode ser utilizado para manter o contexto entre as interações. O `user_id` identifica o solicitante quando essa informação estiver disponível.

O projeto informa que o sistema é acionado pelo próprio mecânico ou pelo balconista em nome dele, por meio de um chatbot. A interação é reativa e ocorre no atendimento de balcão ou telefone via Discord da loja.

### Arquivos, imagens e outros conteúdos

Arquivos, planilhas ou imagens **não substituem a entrada textual principal**.

Quando houver conteúdo externo, ele deve ser tratado como fonte consultável pelo agente. No projeto, por exemplo, os manuais são PDFs indexados e são acessados pela ferramenta `buscar_manual`.

A entrada do sistema continua sendo uma pergunta textual, como:

```text
Quando devo trocar o óleo desse veículo?
```

e o agente utiliza o manual como fonte para produzir a resposta.

---

## 1.2 Contrato de saída

A saída do sistema não é texto livre. Ela deve ser um **objeto JSON validado por um schema definido no código**.

O contrato possui três informações obrigatórias:

1. `conteúdo` — a resposta produzida pelo agente;
2. `fonte` — a evidência utilizada para produzir a resposta;
3. `suficiencia` — indica se o sistema possui informação suficiente para responder.

### Schema proposto

```json
{
  "resultado": {},
  "fonte": [],
  "suficiencia": true
}
```

Uma representação mais completa, adequada ao funcionamento do projeto, é:

```json
{
  "modelo": "Toyota Corolla",
  "ano": "2020",
  "motorizacao": "2.0"
  "codigo_peca": "ABC123",
  "modelos_compativeis": [{
    "modelo": "etios",
    "ano":"2021"
  }],
  "fonte": {
    "tipo": "cache",
    "origem": "catalogo_toyota",
    "evidencia": {
      "modelo": "Toyota Corolla",
      "ano": "2020",
      "motorizacao": "2.0", "nome_peca":"xxxx", "codigo_peca":"ABC123"
    }
  },
  "suficiencia": true
}
```

### Resposta de manual

Quando a dúvida não for sobre compatibilidade de peças, o resultado pode representar o resumo extraído do manual:

```json
{
  "duvida_usuario":"Quais são as dicas de direção são recomendadas pela montadora do meu carro?",
  "kws_duvida_usuario":["dicas","direção"],
  "resolucao":"Trocar a marcha à cada 10 km/h, utilizar cinto de segurança sempre que dirigir, nunca desengatar o carro em ladeira...",
  "origem": "manual_toyota_corolla_2020.pdf",
  "suficiencia": true
}
```

O projeto define que, para dúvidas de manual, o agente apresenta um texto de até 400 tokens com a resposta.

### Resposta sem informação suficiente

A recusa também faz parte do contrato. O agente não deve preencher uma resposta por aproximação quando não possui dados suficientes.

Exemplo:

```json
{
  "duvida_usuario":"Quais são as dicas de direção são recomendadas pela montadora do meu carro?",
  "kws_duvida_usuario":["dicas","direção"],
  "resolucao":"",
  "origem": "manual_toyota_corolla_2020.pdf",
  "suficiencia": False
}
```

Esse comportamento é especialmente importante para peças de segurança. O projeto determina que peças de freio, suspensão e direção não devem ser apresentadas com baixa confiança.

Também existe uma regra explícita para peças sem substituta exata: o sistema deve informar que não encontrou a peça, em vez de apresentar uma peça apenas aproximada.

## 1.4 Entradas que não podem ser atendidas diretamente

O agente deve tratar explicitamente três situações:

1. entrada incompleta;
2. entrada ambígua;
3. entrada fora do escopo.

Responder normalmente nesses casos poderia gerar uma resposta aparentemente válida, mas sem base suficiente.

---

### 1.4.1 Entrada incompleta

Uma entrada é incompleta quando faltam dados necessários para identificar a resposta.

**Entrada:**

```text
Qual é o código da pastilha de freio do Corolla 2020?
```

**Comportamento esperado:**
O agente irá fazer uma nova pergunta ao usuário para coletar os dados faltantes.

A regra é não realizar uma busca com informações insuficientes e apresentar o primeiro resultado encontrado como se fosse necessariamente compatível.

---

### 1.4.2 Entrada ambígua

Uma entrada é ambígua quando os dados fornecidos permitem mais de uma interpretação possível.

**Entrada:**

```text
Preciso da peça do Corolla 2020.
```

Essa entrada não informa sequer qual peça está sendo procurada e também pode não especificar a versão ou motorização.

**Comportamento esperado:**

O agente não deve escolher arbitrariamente uma peça ou uma configuração do veículo.

Caso existam duas interpretações plausíveis, outra possibilidade é o agente apresentar explicitamente a interpretação escolhida e solicitar confirmação.

---

### 1.4.3 Entrada fora do escopo

Uma entrada está fora do escopo quando solicita uma operação que o sistema não realiza.

O projeto estabelece que o agente é **informativo** e não executa compras ou reservas.

**Entrada:**

```text
Compre agora a pastilha de freio para o meu Corolla.
```

**Saída esperada:**

**O que demonstra:** o agente reconhece a intenção relacionada ao seu domínio, mas não executa uma ação que está explicitamente fora do escopo.
