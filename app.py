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
    allow_origins=["https://gray-termite-250383.hostingersite.com"],  # Permite apenas seu site
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/buscar")
def buscar_vagas(localizacao: str, termo: str = None):
    """Busca vagas de emprego no Jooble e retorna ordenadas por data (mais recente primeiro)."""

    # ✅ A cidade é obrigatória, mas o cargo (termo) é opcional
    if not localizacao:
        return {"error": "A cidade é obrigatória."}

    # 🔴 Verifica se já tem essa busca no cache
    cache_key = f"{termo or 'todas'}_{localizacao}"
    cached_data = cache.get(cache_key)
    if cached_data:
        try:
            return {"source": "cache", "data": eval(cached_data)}
        except:
            pass  # Evita erro caso o cache esteja corrompido

    # 🔵 Busca múltiplas páginas da API Jooble
    vagas = []
    pagina = 1
    max_paginas = 5  # Limite de páginas para evitar sobrecarga

    while pagina <= max_paginas:
        payload = {"location": localizacao, "page": pagina}
        if termo:
            payload["keywords"] = termo  # ✅ Adiciona o cargo apenas se for informado

        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=payload, headers=headers)

            if response.status_code != 200:
                return {"error": f"Erro ao buscar vagas (HTTP {response.status_code})"}

            data = response.json()
            novas_vagas = data.get("jobs", [])

            if not novas_vagas:
                break  # Para se não houver mais resultados

            for vaga in novas_vagas:
                data_atualizacao = vaga.get("updated", "")
                try:
                    data_formatada = datetime.strptime(data_atualizacao, "%Y-%m-%dT%H:%M:%S") if data_atualizacao else None
                except:
                    data_formatada = None  # Se falhar, assume que a data não está disponível

                vagas.append({
                    "titulo": vaga.get("title", "Sem título"),
                    "empresa": vaga.get("company", "Empresa não informada"),
                    "localizacao": vaga.get("location", "Local não informado"),
                    "salario": vaga.get("salary", "Salário não informado"),
                    "data_atualizacao": data_atualizacao if data_formatada else "Data não informada",
                    "data_formatada": data_formatada if data_formatada else datetime.min,
                    "link": vaga.get("link", "#"),
                    "descricao": vaga.get("snippet", "Descrição não disponível")
                })

            pagina += 1  # Avança para a próxima página

        except requests.exceptions.RequestException as e:
            return {"error": f"Erro ao conectar na API Jooble: {str(e)}"}

    if not vagas:
        return {"error": "Nenhuma vaga encontrada."}

    # 🔵 Ordenar vagas por data (mais recente primeiro)
    vagas.sort(key=lambda x: x["data_formatada"], reverse=True)

    for vaga in vagas:
        vaga.pop("data_formatada", None)

    # 🔵 Salva no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)

    return {"source": "live", "data": vagas}
