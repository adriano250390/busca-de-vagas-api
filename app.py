from fastapi import FastAPI
import requests
import redis
import os
import json
from bs4 import BeautifulSoup  # Importa BeautifulSoup para processar HTML

app = FastAPI()

@app.get("/")
def home():
    return {"message": "API de busca de vagas está rodando!"}

# Configuração do Redis (cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# URL base do site de empregos
BASE_URL = "https://www.empregos.com.br/vagas"

def extrair_dados(html):
    """Extrai informações relevantes das vagas a partir do HTML"""
    soup = BeautifulSoup(html, "html.parser")
    vagas = []

    # Encontrar todas as vagas na página
    for vaga in soup.find_all("div", class_="info_vaga"):  # Ajuste conforme necessário
        titulo_elemento = vaga.find("a", class_="titulo")
        empresa_elemento = vaga.find("a", class_="empresa")
        localizacao_elemento = vaga.find("span", class_="cidade")
        link_elemento = vaga.find("a", class_="titulo")

        # Extraindo os dados corretamente
        titulo = titulo_elemento.text.strip() if titulo_elemento else "Sem título"
        empresa = empresa_elemento.text.strip() if empresa_elemento else "Empresa não informada"
        localizacao = localizacao_elemento.text.strip() if localizacao_elemento else "Local não informado"
        link = f"https://www.empregos.com.br{link_elemento['href']}" if link_elemento else "#"

        vagas.append({
            "titulo": titulo,
            "empresa": empresa,
            "localizacao": localizacao,
            "link": link
        })

    return vagas

@app.get("/buscar")
def buscar_vagas(termo: str):
    """Busca vagas de emprego no site Empregos.com.br e retorna apenas os títulos, links e localizações."""
    cached_data = cache.get(termo)
    if cached_data:
        return {"source": "cache", "data": cached_data}

    url = f"{JOBS_API_URL}/{termo}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        vagas = []

        for vaga in soup.find_all("div", class_="vaga"):  # Ajuste esse seletor se necessário
            titulo_elemento = vaga.find("a", class_="titulo")
            empresa_elemento = vaga.find("span", class_="empresa")
            localizacao_elemento = vaga.find("span", class_="localizacao")
            link_elemento = vaga.find("a", class_="titulo")

            titulo = titulo_elemento.text.strip() if titulo_elemento else "Sem título"
            empresa = empresa_elemento.text.strip() if empresa_elemento else "Empresa não informada"
            localizacao = localizacao_elemento.text.strip() if localizacao_elemento else "Local não informado"
            link = f"https://www.empregos.com.br{link_elemento['href']}" if link_elemento else "#"

            vagas.append({
                "titulo": titulo,
                "empresa": empresa,
                "localizacao": localizacao,
                "link": link
            })

        if not vagas:
            return {"error": "Nenhuma vaga encontrada.", "html": response.text[:1000]}  # Retorna um trecho do HTML para debug

        cache.set(termo, str(vagas), ex=3600)
        return {"source": "live", "data": vagas}

    return {"error": "Falha na busca de vagas"}
