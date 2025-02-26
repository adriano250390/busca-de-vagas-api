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
    Converte datas relativas do Jooble, por exemplo:
    - "há 14 horas atrás"
    - "há 3 dias atrás"
    - "há 30 minutos atrás"
    - "Nova"
    - Formato ISO "2025-02-25T10:00:00"
    
    Para um formato absoluto (YYYY-MM-DD). Qualquer situação que não
    se encaixar cai em "Data não informada".
    
    *Observação*: agora consideramos qualquer "hora(s)" ou "minuto(s)" como data de HOJE,
    para que apareçam corretamente no filtro "hoje".
    """
    hoje = datetime.today()

    # 1) Caso seja um formato ISO ("2025-02-25T12:00:00"), usamos só a parte YYYY-MM-DD
    if "T" in data_str:
        return data_str.split("T")[0]

    # 2) Se o texto tiver "Nova" (ou "nova"), consideramos como hoje
    if "nova" in data_str.lower():
        return hoje.strftime("%Y-%m-%d")

    # 3) Expressão regular para encontrar "há X unidade atrás" (minutos, horas, dias)
    match = re.search(r"há\s+(\d+)\s+(minuto|minutos|hora|horas|dia|dias)\s+atrás", data_str.lower())
    if match:
        quantidade = int(match.group(1))
        unidade = match.group(2)

        if "dia" in unidade:
            # Subtrai o número de dias
            data_final = hoje - timedelta(days=quantidade)
        else:
            # Para horas ou minutos, consideramos a vaga ainda como "hoje"
            data_final = hoje

        return data_final.strftime("%Y-%m-%d")

    # 4) Se não conseguir converter, retorna "Data não informada"
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

    # Monta a lista de vagas
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

    # Filtra os resultados do Apify pelo termo, depois retorna apenas 5
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
    """
    Busca vagas no Jooble e Indeed, aplicando filtro de datas.
    Parâmetros:
      - termo: cargo ou palavra-chave
      - localizacao: cidade/estado
      - pagina: página de resultados do Jooble
      - data_filtro: hoje, ontem, ultimos5dias, ultimos10dias, ultimos30dias ou todas
    """

    if not termo and not localizacao:
        raise HTTPException(status_code=400, detail="É necessário informar um termo de busca ou localização.")

    # Chave de cache para evitar consultas repetidas em curto intervalo
    cache_key = f"{termo}_{localizacao}_{pagina}_{data_filtro}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # Dispara buscas simultâneas no Jooble e Indeed
    jooble_task = buscar_vagas_jooble(termo, localizacao, pagina)
    indeed_task = buscar_vagas_indeed(termo, localizacao)

    jooble_vagas, indeed_vagas = await asyncio.gather(jooble_task, indeed_task)

    # Combina os resultados (limita a 20 vagas no total)
    vagas_combinadas = (indeed_vagas or []) + (jooble_vagas or [])
    vagas_combinadas = vagas_combinadas[:20]

    if not vagas_combinadas:
        raise HTTPException(status_code=404, detail="Nenhuma vaga encontrada.")

    # Filtro de data
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
        vagas_filtradas = []
for vaga in vagas_combinadas:
    data_str = vaga["data_atualizacao"]
    
    if data_str and data_str != "Data não informada":
        try:
            data_vaga = datetime.strptime(data_str, "%Y-%m-%d").date()
            if data_vaga >= data_limite:
                vagas_filtradas.append(vaga)
        except ValueError:
            print(f"Erro ao converter data: {data_str}")  # Para debug

# Se a filtragem removeu tudo, exibir debug
if not vagas_filtradas:
    print(f"🔴 Nenhuma vaga foi encontrada para o filtro {data_filtro}")

vagas_combinadas = vagas_filtradas


    # Grava no cache por 6 horas (21600 segundos)
    cache.set(cache_key, str(vagas_combinadas), ex=21600)

    return {"source": "live", "data": vagas_combinadas}
