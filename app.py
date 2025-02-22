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
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")
def health_check():
    """Rota de Health Check"""
    return {"status": "ok"}

# -------------------------
# Rota unificada: buscar vagas de Jooble + Indeed
# -------------------------
@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """
    Exemplo que busca vagas em duas fontes:
     - Jooble (retorna até 15 vagas)
     - Bright Data (Indeed)

    Retorna uma lista unificada de vagas para exibir no front.
    """

    # -- Monta chaves de cache (opcional, mas bom para evitar repetição de chamadas) --
    jooble_cache_key = f"jooble_{termo}_{localizacao}_{pagina}"
    indeed_cache_key = f"indeed_{termo}_{localizacao}"

    # Tenta do cache (opcional). Se quiser remover o cache, basta comentar essas linhas.
    jooble_cached = cache.get(jooble_cache_key)
    indeed_cached = cache.get(indeed_cache_key)

    if jooble_cached and indeed_cached:
        # Se ambos estiverem em cache, unifica e retorna
        jooble_vagas = eval(jooble_cached)
        indeed_vagas = eval(indeed_cached)
        vagas_unificadas = jooble_vagas + indeed_vagas
        return {
            "source": "cache",
            "total_vagas": len(vagas_unificadas),
            "data": vagas_unificadas
        }

    # -------------------------
    # 1) Buscar dados do Jooble
    # -------------------------
    payload_jooble = {
        "keywords": termo,
        "location": localizacao,
        "page": pagina
    }
    headers_jooble = {"Content-Type": "application/json"}

    # -------------------------
    # 2) Buscar dados do Bright Data (Indeed)
    # -------------------------
    headers_bd = {
        "Authorization": BRIGHTDATA_TOKEN,
        "Content-Type": "application/json",
    }
    params_bd = {
        "dataset_id": BRIGHTDATA_DATASET_ID,
        "include_errors": "true",
        "type": "discover_new",   # ou 'all', depende de como quer buscar
        "discover_by": "keyword",
        "limit_per_input": "6",   # Ajuste conforme sua necessidade
    }
    # Exemplo simples: um único "item" para pesquisa
    data_bd = [
        {
            "country": "US",
            "domain": "indeed.com",
            "keyword_search": termo,
            "location": localizacao,
            "date_posted": "Last 7 days",  # Você pode alterar
            "posted_by": ""
        }
    ]

    # -------------------------
    # Chamar ambas as APIs em paralelo (usando asyncio.gather)
    # -------------------------
    async with httpx.AsyncClient(timeout=30) as client:
        # Prepare duas coro-rotinas
        jooble_coro = client.post(
            f"{JOOBLE_API_URL}{JOOBLE_API_KEY}",
            json=payload_jooble,
            headers=headers_jooble
        )
        indeed_coro = client.post(
            BRIGHTDATA_URL,
            headers=headers_bd,
            params=params_bd,
            json=data_bd
        )

        # Executa em paralelo
        jooble_resp, indeed_resp = await asyncio.gather(jooble_coro, indeed_coro)

    # -------------------------
    # Trata resposta do Jooble
    # -------------------------
    jooble_vagas = []
    try:
        jooble_resp.raise_for_status()  # Se falhar, gera exception
        jooble_data = jooble_resp.json()
        jooble_jobs = jooble_data.get("jobs", [])[:15]  # Pega até 15
        jooble_vagas = [
            {
                "titulo": vaga.get("title", "Sem título"),
                "empresa": vaga.get("company", "Empresa não informada"),
                "localizacao": vaga.get("location", "Local não informado"),
                "salario": vaga.get("salary", "Salário não informado"),
                "data_atualizacao": vaga.get("updated", "Data não informada"),
                "link": vaga.get("link", "#"),
                "descricao": vaga.get("snippet", "Descrição não disponível"),
                "fonte": "Jooble"
            }
            for vaga in jooble_jobs
        ]
    except Exception as e:
        print("Erro ao buscar dados no Jooble:", str(e))
        # jooble_vagas segue como lista vazia

    # -------------------------
    # Trata resposta da Bright Data (Indeed)
    # -------------------------
    indeed_vagas = []
    try:
        indeed_resp.raise_for_status()
        indeed_data = indeed_resp.json()

        # IMPORTANTE:
        # Normalmente, esse "indeed_data" é só o 'gatilho' (trigger) da coleta.
        # Se você precisar de fato das vagas, verifique se a Bright Data
        # retorna algo imediatamente ou se é preciso fazer uma segunda requisição
        # usando um "request_id" retornado nesse JSON.

        # Exemplo de como ficaria se a API já retornasse as vagas (imaginário):
        #   for item in indeed_data.get("jobs", []):
        #       indeed_vagas.append({
        #          "titulo": item.get("title", "Sem título"),
        #          "empresa": item.get("company", "Empresa não informada"),
        #          "localizacao": item.get("location", "Local não informado"),
        #          ...
        #       })
        #
        # Como, na prática, normalmente não é assim, vamos só retornar a resposta pura
        # ou criar um item "fonte": "Indeed" para manter o mesmo formato.

        # Exemplo simples (caso queira apenas sinalizar):
        indeed_vagas = [{
            "titulo": "Bright Data Trigger (não é a lista final)",
            "fonte": "Indeed/BrightData",
            "detalhes_trigger": indeed_data
        }]
    except Exception as e:
        print("Erro ao buscar dados no Bright Data:", str(e))
        # indeed_vagas segue como lista vazia ou com a info de erro

    # -------------------------
    # Unificando as listas
    # -------------------------
    vagas_unificadas = jooble_vagas + indeed_vagas  # Concatena

    # -------------------------
    # Salvar no cache (opcional)
    # -------------------------
    cache.set(jooble_cache_key, str(jooble_vagas), ex=3600)
    cache.set(indeed_cache_key, str(indeed_vagas), ex=3600)

    # -------------------------
    # Retornar resultado
    # -------------------------
    return {
        "source": "live",
        "total_vagas": len(vagas_unificadas),
        "data": vagas_unificadas
    }
