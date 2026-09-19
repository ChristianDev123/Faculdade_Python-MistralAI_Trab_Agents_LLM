# Exercício 6 — Base de conhecimento 

*(Mesmo case do assistente de peças automotivas)*

**1. O que indexar, e por que não vem do modelo**
- Catálogo de compatibilidade — específico demais + muda toda semana.
- Manuais do proprietário — específico demais (torque, óleo, procedimento por modelo).
- Tabela de peças substitutas — privada, muda por recall/descontinuação.
- *Não indexar:* conhecimento geral de mecânica — o modelo já sabe.

**2. Onde estão, e acesso**

| Fonte | Onde / formato | Acesso |
|---|---|---|
| Catálogo de compatibilidade | API/banco do distribuidor (tipo ACES/PIES) | **Não garantido hoje — maior risco do case** |
| Manuais | PDF da montadora; alguns escaneados | A confirmar por modelo |
| Peças substitutas | Boletim técnico do fabricante | **Não existe hoje, precisa ser criada** |

**3. O que vai para o índice**
- Entra: manuais dos ~15 modelos mais vendidos → ordem de 300–500 chunks, cortando por seção.
- Escala pequena → **não precisa de banco vetorial**, índice simples resolve.
- Fica fora (é consulta estruturada, não busca semântica): catálogo de compatibilidade, estoque e preço — todos com filtro exato (`modelo ==`, `ano <=`).

**4. Chunking por documento**

| Documento | Corte | Metadado |
|---|---|---|
| Manual do proprietário | Por seção, herdando o cabeçalho | modelo, ano, seção |
| Boletim técnico | 1 boletim = 1 chunk | código original / substituto |
| Histórico de devolução | Não é chunk — é linha de banco | — |
