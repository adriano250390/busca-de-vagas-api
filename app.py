from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import redis
import os
import asyncio

app = FastAPI()

# -----------------------------------------------------------------------------
# Configuração do Redis (se quiser manter o cache; pode remover se não usar)
# -----------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# -----------------------------------------------------------------------------
# **Jooble** está comentado (pois queremos testar apenas Bright Data)
# -----------------------------------------------------------------------------
# JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
# JOOBLE_API_URL = "https://br.jooble.org/api/"

# -----------------------------------------------------------------------------
# Configuração da Bright Data (para Indeed)
# -----------------------------------------------------------------------------
BRIGHTDATA_URL = "https://api.brightdata.com/datasets/v3/trigger"
BRIGHTDATA_TOKEN = "Bearer 1d3cf9f7dd24acb0109d558a667720ffdeecbb0a64c305d08bfee5b4f86e8436"
BRIGHTDATA_DATASET_ID = "gd_l4dx9j9sscpvs7no2"

# -----------------------------------------------------------------------------
# Habilitar CORS
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gray-termite-250383.hostingersite.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Função auxiliar para escolher domain/country com base na localização
# -----------------------------------------------------------------------------
def escolher_domain_e_pais(localizacao: str):
    """
    Exemplo BEM simples de correspondência:
      - Se contiver 'paris' -> (FR, fr.indeed.com)
      - Se contiver 'new york' ou 'usa' -> (US, indeed.com)
      - Se contiver 'brasil', 'são paulo', etc. -> (BR, br.indeed.com)
      - Senão, default = (US, indeed.com)
    Ajuste conforme seu dataset real. Se BrightData não aceita BR, retire a parte BR.
    """
    loc = localizacao.lower()

    if "paris" in loc or "france" in loc:
        return ("FR", "fr.indeed.com")
    elif "new york" in loc or "usa" in loc or "united states" in loc:
        return ("US", "indeed.com")
    elif "brasil" in loc or "são paulo" in loc or "rio de janeiro" in loc or "brazil" in loc:
        return ("BR", "br.indeed.com")
    else:
        # Default
        return ("US", "indeed.com")

# -----------------------------------------------------------------------------
# Rotas básicas
# -----------------------------------------------------------------------------
@app.get("/")
def home():
    return {"message": "API rodando - Apenas Bright Data (Indeed)"}

@app.get("/healthz")
@app.head("/healthz")
def health_check():
    return {"status": "ok"}

# -----------------------------------------------------------------------------
# Rota /buscar - SÓ Bright Data (Indeed)
# -----------------------------------------------------------------------------
@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = ""):
    """
    Testa somente a Bright Data (Indeed). Jooble está comentado.
    """

    # -- Exemplo simples: usar a função auxiliar p/ domain e country
    country_code, domain = escolher_domain_e_pais(localizacao)

    # -- Monta chave de cache (opcional)
    cache_key = f"indeed_{termo}_{localizacao}"

    # -- Tenta cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # -----------------------
    # Parâmetros Bright Data
    # -----------------------
    headers = {
        "Authorization": BRIGHTDATA_TOKEN,
        "Content-Type": "application/json",
    }
    params = {
        "dataset_id": BRIGHTDATA_DATASET_ID,
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
        "limit_per_input": "6",
    }

    # data_posted pode ser "Last 7 days", "Last 24 hours", etc.
    data_bd = [
        {
            "country": country_code,
            "domain": domain,
            "keyword_search": termo,
            "location": localizacao,
            "date_posted": "Last 7 days",
            "posted_by": ""
        }
    ]

    # Faz a requisição
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(BRIGHTDATA_URL, headers=headers, params=params, json=data_bd)

    # Se não for 200, retorna erro e mostra o corpo de resposta p/ diagnosticar
    if resp.status_code != 200:
        return {
            "error": f"HTTP {resp.status_code} na chamada Bright Data",
            "detail": resp.text  # Isso ajuda ver a msg de erro exata
        }

    # Se deu certo, pegue o JSON
    result = resp.json()

    # IMPORTANTE: Normalmente aqui só temos o "gatilho" (trigger).
    # Se você PRECISA de fato das vagas, tem que consultar o request_id
    # em outro endpoint. Por ora, vamos só retornar o que vier.
    cache.set(cache_key, str(result), ex=3600)

    return {
        "source": "live",
        "data": result
    }

# -----------------------------------------------------------------------------
# (COMENTADO) Código do Jooble
# -----------------------------------------------------------------------------
"""
# Aqui estaria toda a lógica do Jooble caso quisesse reativar depois:

# @app.get("/buscar_jooble")
# async def buscar_vagas_jooble(termo: str, localizacao: str = "", pagina: int = 1):
#     # ...
#     # ...
#     return ...
"""
