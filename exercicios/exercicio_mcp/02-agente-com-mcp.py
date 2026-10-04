import asyncio
import json
import sys

from cliente import modelo
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL_SERVIDOR = "http://127.0.0.1:8000/mcp"


def extrair_texto_mcp(resultado_mcp) -> str:
    """Extrai o conteúdo em texto puro retornado pela ferramenta MCP."""
    textos = []
    for content in resultado_mcp.content:
        if content.type == "text":
            textos.append(content.text)
    return "\n".join(textos)


async def main():
    if len(sys.argv) < 2:
        print("Uso incorreto. Exemplo: python cliente_cnpj.py 19.131.243/0001-97")
        sys.exit(1)

    cnpj_input = sys.argv[1]

    print(f"Conectando ao servidor FastMCP via SSE ({URL_SERVIDOR})...\n")

    # Conecta no servidor HTTP/SSE ativo
    async with streamable_http_client(URL_SERVIDOR) as (leitura, escrita, _):
        async with ClientSession(leitura, escrita) as session:
            await session.initialize()

            # 1. Validar ferramentas
            tools_response = await session.list_tools()
            ferramentas_disponiveis = {tool.name for tool in tools_response.tools}
            ferramentas_obrigatorias = {"consultar_cnpj", "consultar_cep"}

            faltantes = ferramentas_obrigatorias - ferramentas_disponiveis
            if faltantes:
                print(f"Erro: Ferramentas faltantes no servidor: {', '.join(faltantes)}")
                sys.exit(1)

            # 2. Chamar consultar_cnpj
            print("--> Executando consultar_cnpj...")
            res_cnpj_raw = await session.call_tool("consultar_cnpj", {"cnpj": cnpj_input})
            if res_cnpj_raw.isError:
                print(f"\n[Erro na Consulta de CNPJ]\n{extrair_texto_mcp(res_cnpj_raw)}")
                return

            texto_cnpj = extrair_texto_mcp(res_cnpj_raw)

            try:
                dados_cnpj = json.loads(texto_cnpj)
                if isinstance(dados_cnpj, list):
                    # Transforma lista de dicts em um dicionário único caso o servidor devolva lista
                    dados_cnpj = {k: v for item in dados_cnpj for k, v in item.items()}
            except json.JSONDecodeError:
                prompt_extracao = f"Extraia em JSON com as chaves 'razao_social', 'cep', 'error' de:\n{texto_cnpj}"
                print(prompt_extracao)
                dados = modelo.invoke(prompt_extracao).content
                dados_cnpj = json.loads(dados)

            if dados_cnpj.get("error") or dados_cnpj.get("erro") or not dados_cnpj.get("cep"):
                erro = dados_cnpj.get("error") or dados_cnpj.get("erro") or "CEP não encontrado."
                print(f"\n[Erro no CNPJ]: {erro}")
                return

            razao_social = dados_cnpj.get("razao_social", "Não informada")
            cep_extraido = dados_cnpj.get("cep")

            print(f"   Razão Social: {razao_social}")
            print(f"   CEP: {cep_extraido}")

            # 3. Chamar consultar_cep
            print("\n--> Executando consultar_cep...")
            res_cep_raw = await session.call_tool("consultar_cep", {"cep": cep_extraido})

            if res_cep_raw.isError:
                print(f"\n[Erro na Consulta de CEP]\n{extrair_texto_mcp(res_cep_raw)}")
                return

            texto_cep = extrair_texto_mcp(res_cep_raw)

            try:
                dados_cep = json.loads(texto_cep)
            except json.JSONDecodeError:
                prompt_extracao_cep = f"Extraia em JSON com 'street', 'neighborhood', 'city', 'state' de:\n{texto_cep}"
                dados_cep = json.loads(modelo.invoke(prompt_extracao_cep).content)

            if dados_cep.get("error") or dados_cep.get("erro"):
                print(f"\n[Erro no CEP]: {dados_cep.get('error') or dados_cep.get('erro')}")
                return

            # 4. Prompt Final
            prompt_final = f"""
            Sua tarefa é formatar a apresentação final dos dados de uma empresa.
                SERVIDOR:   
                    ferramentas: [consultar_cnpj, consultar_cep]
                    CNPJ ............ 00.000.000/0000-00
                    Razão social .... XXXXXXXXXXXXXXXXXX
                    CEP ............. 00000-000
                    Endereço ........ <NOME RUA> <NUMERO> - <BAIRRO>, <CIDADE>/<UF>
                    Lat / Long ...... <latitude> / <longitude>
                    Quando o CEP não tiver coordenadas:
                    Lat / Long ...... não disponível para este CEP

                Dados:{dados_cep}
            """
            print("\n" + "=" * 50)
            resposta_final = modelo.invoke(prompt_final)
            print(resposta_final.content)
            print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())


# o cliente que você escreveu conhece a BrasilAPI? O que precisaria mudar nele se o servidor trocasse a BrasilAPI por outra fonte de dados?
# R: Não conhece, se o servidor alterar a fonte de dados o cliente não precisa de alteração nenhuma.


#CNPJ: 43.600.266/0003-40 (Válido)
### Informações da Empresa
# **CNPJ:** 00.000.000/0000-00
# **Razão Social:** XXXXXXXXXXXXXXXXXX
# **CEP:** 04752-901
# **Endereço:** Rua Amador Bueno 474 - Santo Amaro, São Paulo/SP
# **Coordenadas Geográficas:** -23.5475 / -46.63611

#CNPJ: 43.600.266/0003-00 (Formato válido mas cnpj não existe)
#OBS: Servidor api retorna status code 400 ao não encontrar cnpj
# File "/usr/lib/python3.14/json/decoder.py", line 363, in raw_decode
#       |     raise JSONDecodeError("Expecting value", s, err.value) from None

#CNPJ: 43.600.266/0003-0 (INVALIDO)
# [Erro no CNPJ]: Quantidade de caracteres inválido!