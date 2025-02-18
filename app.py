from fastapi import FastAPI
import requests
import redis
import os
from bs4 import BeautifulSoup  # Importa BeautifulSoup para processar o HTML

app = FastAPI()

@app.get("/")
def home():
    return {"message": "API de busca de vagas está rodando!"}

# Configuração do Redis (cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# URL base do site de empregos
JOBS_API_URL = "https://www.empregos.com.br/vagas"

@app.get("/buscar")
def buscar_vagas(termo: str, cidade: str = None):
    """Busca vagas de emprego no site Empregos.com.br e retorna títulos, empresas e localizações."""
    
    # Construção da URL com cargo e cidade
    if cidade:
        url = f"{JOBS_API_URL}/{cidade.replace(' ', '-').lower()}/sp/{termo.replace(' ', '-').lower()}"
    else:
        url = f"{JOBS_API_URL}/{termo.replace(' ', '-').lower()}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")

        # Lista para armazenar as vagas
        vagas = []

        # Encontrando todas as vagas no HTML correto
        for vaga in soup.find_all("div", class_="vaga-box"):  # Ajuste conforme a estrutura do HTML
            titulo_elemento = vaga.find("a", class_="vaga-titulo")
            empresa_elemento = vaga.find("span", class_="vaga-empresa")
            localizacao_elemento = vaga.find("span", class_="vaga-localizacao")
            link_elemento = vaga.find("a", class_="vaga-titulo")

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

        if vagas:
            cache.set(termo, str(vagas), ex=3600)  # Cache por 1 hora
            return {"source": "live", "data": vagas}
        else:
            return {"error": "Nenhuma vaga encontrada.", "html": response.text[:1000]}

    return {"error": "Falha na busca de vagas"}
