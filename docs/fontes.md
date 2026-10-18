## 1. AutoPapo
**Link:** [https://autopapo.com.br/curta/carros-mercado-pecas-paralelas/](https://autopapo.com.br/curta/carros-mercado-pecas-paralelas/)
**O que sustenta no texto:** Confirma que a frota brasileira ultrapassa os 60 milhões de veículos, com uma idade média de 10 anos e 9 meses (segundo a Sindipeças). Além disso, ratifica a informação de que o mercado de reposição independente movimenta cerca de R$ 140 bilhões por ano.

## 2. Revista O Mecânico
**Link:** [https://omecanico.com.br/sindipecas-realiza-estudo-para-prever-vendas-de-autopecas/](https://omecanico.com.br/sindipecas-realiza-estudo-para-prever-vendas-de-autopecas/)
**O que sustenta no texto:** Sustenta que os cálculos de previsão de vendas e demanda do setor são elaborados eletronicamente pelo Sistema de Informações de Frota e Demanda (SIF/SID). O texto confirma explicitamente que este sistema "considera a demanda por modelo de veículo levando-se em conta a versão e motorização", validando a regra de compatibilidade real do mercado.

## 3. Portal do Trânsito
**Link:** [https://www.portaldotransito.com.br/noticias/voce-sabe-as-diferencas-entre-pecas-genuinas-originais-e-genericas-2/amp/](https://www.portaldotransito.com.br/noticias/voce-sabe-as-diferencas-entre-pecas-genuinas-originais-e-genericas-2/amp/)
**O que sustenta no texto:** Confirma a classificação técnica oficial utilizada pelo setor (com base no Boletim Técnico do CESVI) para diferenciar as peças do mercado automotivo nas categorias: **Genuínas**, **Originais** e **Genéricas** (sendo estas últimas também tratadas no texto como alternativas ou paralelas).

## 4. Autoo
**Link:** [https://www.autoo.com.br/original-paralela-genuina-entenda-quais-sao-os-tipos-de-pecas-de-reposicao/](https://www.autoo.com.br/original-paralela-genuina-entenda-quais-sao-os-tipos-de-pecas-de-reposicao/)
**O que sustenta no texto:** Valida a informação de que, a partir do segundo semestre de 2019 (nova orientação da Susep), deixou de ser obrigatório o uso de peças originais em reparos de veículos (sinistros parciais), abrindo espaço para peças de fabricantes independentes. O texto também confirma o risco da compatibilidade e qualidade, citando o alerta do CESVI para que as partes fiquem atentas à qualidade para "evitar retrabalho".

---

# Fontes da Parte 2

As fontes abaixo foram abertas em 2026-10-18 para conferir que o link existe e diz o que está atribuído a ele. Onde a afirmação do texto vem de **medição nossa** e não da fonte, isso está dito.

## 5. LangGraph (documentação oficial)
**Link:** [https://docs.langchain.com/oss/python/langgraph/overview](https://docs.langchain.com/oss/python/langgraph/overview) (a página antiga, `langchain-ai.github.io/langgraph`, redireciona para esta)
**O que sustenta no texto:** descreve o LangGraph como ferramenta de baixo nível para orquestrar agentes com estado, com persistência (o agente "retoma de onde parou") e supervisão humana (inspecionar e modificar o estado). Sustenta a escolha do `StateGraph`, do checkpointer e do `interrupt` em [grafo.md](grafo.md) e [humano.md](humano.md). A versão usada está fixada em `requirements.txt` (`langgraph==1.2.14`); o comportamento medido por nós (por exemplo, a retomada reexecutando o nó desde o começo) vem dos cenários de `logs/exemplos/`, não desta página.

## 6. Ollama: perguntas frequentes
**Link:** [https://docs.ollama.com/faq](https://docs.ollama.com/faq)
**O que sustenta no texto:** o contexto padrão é de 4096 tokens e pode ser mudado com `OLLAMA_CONTEXT_LENGTH` (exemplo da própria página: `OLLAMA_CONTEXT_LENGTH=8192 ollama serve`). Sustenta a condição de medição de [prompts.md](prompts.md) §2. **O corte do prompt em metade do contexto (mais 2 tokens), descartando o começo, não vem desta página:** foi medido por nós (teste da agulha e aviso `truncating input prompt` no log do servidor, [prompts.md](prompts.md) §6).

## 7. Ollama: modelo `qwen2.5`
**Link:** [https://ollama.com/library/qwen2.5](https://ollama.com/library/qwen2.5)
**O que sustenta no texto:** o modelo `qwen2.5:7b` (4,7 GB), usado em todas as medições locais. A página lista contexto de 32K para as etiquetas do Ollama (o texto de apresentação fala em até 128K); o que o sistema usa de fato é o contexto configurado no servidor (4096 por padrão, 8192 nas medições).

## 8. Modelo de embeddings `all-MiniLM-L6-v2`
**Link:** [https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
**O que sustenta no texto:** o modelo que indexa os trechos do manual e a memória episódica no Chroma gera vetores de 384 dimensões e a página lista só o inglês como idioma. É um fato que ajuda a ler a medição de [rag.md](rag.md) §6.1 (busca vetorial 13/20 contra textual 16/20 em acertos entre os 5 primeiros, sobre manuais em português): a página não diz que o modelo serve ao português. A causa da diferença não foi isolada; os números são **medição nossa**.

## 9. BM25
**Link:** [https://doi.org/10.1561/1500000019](https://doi.org/10.1561/1500000019)
**O que sustenta no texto:** S. Robertson e H. Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond*, Foundations and Trends in Information Retrieval, vol. 4, n. 1-2, p. 1-174 (2009, segundo a linha de citação da página). É a base da busca textual própria de `src/busca_textual.py`; os parâmetros `k1 = 1,5` e `b = 0,75` são os valores clássicos e **não foram ajustados ao corpus** (declarado no código).

## 10. Chroma
**Link:** [https://docs.trychroma.com/](https://docs.trychroma.com/)
**O que sustenta no texto:** o Chroma guarda os vetores e os metadados dos trechos dos manuais e da memória episódica, e permite recuperar os trechos guardados (a busca textual do sistema parte dos trechos que ele guarda). Versão fixada em `requirements.txt`.

## 11. Playwright para Python
**Link:** [https://playwright.dev/python/](https://playwright.dev/python/)
**O que sustenta no texto:** a biblioteca que controla o Chromium sem tela na raspagem do catálogo ([prompts.md](prompts.md) §5). O sistema usa o Chromium do sistema (`/usr/bin/chromium`), não o baixado pela biblioteca.

## 12. Pydantic
**Link:** [https://pydantic.dev/docs/validation/latest/get-started/](https://pydantic.dev/docs/validation/latest/get-started/) (a página antiga, `docs.pydantic.dev/latest`, redireciona para esta)
**O que sustenta no texto:** a biblioteca de validação por tipos usada nos contratos de entrada e de saída (`Saida`, `Fonte`, `Peca`, `Extracao`, `LeituraManual`, `RespostaAprovacao`) em [io.md](io.md).

## 13. Catálogo web da Chevrolet (corpus de peças)
**Link:** [https://www.pecachevrolet.com.br/pesquisa](https://www.pecachevrolet.com.br/pesquisa)
**O que sustenta no texto:** a fonte das peças da Chevrolet gravadas em `pecas_automoveis` após aprovação humana. A estrutura observada em 2026-10-18 (202 cartões numa busca, 200 deles com o código da peça no endereço `/peca/<código>/<nome>`, 194 com o campo "Nº original GM" igual a esse código) é **observação nossa** da página, e vale para aquela data ([prompts.md](prompts.md) §5; [case.md](case.md) §2.12); o catálogo devolve tudo o que casa com o carro e com uma das palavras da busca, por isso o filtro por nome de [prompts.md](prompts.md) §5.4. O site é privado e pode mudar.

## 14. Catálogo web da Volkswagen (corpus de peças)
**Link:** [https://pecas.vw.com.br/todas-categorias](https://pecas.vw.com.br/todas-categorias)
**O que sustenta no texto:** o segundo catálogo cadastrado em `webcatalogos`. **Ainda não foi inspecionado nem raspado em nenhuma medição**; está aqui por constar da configuração.

## 15. Manuais do proprietário (corpus de manuais)
**Documentos:** `Volkswagen_Fox_2015.pdf` (335 páginas, fechamento 22.08.2014, edição 09.2014) e `Volkswagen_Fox_2020.pdf` (300 páginas, fechamento 07.02.2020, edição 05.2020), em `databases/manuais/`.
**O que sustenta no texto:** o conteúdo que o RAG consulta ([rag.md](rag.md) §2). **O endereço de onde o grupo baixou cada PDF não foi registrado:** quem os baixou precisa acrescentar o link aqui.
