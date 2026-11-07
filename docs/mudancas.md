# Histórico de mudanças

O que mudou desde a Parte 2. A versão do sistema está em `VERSAO_SISTEMA`, em `src/trajetoria.py`, e vai em cada trace.

| Versão | Commit | O que estava errado ou faltava | O que mudou |
|---|---|---|---|
| 3.0.0 | `7bca8a5` | um trecho falso na mensagem virava resposta e entrava na memória compartilhada; dado pessoal podia ser gravado nela | a resposta precisa se sustentar nos trechos; CPF, e-mail e telefone não entram na memória; testes dos controles em `tests/` ([seguranca.md](seguranca.md)) |
| – | `b46d418` | não havia suíte de avaliação | `evals/`: dataset, execução e comparação ([evals.md](evals.md)) |
| 2.0.0 | `bc0ca95` | quando a última frase não citava carro, o modelo às vezes devolvia um veículo antigo do histórico (`so_o_dito`, `src/nos.py:121`) | só vale o dado do veículo que está na última mensagem; o reducer mantém o resto |
| 2.0.0 | `bc0ca95` | o registro era um log próprio, `trajetoria.jsonl` | traces OpenTelemetry nas convenções GenAI, em `trace.jsonl` ([observabilidade.md](observabilidade.md)). Os logs antigos ficam em `logs/` como evidência dos documentos da Parte 2 |
| – | `d131365` | rodar do zero exigia instalar Python, Chromium e dependências | execução com Docker (README) |
| – | `227318b` | a pessoa aprovava 198 peças para pedir uma | filtro por nome da peça; o lado e a medida entram no nome ([prompts.md](prompts.md) §5.4) |
| – | `106abee` | o modelo inventava de 57% a 62% dos códigos de peça | cartões lidos em código, modelo só como reserva, código conferido na página, tetos de 3 páginas e 120 s ([prompts.md](prompts.md) §5) |
| – | `b1880be` | a regra 5 do prompt fazia o leitor recusar respostas que estavam nos trechos | regra removida: de 10 ou 11 para 15 de 18 respostas com o fato ([rag.md](rag.md) §6.2.1) |

As versões anteriores a 2.0.0 não têm número: o carimbo delas é o commit.
