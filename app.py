from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import redis
import os
import asyncio
from datetime import datetime, timedelta

app = FastAPI()

# Configuração do Redis (Cache) - Cache por 6 horas (21600 segundos)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Configuração da API Jooble
JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
JOOBLE_API_URL = "https://br.jooble.org/api/"

# Configuração da API Apify
APIFY_API_TOKEN = "apify_api_JPdMIJwlO6TJZbubU2UUrkIZcqjUcU4zjtX1"
APIFY_ACTOR_ID = "hMvNSpz3JnHgl5jkh"  # ID do scraper na Apify

# Habilitar CORS corretamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite qualquer origem (mude para seu domínio se necessário)
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")
def health_check():
    """Rota de Health Check para monitoramento"""
    return {"status": "ok"}

async def iniciar_scraper_indeed(termo: str, localizacao: str):
    """Inicia o scraper no Apify e retorna o run_id"""
    url_actors = f"https://api.apify.com/v2/actors/{APIFY_ACTOR_ID}/runs?token={APIFY_API_TOKEN}"
    url_acts = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs?token={APIFY_API_TOKEN}"

    payload = {
        "input": {
            "country": "BR",
            "query": termo,
            "location": localizacao,
            "maxItems": 5
        }
    }

    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60) as client:
        for url in [url_actors, url_acts]:  # Testa as duas versões da API
            try:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 201:  # Sucesso
                    run_data = response.json()
                    run_id = run_data.get("data", {}).get("id")
                    if run_id:
                        return run_id
                elif response.status_code == 403:
                    return {"error": "Permissão negada para acessar o ator na Apify. Verifique as configurações."}
                elif response.status_code == 404:
                    continue  # Tenta a outra URL

            except httpx.HTTPStatusError as e:
                return {"error": f"Erro na API Apify: {e.response.status_code}"}
            except httpx.RequestError:
                return {"error": "Erro de conexão com a API Apify"}

    return {"error": "Não foi possível iniciar o scraper na Apify."}

async def aguardar_scraper_indeed(run_id: str):
    """Aguarda a conclusão do scraper na Apify"""
    url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_API_TOKEN}"

    async with httpx.AsyncClient(timeout=60) as client:
        for _ in range(15):  # Até 3 minutos (15 tentativas de 12s)
            try:
                response = await client.get(url)
                response.raise_for_status()
                status = response.json().get("data", {}).get("status")

                if status == "SUCCEEDED":
                    return True
                elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                    return {"error": f"Scraper falhou com status: {status}"}

                await asyncio.sleep(12)

            except httpx.RequestError:
                return {"error": "Erro ao verificar o status do scraper na Apify"}

    return {"error": "Scraper demorou muito para finalizar"}

async def buscar_vagas_indeed(run_id: str):
    """Busca os resultados do scraper na Apify"""
    url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items?token={APIFY_API_TOKEN}"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro ao buscar dados na Apify: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Apify"}

    return data[:5]  # Retorna no máximo 5 vagas

@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas no Indeed e combina com Jooble"""
    
    cache_key = f"{termo}_{localizacao}_{pagina}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # Iniciar o scraper do Indeed
    run_id = await iniciar_scraper_indeed(termo, localizacao)
    
    if isinstance(run_id, dict) and "error" in run_id:
        return run_id

    # Aguardar conclusão do scraper
    scraper_status = await aguardar_scraper_indeed(run_id)
    if isinstance(scraper_status, dict) and "error" in scraper_status:
        return scraper_status

    # Buscar as vagas do Indeed
    indeed_vagas = await buscar_vagas_indeed(run_id)

    if not indeed_vagas:
        return {"error": "Nenhuma vaga encontrada no Indeed."}

    # Salva no cache por 6 horas (21600 segundos)
    cache.set(cache_key, str(indeed_vagas), ex=21600)

    return {"source": "live", "data": indeed_vagas}
