from fastapi import FastAPI
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

    # Envia a requisição para a API do Jooble
    payload = {"keywords": termo, "location": localizacao}
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        
        # Processa os resultados e adiciona a data
        vagas = []
        for vaga in data.get("jobs", []):
            vagas.append({
                "titulo": vaga.get("title", "Sem título"),
                "empresa": vaga.get("company", "Empresa não informada"),
                "localizacao": vaga.get("location", "Local não informado"),
                "salario": vaga.get("salary", "Salário não informado"),
                "data_atualizacao": vaga.get("updated", "Data não informada"),
                "link": vaga.get("link", "#")
            })
        
        if not vagas:
            return {"error": "Nenhuma vaga encontrada."}

        # Salva no cache por 1 hora
        cache.set(cache_key, str(vagas), ex=3600)

        return {"source": "live", "data": vagas}

    return {"error": "Falha na busca de vagas", "status_code": response.status_code}
