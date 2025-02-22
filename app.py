from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import redis
import os
import asyncio

app = FastAPI()

# -------------------------
# Configuração do Redis (Cache)
# -------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# -------------------------
# Configuração da API Jooble
# -------------------------
JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
JOOBLE_API_URL = "https://br.jooble.org/api/"

# -------------------------
# Configuração da Bright Data (Indeed)
# -------------------------
BRIGHTDATA_URL = "https://api.brightdata.com/datasets/v3/trigger"
BRIGHTDATA_TOKEN = "Bearer 1d3cf9f7dd24acb0109d558a667720ffdeecbb0a64c305d08bfee5b4f86e8436"
BRIGHTDATA_DATASET_ID = "gd_l4dx9j9sscpvs7no2"

# -------------------------
# Habilitar CORS corretamente
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gray-termite-250383.hostingersite.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# -------------------------
# Rotas padrões
# -------------------------
@app.get("/")
def home():
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")  # Suporte para requisições HEAD
def health_check():
    """Rota de Health Check"""
    return {"status": "ok"}

# -------------------------
# Rota: Buscar vagas no Jooble
# -------------------------
@app.get("/buscar_jooble")
async def buscar_vagas_jooble(termo: str, localizacao: str = "", pagina: int = 1):
    """
    Busca vagas de emprego no Jooble e retorna no máximo 15 por página.
    Exemplo de uso: /buscar_jooble?termo=python&localizacao=SP&pagina=1
    """
    cache_key = f"jooble_{termo}_{localizacao}_{pagina}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    payload = {
        "keywords": termo,
        "location": localizacao,
        "page": pagina
    }
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}",
                                         json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Jooble: {e.response.status_code}"}
        except httpx.RequestError as e:
            return {"error": f"Erro de conexão com a API Jooble: {str(e)}"}

    novas_vagas = data.get("jobs", [])[:15]  # Retorna apenas 15 vagas

    if not novas_vagas:
        return {"error": "Nenhuma vaga encontrada para esta página."}

    vagas = [
        {
            "titulo": vaga.get("title", "Sem título"),
            "empresa": vaga.get("company", "Empresa não informada"),
            "localizacao": vaga.get("location", "Local não informado"),
            "salario": vaga.get("salary", "Salário não informado"),
            "data_atualizacao": vaga.get("updated", "Data não informada"),
            "link": vaga.get("link", "#"),
            "descricao": vaga.get("snippet", "Descrição não disponível"),
        }
        for vaga in novas_vagas
    ]

    # Salva no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)
    return {"source": "live", "data": vagas}

# -------------------------
# Rota: Buscar vagas no Indeed (via Bright Data)
# -------------------------
@app.get("/buscar_indeed")
async def buscar_vagas_indeed(
    termo: str,
    localizacao: str = "",
    data_postagem: str = "Last 7 days",  # exemplos: "Last 24 hours", "Last 7 days"...
    posted_by: str = ""
):
    """
    Dispara a coleta de vagas do Indeed via Bright Data (exemplo).
    Pode-se ajustar parâmetros conforme necessidade.
    
    Exemplo de uso: /buscar_indeed?termo=analyst&localizacao=New%20York,%20NY&data_postagem=Last%2024%20hours
    """
    # Monta a chave de cache
    cache_key = f"indeed_{termo}_{localizacao}_{data_postagem}_{posted_by}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # Montando os parâmetros da chamada
    headers = {
        "Authorization": BRIGHTDATA_TOKEN,
        "Content-Type": "application/json",
    }
    params = {
        "dataset_id": BRIGHTDATA_DATASET_ID,
        "include_errors": "true",
        "type": "discover_new",   # ou 'all', depende de como quer buscar
        "discover_by": "keyword",
        "limit_per_input": "6",
    }
    # Você pode ajustar o "country", "domain" ou "date_posted" conforme sua necessidade:
    data = [
        {
            "country": "US",
            "domain": "indeed.com",
            "keyword_search": termo,
            "location": localizacao,
            "date_posted": data_postagem,
            "posted_by": posted_by
        }
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                BRIGHTDATA_URL,
                headers=headers,
                params=params,
                json=data
            )
            response.raise_for_status()
            resultado = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Bright Data: {e.response.status_code}"}
        except httpx.RequestError as e:
            return {"error": f"Erro de conexão com a API Bright Data: {str(e)}"}

    # Importante: O "resultado" retornado pela Bright Data pode ser apenas o "trigger" de coleta
    # Muitas vezes é necessário depois consultar o "request_id" gerado e buscar
    # em uma URL de resultados. Depende de como você está usando a Bright Data.
    #
    # Se esse "resultado" já contiver vagas, você pode processá-las aqui.
    # Caso contrário, você salva esse "resultado" ou retorna diretamente.

    # Neste exemplo, vamos supor que você só quer retornar o JSON da Bright Data:
    cache.set(cache_key, str(resultado), ex=3600)
    return {"source": "live", "data": resultado}
