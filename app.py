import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import redis
import os
import httpx
from bs4 import BeautifulSoup

app = FastAPI()

# Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Configuração do CORS para permitir acesso do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gray-termite-250383.hostingersite.com"],  # 🔹 Substituir pelo domínio real do seu site
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/buscar-indeed")
async def buscar_vagas_indeed(termo: str, localizacao: str = ""):
    """Busca vagas no Indeed usando proxy rotativo"""

    cache_key = f"indeed_{termo}_{localizacao}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "vagas": eval(cached_data)}

    url = f"https://br.indeed.com/jobs?q={termo}&l={localizacao}"

    # 🔹 Lista de proxies gratuitos (troque por um serviço pago se necessário)
    proxies = [
        "http://185.199.229.156:7492",
        "http://178.128.122.42:3128",
        "http://64.225.8.192:7497"
    ]
    proxy = random.choice(proxies)  # Escolher um proxy aleatório

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(timeout=10, proxies={"http": proxy, "https": proxy}) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            vagas = []

            elementos_vagas = soup.find_all("div", class_="job_seen_beacon")
            for vaga in elementos_vagas[:15]:
                titulo = vaga.find("h2").get_text(strip=True) if vaga.find("h2") else "Sem título"
                empresa = vaga.find("span", class_="companyName").get_text(strip=True) if vaga.find("span", class_="companyName") else "Empresa não informada"
                local = vaga.find("div", class_="companyLocation").get_text(strip=True) if vaga.find("div", class_="companyLocation") else "Local não informado"
                link = "https://br.indeed.com" + vaga.find("a")["href"] if vaga.find("a") else "#"

                vagas.append({
                    "titulo": titulo,
                    "empresa": empresa,
                    "localizacao": local,
                    "link": link
                })

            # 🔹 Salvar no cache para evitar chamadas repetidas
            cache.set(cache_key, str(vagas), ex=3600)

            return {"source": "live", "vagas": vagas}

        except httpx.HTTPStatusError as e:
            return {"error": f"Erro ao acessar o Indeed: {e.response.status_code}"}
        except Exception as e:
            return {"error": f"Erro desconhecido: {str(e)}"}
