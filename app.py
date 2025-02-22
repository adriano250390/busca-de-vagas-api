import requests
import httpx
import redis
import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Configuração das APIs
JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
JOOBLE_API_URL = "https://br.jooble.org/api/"

BRIGHT_DATA_API_URL = "https://api.brightdata.com/datasets/v3/trigger"
BRIGHT_DATA_TOKEN = "1d3cf9f7dd24acb0109d558a667720ffdeecbb0a64c305d08bfee5b4f86e8436"
BRIGHT_DATA_DATASET_ID = "gd_l4dx9j9sscpvs7no2"

# Habilitar CORS corretamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gray-termite-250383.hostingersite.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")
def health_check():
    return {"status": "ok"}

@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    cache_key = f"{termo}_{localizacao}_{pagina}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # Buscar vagas do Jooble
    jooble_payload = {"keywords": termo, "location": localizacao, "page": pagina}
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=jooble_payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Jooble: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Jooble"}
    vagas_jooble = data.get("jobs", [])[:10]  # Pegamos 10 vagas do Jooble

    # Buscar vagas do Indeed via Bright Data
    bright_data_headers = {
        "Authorization": f"Bearer {BRIGHT_DATA_TOKEN}",
        "Content-Type": "application/json",
    }
    bright_data_params = {
        "dataset_id": BRIGHT_DATA_DATASET_ID,
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
        "limit_per_input": "5"
    }
    bright_data_payload = [{
        "country": "US",
        "domain": "indeed.com",
        "keyword_search": termo,
        "location": localizacao,
        "date_posted": "Last 7 days",
        "posted_by": ""
    }]
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(BRIGHT_DATA_API_URL, headers=bright_data_headers, params=bright_data_params, json=bright_data_payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Bright Data: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Bright Data"}
    vagas_indeed = data.get("results", [])[:5]  # Pegamos no máximo 5 vagas do Indeed

    # Mesclar os resultados
    vagas_combinadas = vagas_jooble + vagas_indeed

    cache.set(cache_key, str(vagas_combinadas), ex=3600)
    return {"source": "live", "data": vagas_combinadas}
