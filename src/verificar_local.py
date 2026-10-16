"""Verificação de fumaça do modelo configurado no .env (use com MODE=local para o Ollama).

Confere, nesta ordem, os recursos que o sistema usa de fato:
  1. conexão e modelo disponível;
  2. resposta simples;
  3. saída estruturada com schema estrito (response_format) — Registrador, Leitor, Scrapper;
  4. enum respeitado no schema — roteamento do Registrador;
  5. tool calling sem argumentos — get_all_table_names;
  6. tool calling com argumento objeto — rescue_db_data.

Uso, a partir da raiz do projeto:  python src/verificar_local.py
Sai com código 1 se algum item falhar. O que isto prova é que o modelo aceita os recursos,
não que ele acerta as respostas do domínio.
"""
import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from interfaces.json_format import createJsonFormat
from interfaces.tool_call import ToolCall
from src.config import client, MODEL

modelo = MODEL or "openai/gpt-oss-120b"
resultados = []


def verificar(nome, func):
    inicio = time.time()
    try:
        detalhe = func()
        ok = True
    except Exception as err:
        detalhe, ok = f"{type(err).__name__}: {err}", False
    resultados.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {nome}  ({time.time() - inicio:.1f}s)  {detalhe}")
    return ok


def conversar(mensagens, **kwargs):
    return client.chat.completions.create(model=modelo, messages=mensagens, temperature=0, **kwargs).choices[0].message


def t_modelo():
    ids = [m.id for m in client.models.list().data]
    if modelo not in ids:
        raise RuntimeError(f"'{modelo}' não está na lista do servidor. Disponíveis: {ids}")
    return modelo


def t_simples():
    msg = conversar([{"role": "user", "content": "Responda apenas: ok"}], max_tokens=20)
    if not (msg.content or "").strip():
        raise RuntimeError("resposta vazia")
    return repr(msg.content.strip()[:40])


def t_schema():
    fmt = createJsonFormat("verificacao_entrada", [
        {"name": "modelo", "type": "string"},
        {"name": "ano", "type": "integer"},
        {"name": "motorizacao", "type": "string"},
    ])
    msg = conversar([
        {"role": "system", "content": "Estruture os dados do veículo em JSON."},
        {"role": "user", "content": "Meu carro é um Volkswagen Fox 2015 motor 1.6"},
    ], response_format=fmt, max_tokens=200)
    dados = json.loads(msg.content)
    if set(dados) != {"modelo", "ano", "motorizacao"}:
        raise RuntimeError(f"campos inesperados: {dados}")
    if not isinstance(dados["ano"], int):
        raise RuntimeError(f"ano deveria ser inteiro: {dados}")
    return dados


def t_enum():
    fmt = createJsonFormat("verificacao_rota", [
        {"name": "pensamento", "type": "string"},
        {"name": "acao", "type": "string", "enum": ["RESGATAR_DADOS", "INSERIR_DADOS"]},
        {"name": "conteudo", "type": "string"},
    ])
    msg = conversar([
        {"role": "system", "content": "Escolha a ação: RESGATAR_DADOS lê da base, INSERIR_DADOS grava na base."},
        {"role": "user", "content": "Mostre todas as peças cadastradas."},
    ], response_format=fmt, max_tokens=300)
    dados = json.loads(msg.content)
    if dados["acao"] not in ("RESGATAR_DADOS", "INSERIR_DADOS"):
        raise RuntimeError(f"ação fora do enum: {dados}")
    return f"acao={dados['acao']}"


def _chamar_tool(tool_dict, pergunta):
    msg = conversar([
        {"role": "system", "content": "Use as ferramentas disponíveis. Não responda sem chamar a ferramenta adequada."},
        {"role": "user", "content": pergunta},
    ], tools=[tool_dict], max_tokens=400)
    if not msg.tool_calls:
        raise RuntimeError(f"nenhuma tool call; resposta em texto: {(msg.content or '')[:80]!r}")
    return msg.tool_calls[0].function


def t_tool_sem_args():
    tool = ToolCall("get_all_table_names", "Receber as tabelas criadas e as colunas de cada uma")
    fn = _chamar_tool(tool.to_dict(), "Quais tabelas existem na base?")
    if fn.name != "get_all_table_names":
        raise RuntimeError(f"ferramenta errada: {fn.name}")
    return f"{fn.name}({fn.arguments})"


def t_tool_com_objeto():
    tool = ToolCall("rescue_db_data", "Resgatar dados da base local")
    tool.insert_prop("tablename", {"type": "string", "description": "nome da tabela à ser lida"})
    tool.insert_prop("query_filter", {
        "type": "object",
        "description": "Filtros no formato {coluna: valor}. Use {} para trazer a tabela inteira.",
        "additionalProperties": True,
    })
    fn = _chamar_tool(tool.to_dict(), "Traga da tabela pecas_automoveis as peças do modelo Fox.")
    args = json.loads(fn.arguments)
    if fn.name != "rescue_db_data" or args.get("tablename") != "pecas_automoveis":
        raise RuntimeError(f"chamada inesperada: {fn.name} {args}")
    if not isinstance(args.get("query_filter"), dict):
        raise RuntimeError(f"query_filter deveria ser objeto: {args}")
    return f"{fn.name}({args})"


print(f"Modelo: {modelo}\n")
if verificar("1. conexão e modelo disponível", t_modelo):
    verificar("2. resposta simples", t_simples)
    verificar("3. schema estrito (JSON)", t_schema)
    verificar("4. enum no schema", t_enum)
    verificar("5. tool call sem argumentos", t_tool_sem_args)
    verificar("6. tool call com argumento objeto", t_tool_com_objeto)

print(f"\n{sum(resultados)}/{len(resultados)} verificações passaram")
sys.exit(0 if all(resultados) and len(resultados) == 6 else 1)
