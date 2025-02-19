from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import redis
import os
from datetime import datetime

app = FastAPI()

# 🔵 Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# 🔵 Configuração da API Jooble
JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
JOOBLE_API_URL = "https://br.jooble.org/api/"

# 🔥 Habilitar CORS corretamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gray-termite-250383.hostingersite.com"],  # Permita apenas seu site
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/buscar")
def buscar_vagas(termo: str, localizacao: str = ""):
    """Busca vagas de emprego no Jooble e retorna ordenadas por data (mais recente primeiro)."""

    # 🔴 Verifica se já tem essa busca no cache
    cache_key = f"{termo}_{localizacao}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return {"source": "cache", "data": eval(cached_data)}

    # 🔵 Busca múltiplas páginas da API Jooble
    vagas = []
    pagina = 1
    max_paginas = 5  # Limite de páginas para evitar sobrecarga

    while pagina <= max_paginas:
        payload = {
            "keywords": termo,
            "location": localizacao,
            "page": pagina  # ✅ Paginação ativada
        }
        headers = {"Content-Type": "application/json"}

        response = requests.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=payload, headers=headers)

        if response.status_code == 200:
            data = response.json()
            novas_vagas = data.get("jobs", [])

            if not novas_vagas:  # Se não há mais vagas, parar a busca
                break

            for vaga in novas_vagas:
                # 🔹 Converte a data para um formato comparável
                data_atualizacao = vaga.get("updated", "")

                try:
                    # Tenta converter para o formato correto (Exemplo: "2025-02-19T12:30:00")
                    data_formatada = datetime.strptime(data_atualizacao, "%Y-%m-%dT%H:%M:%S") if data_atualizacao else None
                except:
                    data_formatada = None  # Se falhar, assume que a data não está disponível

                vagas.append({
                    "titulo": vaga.get("title", "Sem título"),
                    "empresa": vaga.get("company", "Empresa não informada"),
                    "localizacao": vaga.get("location", "Local não informado"),
                    "salario": vaga.get("salary", "Salário não informado"),
                    "data_atualizacao": data_atualizacao if data_formatada else "Data não informada",
                    "data_formatada": data_formatada if data_formatada else datetime.min,  # Definir datetime.min se a data for inválida
                    "link": vaga.get("link", "#"),
                    "descricao": vaga.get("snippet", "Descrição não disponível")
                })

            pagina += 1  # Avança para a próxima página

        else:
            return {"error": "Erro ao buscar vagas", "status_code": response.status_code}

    if not vagas:
        return {"error": "Nenhuma vaga encontrada."}

    # 🔵 Ordenar vagas por data (mais recente primeiro)
    vagas.sort(key=lambda x: x["data_formatada"], reverse=True)

    # 🔵 Remove o campo auxiliar "data_formatada" antes de retornar os resultados
    for vaga in vagas:
        vaga.pop("data_formatada", None)

    # 🔵 Salva no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)

    return {"source": "live", "data": vagas}
