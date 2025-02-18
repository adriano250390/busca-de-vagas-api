from fastapi import FastAPI
import requests
import redis
import os

app = FastAPI()

@app.get("/")
def home():
    return {"message": "API de busca de vagas está rodando!"}

# Configuração do Redis (cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Fonte de vagas (Empregos.com.br)
JOBS_API_URL = "https://www.empregos.com.br/vagas"

@app.get("/buscar")
def buscar_vagas(termo: str):
    """Busca vagas de emprego no site empregos.com.br com cache"""

    # Verifica se já tem essa busca no cache
    cached_data = cache.get(termo)
    if cached_data:
        return {"source": "cache", "data": cached_data}

    # Faz a requisição ao site de vagas
    url = f"{JOBS_API_URL}?q={termo}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        cache.set(termo, response.text, ex=3600)  # Cache por 1 hora
        return {"source": "live", "data": response.text}  # Retorna o HTML da busca
    
    return {"error": "Falha na busca de vagas"}
