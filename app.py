from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx  # Alterando para uma requisição assíncrona
import redis
import os
import asyncio  # Adicionando para assíncrona

app = FastAPI()

# Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Configuração da API Jooble
JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
JOOBLE_API_URL = "https://br.jooble.org/api/"

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

@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas de emprego no Jooble e retorna somente uma página de resultados."""
    
    cache_key = f"{termo}_{localizacao}_{pagina}"
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
            response = await client.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=payload, headers=headers)
            response.raise_for_status()  # Lança erro caso a API retorne status diferente de 200
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Jooble: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Jooble"}
    
    novas_vagas = data.get("jobs", [])

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
            "descricao": vaga.get("snippet", "Descrição não disponível")
        }
        for vaga in novas_vagas
    ]

    # Salva no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)

    return {"source": "live", "data": vagas}
