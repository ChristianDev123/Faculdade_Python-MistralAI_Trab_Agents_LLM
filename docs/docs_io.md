# Contrato de Entrada e Saída

## 1.3 Exemplos na documentação

### Exemplo 1 — Caminho feliz: identificação de peça

**Entrada exata:**

```text
Tenho um Corolla 2020 2.0 e preciso saber qual pastilha de freio devo comprar.
```

**Saída completa:**

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
      "motorizacao": "2.0", 
      "nome_peca":"xxxx", 
      "codigo_peca":"ABC123"
    }
  },
  "suficiencia": true
}
```

**O que demonstra:** `suficiencia: true` mostra que o agente encontrou informação suficiente para produzir a resposta. A presença da fonte permite conferir de onde veio a identificação da peça.

**Commit da execução:** `PREENCHER_COM_COMMIT_REAL`

**Data da execução:** `PREENCHER_COM_DATA_REAL`

**Log:** `logs/PREENCHER_LOG_REAL`

---

### Exemplo 2 — Recusa: informação insuficiente

**Entrada exata:**

```text
Preciso da pastilha de freio do Corolla 2020.
```

**Saída completa:**

```json
{
  "resultado": {
    "tipo": "recusa",
    "resposta": "Preciso saber a versão e a motorização do Corolla para verificar corretamente a compatibilidade da pastilha de freio."
  },
  "fonte": [],
  "suficiencia": false
}
```

**O que demonstra:** `suficiencia: false` indica que o agente não possui base suficiente para responder. Em vez de inventar ou aproximar uma peça, ele informa quais dados faltam.

Isso está de acordo com a regra do domínio de que a compatibilidade depende de **modelo + versão + motorização**, e não somente de modelo e ano.

**Commit da execução:** `PREENCHER_COM_COMMIT_REAL`

**Data da execução:** `PREENCHER_COM_DATA_REAL`

**Log:** `logs/PREENCHER_LOG_REAL`

---

### Exemplo 3 — Dúvida de manual

**Entrada exata:**

```text
Quando devo fazer a manutenção preventiva do meu Corolla?
```

**Saída completa:**

```json
{
  "resultado": {
    "tipo": "manual",
    "resposta": "Consulte o intervalo de manutenção indicado no manual do veículo para verificar as revisões e substituições previstas."
  },
  "fonte": [
    {
      "tipo": "manual",
      "origem": "manual_corolla.pdf",
      "evidencia": "Trecho do manual utilizado na resposta."
    }
  ],
  "suficiencia": true
}
```

**O que demonstra:** a saída identifica que a consulta é relacionada ao manual e apresenta a fonte utilizada. Diferentemente de uma consulta de peça, essa execução não deve registrar uma nova compatibilidade no SQLite.

**Commit da execução:** `PREENCHER_COM_COMMIT_REAL`

**Data da execução:** `PREENCHER_COM_DATA_REAL`

**Log:** `logs/PREENCHER_LOG_REAL`

