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
    allow_origins=["https://gray-termite-250383.hostingersite.com"],  # 🔹 Substituir pelo domínio real do site
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")  # 🔹 Suporte para requisições HEAD (monitoramento)
def health_check():
    """Rota de Health Check"""
    return {"status": "ok"}

# 🔹 ROTA PARA RECEBER AS VAGAS DO INDEED DO FRONTEND (caso seja necessário no futuro)
@app.post("/coletar-indeed")
def coletar_vagas_indeed(dados: dict):
    """Recebe vagas do Indeed capturadas pelo frontend e salva no cache"""

    vagas = dados.get("vagas", [])

    if not vagas:
        raise HTTPException(status_code=400, detail="Nenhuma vaga recebida")

    # 🔹 Criar chave de cache para armazenar as vagas
    cache.set("vagas_indeed", str(vagas), ex=3600)  # Cache por 1 hora

    return {"message": "✅ Vagas do Indeed salvas com sucesso!", "total_vagas": len(vagas)}

@app.get("/buscar-indeed")
async def buscar_vagas_indeed(termo: str, localizacao: str = ""):
    """Busca vagas no Indeed via scraping e retorna JSON"""

    cache_key = f"indeed_{termo}_{localizacao}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return {"source": "cache", "vagas": eval(cached_data)}

    url = f"https://br.indeed.com/jobs?q={termo}&l={localizacao}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text  # Pegamos o HTML da página

            # 🔹 Usando BeautifulSoup para extrair as vagas
            soup = BeautifulSoup(html, "html.parser")
            vagas = []

            elementos_vagas = soup.find_all("div", class_="job_seen_beacon")
            for vaga in elementos_vagas[:15]:  # Pegamos as 15 primeiras
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

            # 🔹 Armazena no cache para evitar chamadas repetidas
            cache.set(cache_key, str(vagas), ex=3600)

            return {"source": "live", "vagas": vagas}

        except httpx.HTTPStatusError as e:
            return {"error": f"Erro ao acessar o Indeed: {e.response.status_code}"}
        except Exception as e:
            return {"error": f"Erro desconhecido: {str(e)}"}
