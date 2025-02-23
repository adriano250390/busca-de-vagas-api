from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import redis
import os
import asyncio
from jobspy import scrape_jobs

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
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")  # 🔹 Suporte para requisições HEAD (necessário para o UptimeRobot)
def health_check():
    """Rota de Health Check para o Render e monitoramento"""
    return {"status": "ok"}

async def buscar_vagas_jooble(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas de emprego no Jooble"""
    
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

    novas_vagas = data.get("jobs", [])[:15]  # 🔹 Retorna apenas 15 vagas
    return [
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
        for vaga in novas_vagas
    ]

def buscar_vagas_jobspy(termo: str, localizacao: str = "", quantidade: int = 10):
    """Busca vagas no JobSpy"""
    
    jobs = scrape_jobs(
        site_name=["indeed", "linkedin", "zip_recruiter", "glassdoor", "google"],
        search_term=termo,
        location=localizacao,
        results_wanted=quantidade,
        hours_old=72,  # Apenas vagas dos últimos 3 dias
        country_indeed='Brazil',
    )

    return [
        {
            "titulo": vaga.get("title", "Sem título"),
            "empresa": vaga.get("company", "Empresa não informada"),
            "localizacao": vaga.get("location", "Local não informado"),
            "salario": f"{vaga.get('min_amount', 'N/A')} - {vaga.get('max_amount', 'N/A')}",
            "data_atualizacao": vaga.get("date_posted", "Data não informada"),
            "link": vaga.get("job_url", "#"),
            "descricao": vaga.get("description", "Descrição não disponível"),
            "fonte": vaga.get("site", "JobSpy")
        }
        for _, vaga in jobs.iterrows()
    ]

@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas de emprego no Jooble e no JobSpy"""
    
    cache_key = f"{termo}_{localizacao}_{pagina}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # Buscando simultaneamente em ambas as fontes
    vagas_jooble = await buscar_vagas_jooble(termo, localizacao, pagina)
    vagas_jobspy = buscar_vagas_jobspy(termo, localizacao)

    # Unindo os resultados
    vagas = vagas_jooble + vagas_jobspy

    if not vagas:
        return {"error": "Nenhuma vaga encontrada."}

    # Salva no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)

    return {"source": "live", "data": vagas}
