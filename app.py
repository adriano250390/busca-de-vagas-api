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
APIFY_DATASET_ID = "7WlZplTf3Y0TNTQY3"

# Habilitação de CORS com suporte para o site frontend
origins = [
    "https://gray-termite-250383.hostingersite.com",  # Seu site hospedado
    "http://localhost:3000",  # Para testes locais
    "http://127.0.0.1:8000"  # Acesso via terminal local
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
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

async def buscar_vagas_indeed(termo: str, localizacao: str):
    """Busca vagas no Indeed Scraper da Apify e limita a 5 resultados"""
    url = f"https://api.apify.com/v2/datasets/{APIFY_DATASET_ID}/items?token={APIFY_API_TOKEN}"
    
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Apify: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Apify"}

    novas_vagas = [vaga for vaga in data if termo.lower() in vaga.get("title", "").lower()]

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
        for vaga in novas_vagas[:5]
    ]

@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1, data_filtro: str = "todas"):
    """Busca vagas no Jooble e Indeed, combinando os resultados com filtro de datas"""

    cache_key = f"{termo}_{localizacao}_{pagina}_{data_filtro}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    jooble_task = buscar_vagas_jooble(termo, localizacao, pagina)
    indeed_task = buscar_vagas_indeed(termo, localizacao)
    
    jooble_vagas, indeed_vagas = await asyncio.gather(jooble_task, indeed_task)

    vagas_combinadas = (indeed_vagas or []) + (jooble_vagas or [])
    vagas_combinadas = vagas_combinadas[:20]

    if not vagas_combinadas:
        return {"error": "Nenhuma vaga encontrada."}

    # Filtro de data
    hoje = datetime.today()
    filtros = {
        "hoje": hoje,
        "ontem": hoje - timedelta(days=1),
        "ultimos5dias": hoje - timedelta(days=5),
        "ultimos10dias": hoje - timedelta(days=10),
        "ultimos30dias": hoje - timedelta(days=30),
    }

    if data_filtro in filtros:
        data_limite = filtros[data_filtro]
        vagas_combinadas = [
            vaga for vaga in vagas_combinadas if "data_atualizacao" in vaga and vaga["data_atualizacao"] != "Data não informada" and 
            datetime.strptime(vaga["data_atualizacao"], "%Y-%m-%d") >= data_limite
        ]

    cache.set(cache_key, str(vagas_combinadas), ex=21600)

    return {"source": "live", "data": vagas_combinadas}
