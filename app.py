from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import redis
import os

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
    allow_origins=["https://gray-termite-250383.hostingersite.com"],  # Permite apenas seu site
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/buscar")
def buscar_vagas(termo: str, localizacao: str = ""):
    """Busca vagas de emprego no Jooble e retorna títulos, empresas, localizações e datas."""

    # Verifica se já tem essa busca no cache
    cache_key = f"{termo}_{localizacao}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # Busca múltiplas páginas da API Jooble
    vagas = []
    pagina = 1
    max_paginas = 5  # Limite de páginas para evitar sobrecarga

    while pagina <= max_paginas:
        payload = {
            "keywords": termo,
            "location": localizacao,
            "page": pagina  # Paginação ativada
        }
        headers = {"Content-Type": "application/json"}

        response = requests.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=payload, headers=headers)

        if response.status_code == 200:
            data = response.json()

            # (Opcional) Para depurar, veja o que a API está devolvendo:
            # print(data)

            novas_vagas = data.get("jobs", [])
            if not novas_vagas:  # Se não há mais vagas, parar a busca
                break

            for vaga in novas_vagas:
                vagas.append({
                    "titulo": vaga.get("title", "Sem título"),
                    "empresa": vaga.get("company", "Empresa não informada"),
                    "localizacao": vaga.get("location", "Local não informado"),
                    "salario": vaga.get("salary", "Salário não informado"),
                    "data_atualizacao": vaga.get("updated", "Data não informada"),
                    "link": vaga.get("link", "#"),
                    "descricao": vaga.get("snippet", "Descrição não disponível")
                })

            pagina += 1  # Avança para a próxima página

        else:
            return {"error": "Erro ao buscar vagas", "status_code": response.status_code}

    if not vagas:
        return {"error": "Nenhuma vaga encontrada."}

    # Salva no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)

    return {"source": "live", "data": vagas}
