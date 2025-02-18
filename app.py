from fastapi import FastAPI
import requests
import redis
import os

app = FastAPI()

# 🔑 Chave da API do Scrapingdog
API_KEY = "67b47bd0bc3ed73cbdfab7ba"

# URL base do Scrapingdog para Indeed
SCRAPINGDOG_URL = "https://api.scrapingdog.com/indeed"

# Configuração do Redis (cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

@app.get("/")
def home():
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/buscar")
def buscar_vagas(termo: str, local: str = ""):
    """
    Busca vagas de emprego no Indeed via API do Scrapingdog.
    """

    # Verifica se já tem essa busca no cache
    cache_key = f"{termo}_{local}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return {"source": "cache", "data": cached_data}

    # Criando a URL de busca do Indeed
    job_search_url = f"https://www.indeed.com/jobs?q={termo}&l={local}"

    # Parâmetros para a API do Scrapingdog
    params = {
        "api_key": API_KEY,
        "url": job_search_url
    }

    # Fazendo a requisição via Scrapingdog
    response = requests.get(SCRAPINGDOG_URL, params=params)

    if response.status_code == 200:
        try:
            json_response = response.json()

            # Verifica se há resultados válidos
            if "jobs" not in json_response or not json_response["jobs"]:
                return {"error": "Nenhuma vaga encontrada."}

            vagas = []

            # Processando os dados das vagas
            for vaga in json_response["jobs"]:
                titulo = vaga.get("title", "Sem título")
                empresa = vaga.get("company", "Empresa não informada")
                localizacao = vaga.get("location", "Local não informado")
                link = vaga.get("link", "#")

                vagas.append({
                    "titulo": titulo,
                    "empresa": empresa,
                    "localizacao": localizacao,
                    "link": link
                })

            # Cacheando os resultados por 1 hora
            cache.set(cache_key, str(vagas), ex=3600)

            return {"source": "live", "data": vagas}

        except Exception as e:
            return {"error": "Erro ao processar os dados", "exception": str(e)}

    return {"error": "Falha na busca de vagas", "status_code": response.status_code}
