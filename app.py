from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import redis
import os
import asyncio

# 🔹 Novo: importações para o jobspy e CSV
import csv
from jobspy import scrape_jobs

app = FastAPI()

# Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Configuração da API Jooble (COMENTADA PARA TESTES)
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

# ----------------------------------------------------------------------------
# Rota /buscar que, por enquanto, usa APENAS o jobspy (Jooble COMENTADO)
# ----------------------------------------------------------------------------
@app.get("/buscar")
def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """
    Rota que busca vagas usando a biblioteca 'jobspy'.
    O código do Jooble está comentado para testes de configuração.
    Assim que estiver tudo certo, pode-se descomentar o Jooble e unir ambos.
    """

    # =========================================================================
    #                            (JOOBLE COMENTADO)
    # =========================================================================
    #
    # cache_key = f"{termo}_{localizacao}_{pagina}"
    # cached_data = cache.get(cache_key)
    #
    # if cached_data:
    #     return {"source": "cache", "data": eval(cached_data)}
    #
    # payload = {
    #     "keywords": termo,
    #     "location": localizacao,
    #     "page": pagina
    # }
    # headers = {"Content-Type": "application/json"}
    #
    # async with httpx.AsyncClient(timeout=10) as client:
    #     try:
    #         response = await client.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=payload, headers=headers)
    #         response.raise_for_status()  # Lança erro caso a API retorne status != 200
    #         data = response.json()
    #     except httpx.HTTPStatusError as e:
    #         return {"error": f"Erro na API Jooble: {e.response.status_code}"}
    #     except httpx.RequestError:
    #         return {"error": "Erro de conexão com a API Jooble"}
    #
    # novas_vagas = data.get("jobs", [])[:15]
    # if not novas_vagas:
    #     return {"error": "Nenhuma vaga encontrada para esta página."}
    #
    # vagas_jooble = [
    #     {
    #         "titulo": vaga.get("title", "Sem título"),
    #         "empresa": vaga.get("company", "Empresa não informada"),
    #         "localizacao": vaga.get("location", "Local não informado"),
    #         "salario": vaga.get("salary", "Salário não informado"),
    #         "data_atualizacao": vaga.get("updated", "Data não informada"),
    #         "link": vaga.get("link", "#"),
    #         "descricao": vaga.get("snippet", "Descrição não disponível")
    #     }
    #     for vaga in novas_vagas
    # ]
    #
    # # Salva no cache por 1 hora
    # cache.set(cache_key, str(vagas_jooble), ex=3600)
    #
    # return {"source": "live", "data": vagas_jooble}

    # =========================================================================
    #                       (AGORA USANDO jobspy)
    # =========================================================================
    # Aqui configuramos a busca do jobspy:
    # - site_name: lista de plataformas.
    # - search_term: pode usar o termo recebido por parâmetro.
    # - google_search_term: ajustado dinamicamente conforme a cidade.
    # - location: usa a localização recebida ou um default.
    # - results_wanted: quantas vagas no total (ajuste se quiser mais).
    # - hours_old: vagas postadas nas últimas X horas (72 horas no exemplo).
    # - country_indeed: 'Brazil' ou outro caso precise.

    # A lib jobspy não lida diretamente com paginação igual a Jooble.
    # Então, por ora, estamos ignorando o parâmetro 'pagina'.
    # Se quiser fazer algo como slicing manual para simular paginação,
    # você pode ajustar conforme necessário.

    jobs = scrape_jobs(
        site_name=["indeed", "linkedin", "zip_recruiter", "glassdoor", "google", "bayt"],
        search_term=termo if termo else "desenvolvedor Python",
        google_search_term=f"{termo} jobs near {localizacao}" if termo and localizacao else "Python developer jobs near São Paulo, SP",
        location=localizacao if localizacao else "São Paulo, SP",
        results_wanted=15,  # Ajustado para 15, mantendo padrão similar ao Jooble
        hours_old=72,
        country_indeed='Brazil',
    )

    # Se quiser, pode salvar em CSV (opcional):
    # jobs.to_csv("vagas.csv", quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)

    # Agora convertemos o DataFrame para a mesma estrutura esperada pelo front
    vagas = []
    for _, row in jobs.iterrows():
        vagas.append({
            "titulo": row.get("title", "Sem título"),
            "empresa": row.get("company_name", "Empresa não informada"),
            "localizacao": row.get("location", "Local não informado"),
            "salario": row.get("salary", "Salário não informado"),
            "data_atualizacao": row.get("date", "Data não informada"),
            "link": row.get("job_link", "#"),
            "descricao": row.get("snippet") or row.get("summary", "Descrição não disponível")
        })

    if not vagas:
        return {"error": "Nenhuma vaga encontrada."}

    return {"source": "live", "data": vagas}
