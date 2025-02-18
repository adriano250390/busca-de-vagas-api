from fastapi import FastAPI
import requests
import redis
import os

app = FastAPI()

# 🔑 Chave da API do ScrapingDog
API_KEY = "67b47bd0bc3ed73cbdfab7ba"  

# Configuração do Redis (cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

@app.get("/")
def home():
    return {"message": "API de busca de vagas no Indeed está rodando!"}

@app.get("/buscar")
def buscar_vagas(termo: str, local: str = ""):
    """Busca vagas no Indeed e retorna os resultados"""
    
    cache_key = f"{termo}_{local}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # 🔍 Formata a URL do Indeed
    termo_formatado = termo.replace(" ", "+")
    local_formatado = local.replace(" ", "+")
    url = f"https://www.indeed.com/jobs?q={termo_formatado}&l={local_formatado}"

    # 🔍 Faz a requisição via ScrapingDog
    scrapingdog_url = "https://api.scrapingdog.com/indeed"
    params = {"api_key": API_KEY, "url": url}
    
    response = requests.get(scrapingdog_url, params=params)

    if response.status_code == 200:
        json_response = response.json()
        vagas = json_response.get("jobs", [])

        if not vagas:
            return {"error": "Nenhuma vaga encontrada.", "url": url}

        cache.set(cache_key, str(vagas), ex=3600)

        return {"source": "live", "data": vagas}

    return {"error": "Falha na busca de vagas", "status_code": response.status_code, "url": url}
