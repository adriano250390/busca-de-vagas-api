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
# Chaves comentadas, caso não queira usá-las agora
# (somente se realmente não for usar Jooble por enquanto)
# JOOBLE_API_KEY = "xxx"
# JOOBLE_API_URL = "https://br.jooble.org/api/"

# -------------------------
# Configuração da Bright Data (para Indeed)
# -------------------------
BRIGHTDATA_URL = "https://api.brightdata.com/datasets/v3/trigger"
BRIGHTDATA_TOKEN = "Bearer 1d3cf9f7dd24acb0109d558a667720ffdeecbb0a64c305d08bfee5b4f86e8436"
BRIGHTDATA_DATASET_ID = "gd_l4dx9j9sscpvs7no2"

# -------------------------
# Habilitar CORS
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gray-termite-250383.hostingersite.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# -------------------------
# Rotas básicas
# -------------------------
@app.get("/")
def home():
    return {"message": "API rodando - teste do Indeed!"}

@app.get("/healthz")
@app.head("/healthz")
def health_check():
    return {"status": "ok"}

# -------------------------
# Rota unificada (mas Jooble está desativado)
# -------------------------
@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = ""):
    """
    Exemplo que busca vagas *somente* no Indeed (via Bright Data), para testar.
    """

    # -- Monta chave de cache, caso queira
    indeed_cache_key = f"indeed_{termo}_{localizacao}"

    # -- Verifica cache (opcional)
    cached_data = cache.get(indeed_cache_key)
    if cached_data:
        return {
            "source": "cache",
            "data": eval(cached_data),
        }

    # ---------------------------------------
    # LÓGICA DO JOOBLE (COMENTADA/REMOVIDA)
    # ---------------------------------------
    # # payload_jooble = {...}
    # # headers_jooble = {...}
    # # (não vamos chamar o Jooble agora)

    # ---------------------------------------
    # Chamar a API do Bright Data (Indeed)
    # ---------------------------------------
    headers_bd = {
        "Authorization": BRIGHTDATA_TOKEN,
        "Content-Type": "application/json",
    }
    params_bd = {
        "dataset_id": BRIGHTDATA_DATASET_ID,
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
        "limit_per_input": "6",  # Ajuste conforme necessário
    }
    data_bd = [
        {
            "country": "US",
            "domain": "indeed.com",
            "keyword_search": termo,
            "location": localizacao,
            "date_posted": "Last 7 days",
            "posted_by": ""
        }
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            indeed_resp = await client.post(
                BRIGHTDATA_URL,
                headers=headers_bd,
                params=params_bd,
                json=data_bd
            )
            indeed_resp.raise_for_status()
            indeed_data = indeed_resp.json()
        except httpx.HTTPError as e:
            return {"error": f"Erro ao chamar Bright Data: {str(e)}"}

    # ---------------------------------------
    # AVISO: Normalmente brightdata retorna só o "gatilho" (trigger)
    # e não as vagas em si. Se esse for o caso, esse 'indeed_data'
    # pode conter algo como { "request_id": "...", ... }.
    #
    # Se você precisar de fato das vagas, tem que fazer a 2a requisição
    # usando esse request_id. Aqui vamos só retornar o que vier.
    # ---------------------------------------

    # Se fosse processar de verdade as vagas, você formataria algo como:
    #   indeed_vagas = [
    #       {
    #         "titulo": item.get("title", "Sem título"),
    #         "empresa": item.get("company", "Empresa não informada"),
    #         "fonte": "Indeed"
    #       } for item in indeed_data.get("jobs", [])
    #   ]
    #   etc...
    # Mas, por enquanto, só retornamos o JSON puro:

    # Salvar no cache
    cache.set(indeed_cache_key, str(indeed_data), ex=3600)

    return {
        "source": "live",
        "data": indeed_data,
    }
