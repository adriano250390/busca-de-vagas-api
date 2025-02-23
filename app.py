from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import redis
import os
import asyncio
from jobspy import scrape_jobs  # Nova API de busca de vagas

app = FastAPI()

# Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

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

@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas de emprego na nova API JobSpy"""

    cache_key = f"{termo}_{localizacao}_{pagina}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    try:
        # Nova busca de vagas usando jobspy
        vagas_jobspy = scrape_jobs(
            site_name=["indeed", "linkedin", "glassdoor", "google"],
            search_term=termo,
            location=localizacao,
            results_wanted=15  # Pegamos apenas 15 vagas por página
        )

        if not vagas_jobspy:
            return {"error": "Nenhuma vaga encontrada para esta pesquisa."}

        vagas_formatadas = [
            {
                "titulo": vaga.get("title", "Sem título"),
                "empresa": vaga.get("company", "Empresa não informada"),
                "localizacao": vaga.get("location", "Local não informado"),
                "salario": f"{vaga.get('min_amount', 'Não informado')} - {vaga.get('max_amount', 'Não informado')}",
                "data_atualizacao": vaga.get("date_posted", "Data não informada"),
                "link": vaga.get("job_url", "#"),
                "descricao": vaga.get("description", "Descrição não disponível")
            }
            for vaga in vagas_jobspy
        ]

        # Salva no cache por 1 hora
        cache.set(cache_key, str(vagas_formatadas), ex=3600)

        return {"source": "live", "data": vagas_formatadas}

    except Exception as e:
        return {"error": f"Erro ao buscar vagas: {str(e)}"}

# 🔹 Código do Jooble comentado temporariamente. Assim que validarmos a nova API, podemos reativar.
"""
JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
JOOBLE_API_URL = "https://br.jooble.org/api/"

@app.get("/buscar_jooble")
async def buscar_vagas_jooble(termo: str, localizacao: str = "", pagina: int = 1):
    cache_key = f"jooble_{termo}_{localizacao}_{pagina}"
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
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Jooble: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Jooble"}

    novas_vagas = data.get("jobs", [])[:15]

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

    cache.set(cache_key, str(vagas), ex=3600)

    return {"source": "live", "data": vagas}
"""
