from mcp.server.fastmcp import FastMCP
from requests import get

ENDERECO = "127.0.0.1"
PORTA = 8000
CAMINHO = "/mcp"

servidor = FastMCP("cnpj e cep", host=ENDERECO, port=PORTA, streamable_http_path=CAMINHO)

# Headers simulando navegador para evitar bloqueio por rate limit / erro 429
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


# ===================================================================== 2
#  FERRAMENTAS — o MODELO decide invocar
# ===================================================================== 2

@servidor.tool()
def consultar_cnpj(cnpj: str) -> dict:
    """
        Devolve dados pertinentes ao CNPJ informado.
        Esta ferramenta aceita uma string formatada sob o regex: ^[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-[0-9]{2}$
        Dados Retornados: cnpj, razao_social, cep, logradouro, numero, complemento, bairro, municipio, uf
        Esta ferramenta não devolve informação referente à coordenadas do local onde a empresa está instalada.
    """
    cnpj = cnpj\
            .replace('-', '')\
            .replace('/', '')\
            .replace('.', '')
    if(len(cnpj) != 14): return {'error': 'Quantidade de caracteres inválido!'}
    
    campos = ['cnpj', 'razao_social', 'cep', 'logradouro', 'numero', 'complemento', 'bairro', 'municipio', 'uf']

    endpoint = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
    try:
        result = get(endpoint, headers=HEADERS, timeout=10)
        if(result.status_code == 200):
            dados = result.json()
            return {key: dados[key] for key in dados if key in campos}
        elif(result.status_code == 404):
            return {'error':'cnpj não identificado!'}
        elif(result.status_code == 429):
            return {'error':'Muitas requisições seguidas, tente novamente mais tarde'}
    except Exception as err:
        print("[ERROR] Requisição CNPJ")
        raise err

@servidor.tool()
def consultar_cep(cep: str) -> dict:
    """
        Devolve dados pertinentes ao CEP informado.
        Esta ferramenta aceita uma string formatada sob o regex: ^\d{5}(-)\d{3}$
        Dados Retornados: cep, street, neighborhood, city, state, location.coordinates.latitude, location.coordinates.longitude
        Esta ferramenta não apresenta dados referentes à endereços, por exemplo, números de residências/comércios.
    """
    cep = cep.replace('-','')

    endpoint = f"https://brasilapi.com.br/api/cep/v2/{cep}"

    try:
        result = get(endpoint, headers=HEADERS, timeout=10)
        if(result.status_code == 200):
            dados = result.json()
            coords = dados.get('location', {}).get('coordinates', {})
            return {
                'cep': dados.get('cep'),
                'street': dados.get('street'),
                'neighborhood': dados.get('neighborhood'),
                'city': dados.get('city'),
                'state': dados.get('state'),
                'latitude': coords.get('latitude'),
                'longitude': coords.get('longitude')
            }
        elif(result.status_code == 404):
            return {'error':'cpf não identificado!'}
        elif(result.status_code == 429):
            return {'error':'Muitas requisições seguidas, tente novamente mais tarde'}
    except Exception as err:
        raise err


if __name__ == "__main__":
    print(f"servidor no ar em {ENDERECO}:{PORTA}{CAMINHO}")
    # Teste 1: CNPJ Válido
    print("--- TESTE 1: CNPJ VÁLIDO ---")
    resultado = consultar_cnpj("43.600.266/0003-40")
    print("Resultado:", resultado)

    # Teste 2: CNPJ Inexistente (404)
    print("\n--- TESTE 2: CNPJ INEXISTENTE ---")
    resultado_404 = consultar_cnpj("00.000.000/0000-00")
    print("Resultado:", resultado_404)

    servidor.run(transport="streamable-http")