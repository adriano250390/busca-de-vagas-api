from fastapi import FastAPI
import requests
import redis
import os
from bs4 import BeautifulSoup

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

        # 🔍 Testando possíveis seletores
        seletores_teste = ["div.vaga-box", "div.vaga", "div.vaga-container"]

        for seletor in seletores_teste:
            vagas = soup.select(seletor)
            if vagas:
                break  # Se encontrar pelo menos 1 vaga, usa esse seletor
        
        # Se nenhum seletor encontrar vagas, salva o HTML de resposta para debug
        if not vagas:
            with open("debug.html", "w", encoding="utf-8") as file:
                file.write(response.text)
            return {"error": "Nenhuma vaga encontrada.", "url": url, "debug": "Arquivo debug.html salvo"}

        lista_vagas = []
        for vaga in vagas:
            titulo_elemento = vaga.find("a", class_="vaga-titulo") or vaga.find("h2")
            empresa_elemento = vaga.find("span", class_="vaga-empresa") or vaga.find("div", class_="empresa")
            localizacao_elemento = vaga.find("span", class_="vaga-localizacao") or vaga.find("div", class_="localizacao")
            link_elemento = vaga.find("a", class_="vaga-titulo") or vaga.find("a")

            titulo = titulo_elemento.text.strip() if titulo_elemento else "Sem título"
            empresa = empresa_elemento.text.strip() if empresa_elemento else "Empresa não informada"
            localizacao = localizacao_elemento.text.strip() if localizacao_elemento else "Local não informado"
            link = f"https://www.empregos.com.br{link_elemento['href']}" if link_elemento else "#"

            lista_vagas.append({
                "titulo": titulo,
                "empresa": empresa,
                "localizacao": localizacao,
                "link": link
            })

        # Salva no cache apenas se houver resultados
        cache.set(termo, str(lista_vagas), ex=3600)

        return {"source": "live", "data": lista_vagas}

    return {"error": "Falha na busca de vagas"}
