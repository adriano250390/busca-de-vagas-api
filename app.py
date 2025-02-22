from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import redis
import os
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

app = FastAPI()

# Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Configuração das APIs
JOOBLE_API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"
JOOBLE_API_URL = "https://br.jooble.org/api/"

# Habilitar CORS corretamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gray-termite-250383.hostingersite.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Configuração do Selenium para scraping do Indeed
def iniciar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Rodar sem abrir janela
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

@app.get("/")
def home():
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")  # 🔹 Suporte para requisições HEAD
def health_check():
    """Rota de Health Check"""
    return {"status": "ok"}

async def buscar_vagas_jooble(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas na API do Jooble"""
    
    cache_key = f"jooble_{termo}_{localizacao}_{pagina}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return eval(cached_data)

    payload = {
        "keywords": termo,
        "location": localizacao,
        "page": pagina
    }
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(f"{JOOBLE_API_URL}{JOOBLE_API_KEY}", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Erro na API Jooble: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Erro de conexão com a API Jooble"}

    vagas = [
        {
            "titulo": vaga.get("title", "Sem título"),
            "empresa": vaga.get("company", "Empresa não informada"),
            "localizacao": vaga.get("location", "Local não informado"),
            "salario": vaga.get("salary", "Salário não informado"),
            "data_atualizacao": vaga.get("updated", "Data não informada"),
            "link": vaga.get("link", "#"),
            "descricao": vaga.get("snippet", "Descrição não disponível")
        }
        for vaga in data.get("jobs", [])[:15]  # 🔹 Retorna apenas 15 vagas
    ]

    # Salva no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)

    return vagas

async def buscar_vagas_indeed(termo: str, localizacao: str = ""):
    """Scraping de vagas no Indeed"""

    cache_key = f"indeed_{termo}_{localizacao}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return eval(cached_data)

    driver = iniciar_driver()

    url = f"https://br.indeed.com/jobs?q={termo}&l={localizacao}"
    driver.get(url)

    time.sleep(5)  # Esperar a página carregar

    vagas = []

    try:
        elementos_vagas = driver.find_elements(By.CLASS_NAME, "job_seen_beacon")

        for vaga in elementos_vagas[:15]:  # Pegar só as 15 primeiras
            try:
                titulo = vaga.find_element(By.CLASS_NAME, "jobTitle").text
                empresa = vaga.find_element(By.CLASS_NAME, "companyName").text
                local = vaga.find_element(By.CLASS_NAME, "companyLocation").text
                link = vaga.find_element(By.TAG_NAME, "a").get_attribute("href")

                vagas.append({
                    "titulo": titulo,
                    "empresa": empresa,
                    "localizacao": local,
                    "link": link
                })
            except Exception as e:
                print(f"Erro ao capturar vaga: {e}")

    except Exception as e:
        print(f"Erro ao buscar vagas no Indeed: {e}")

    driver.quit()

    # Salvar no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)

    return vagas

@app.get("/buscar")
async def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas de emprego no Jooble e no Indeed"""

    # Buscar vagas das duas fontes em paralelo
    jooble_vagas, indeed_vagas = await asyncio.gather(
        buscar_vagas_jooble(termo, localizacao, pagina),
        buscar_vagas_indeed(termo, localizacao)
    )

    # Unir os resultados
    todas_vagas = jooble_vagas + indeed_vagas

    return {"source": "combined", "data": todas_vagas}
