from fastapi import FastAPI
import requests
import redis
import os

app = FastAPI()

# Configuração do Redis (cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Fonte de vagas (Exemplo: API fictícia - substituir depois)
JOBS_API_URL = "https://jobs-api-exemplo.com/vagas"

@app.get("/buscar")
def buscar_vagas(termo: str):
    """Busca vagas de emprego com cache"""
    
    # Verifica se já tem essa busca no cache
    cached_data = cache.get(termo)
    if cached_data:
        return {"source": "cache", "data": cached_data}
    
    # Se não tem no cache, busca a vaga na API de empregos
    response = requests.get(f"{JOBS_API_URL}?q={termo}")
    if response.status_code == 200:
        cache.set(termo, response.text, ex=3600)  # Cache por 1 hora
        return {"source": "live", "data": response.json()}
    
    return {"error": "Falha na busca de vagas"}
