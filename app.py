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

# Configuração da API do Indeed Scraper (Apify)
APIFY_API_TOKEN = "apify_api_JPdMIJwlO6TJZbubU2UUrkIZcqjUcU4zjtX1"
APIFY_ACTOR_ID = "hMvMvNSpz3JhHgl5jkh"  # ID do scraper na Apify

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
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")
def health_check():
    """Rota de Health Check para monitoramento"""
    return {"status": "ok"}

async def iniciar_scraper_indeed(termo: str, localizacao: str):
    """Executa o scraper do Indeed na Apify com os parâmetros fornecidos"""
    url = f"https://api.apify.com/v2/actor-runs?token={APIFY_API_TOKEN}"
    payload = {
        "actorId": APIFY_ACTOR_ID,
        "runInput": {
            "country": "BR",
            "location": localizacao,
            "maxItems": 5,  # Limitar para 5 resultados
            "parseCompanyDetails": False
        }
    }
    
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            run_data = response.json()
            run_id = run_data.get("data", {}).get("id")
            return run_id
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro ao iniciar o scraper na Apify: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Apify"}

async def buscar_vagas_jooble(termo: str, localizacao: str, pagina: int):
    """Busca vagas no Jooble"""
    payload = {"keywords": termo, "location": localizacao, "page": pagina}
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Jooble: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Jooble"}

    novas_vagas = data.get("jobs", [])[:15]  # Retorna no máximo 15 vagas do Jooble

    return [
        {
            "titulo": vaga.get("title", "Sem título"),
            "empresa": vaga.get("company", "Empresa não informada"),
            "localizacao": vaga.get("location", "Local não informado"),
            "salario": vaga.get("salary", "Salário não informado"),
            "data_atualizacao": vaga.get("updated", "Data não informada"),
            "link": vaga.get("link", "#"),
            "descricao": vaga.get("snippet", "Descrição não disponível"),
            "source": "Jooble"
        }
        for vaga in novas_vagas
    ]

async def buscar_vagas_indeed(run_id: str):
    """Busca os resultados do scraper do Indeed na Apify"""
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

    return [
        {
            "titulo": vaga.get("title", "Sem título"),
            "empresa": vaga.get("company", "Empresa não informada"),
            "localizacao": vaga.get("location", "Local não informado"),
            "salario": "Salário não informado",
            "data_atualizacao": vaga.get("date", "Data não informada"),
            "link": vaga.get("url", "#"),
            "descricao": vaga.get("description", "Descrição não disponível"),
            "source": "Indeed"
        }
        for vaga in data[:5]  # Retorna no máximo 5 vagas do Indeed
    ]

@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas no Jooble e Indeed, combinando os resultados"""
    
    cache_key = f"{termo}_{localizacao}_{pagina}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # Iniciar o scraper do Indeed dinamicamente
    run_id = await iniciar_scraper_indeed(termo, localizacao)
    
    # Se houve erro ao iniciar o scraper, retorna erro
    if isinstance(run_id, dict) and "error" in run_id:
        return run_id

    # Buscar as vagas de ambas as APIs de forma assíncrona
    jooble_task = buscar_vagas_jooble(termo, localizacao, pagina)
    indeed_task = buscar_vagas_indeed(run_id)

    jooble_vagas, indeed_vagas = await asyncio.gather(jooble_task, indeed_task)

    # Garantir que os 5 primeiros resultados sejam do Indeed
    vagas_combinadas = (indeed_vagas or []) + (jooble_vagas or [])
    vagas_combinadas = vagas_combinadas[:20]  # Retorna no máximo 20 vagas

    if not vagas_combinadas:
        return {"error": "Nenhuma vaga encontrada."}

    # Salva no cache por 6 horas (21600 segundos)
    cache.set(cache_key, str(vagas_combinadas), ex=21600)

    return {"source": "live", "data": vagas_combinadas}
