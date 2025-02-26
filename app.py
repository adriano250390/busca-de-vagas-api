from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import redis
import os
import asyncio
import re
from datetime import datetime, timedelta

app = FastAPI()

# Configuração do Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Configuração das APIs externas
JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
JOOBLE_API_URL = "https://br.jooble.org/api/"

APIFY_API_TOKEN = "apify_api_JPdMIJwlO6TJZbubU2UUrkIZcqjUcU4zjtX1"
APIFY_DATASET_ID = "7WlZplTf3Y0TNTQY3"

# Configuração do CORS
origins = [
    "https://gray-termite-250383.hostingersite.com",
    "http://localhost:3000",
    "http://127.0.0.1:8000"
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
    """Rota de Health Check"""
    return {"status": "ok"}

def converter_data_relativa(data_str: str) -> str:
    """
    Converte datas relativas do Jooble, como:
    - "há 14 horas atrás"
    - "há 3 dias atrás"
    - "há 30 minutos atrás"
    - "Nova"
    - Formato ISO "2025-02-25T10:00:00"
    
    Para um formato absoluto (YYYY-MM-DD).
    """
    hoje = datetime.today()

    # Caso seja um formato ISO válido, retornamos diretamente
    if "T" in data_str:
        return data_str.split("T")[0]

    # Se for "Nova", consideramos hoje
    if "nova" in data_str.lower():
        return hoje.strftime("%Y-%m-%d")

    # Regex para detectar padrões como "há X dias/horas/minutos atrás"
    match = re.search(r"há\s+(\d+)\s+(minuto|minutos|hora|horas|dia|dias)\s+atrás", data_str.lower())
    if match:
        quantidade = int(match.group(1))
        unidade = match.group(2)

        if "dia" in unidade:
            data_final = hoje - timedelta(days=quantidade)
        else:
            data_final = hoje  # Horas e minutos são considerados como "hoje"

        return data_final.strftime("%Y-%m-%d")

    return "Data não informada"

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
            print(f"Erro na API Jooble: {e.response.status_code}")
            return []
        except httpx.RequestError:
            print("Erro de conexão com a API Jooble")
            return []

    return [
        {
            "titulo": vaga.get("title", "Sem título"),
            "empresa": vaga.get("company", "Empresa não informada"),
            "localizacao": vaga.get("location", "Local não informado"),
            "salario": vaga.get("salary", "Salário não informado"),
            "data_atualizacao": converter_data_relativa(vaga.get("updated", "Data não informada")),
            "link": vaga.get("link", "#"),
            "descricao": vaga.get("snippet", "Descrição não disponível"),
            "source": "Jooble"
        }
        for vaga in data.get("jobs", [])[:15]
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
            print(f"Erro na API Apify: {e.response.status_code}")
            return []
        except httpx.RequestError:
            print("Erro de conexão com a API Apify")
            return []

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
        for vaga in data if termo.lower() in vaga.get("title", "").lower()
    ][:5]

@app.get("/buscar")
async def buscar_vagas(termo: str = "", localizacao: str = "", pagina: int = 1, data_filtro: str = "todas"):
    """Busca vagas no Jooble e Indeed, aplicando filtro de datas."""

    if not termo and not localizacao:
        raise HTTPException(status_code=400, detail="É necessário informar um termo de busca ou localização.")

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
        raise HTTPException(status_code=404, detail="Nenhuma vaga encontrada.")

    hoje = datetime.today().date()
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
            vaga for vaga in vagas_combinadas
            if vaga["data_atualizacao"] and vaga["data_atualizacao"] != "Data não informada"
            and datetime.strptime(vaga["data_atualizacao"], "%Y-%m-%d").date() >= data_limite
        ]

    cache.set(cache_key, str(vagas_combinadas), ex=21600)

    return {"source": "live", "data": vagas_combinadas}
