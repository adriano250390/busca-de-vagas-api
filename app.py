from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis
import os
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = FastAPI()

# Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

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
    
    # 🔹 Adicionando um User-Agent aleatório
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.198 Safari/537.36",
        "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5615.135 Mobile Safari/537.36"
    ]
    chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")

    driver = webdriver.Chrome(options=chrome_options)
    return driver

@app.get("/")
def home():
    """Rota principal da API"""
    return {"message": "API de busca de vagas está rodando!"}

@app.get("/healthz")
@app.head("/healthz")
def health_check():
    """Rota de Health Check"""
    return {"status": "ok"}

def buscar_vagas_indeed(termo: str, localizacao: str = ""):
    """Scraping de vagas no Indeed"""

    cache_key = f"indeed_{termo}_{localizacao}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return eval(cached_data)

    driver = iniciar_driver()

    url = f"https://br.indeed.com/jobs?q={termo}&l={localizacao}"
    driver.get(url)

    try:
        # 🔹 Espera explícita para garantir que os elementos carreguem
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "job_seen_beacon"))
        )
        time.sleep(random.uniform(2, 4))  # 🔹 Pequeno delay randômico

        vagas = []
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
                    "link": link,
                    "fonte": "indeed"
                })
            except Exception as e:
                print(f"Erro ao capturar vaga: {e}")

    except Exception as e:
        print(f"Erro ao buscar vagas no Indeed: {e}")
        vagas = []

    driver.quit()

    # Salvar no cache por 1 hora
    cache.set(cache_key, str(vagas), ex=3600)

    return vagas

@app.get("/buscar")
def buscar_vagas(termo: str, localizacao: str = "", pagina: int = 1):
    """Busca vagas apenas no Indeed (temporariamente, sem Jooble)"""

    indeed_vagas = buscar_vagas_indeed(termo, localizacao)

    return {"source": "indeed_only", "data": indeed_vagas}
