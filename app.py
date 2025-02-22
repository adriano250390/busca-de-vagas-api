from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import redis
import os

app = FastAPI()

# Configuração do Redis (Cache)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# Habilitar CORS corretamente
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

@app.get("/healthz")
@app.head("/healthz")  # 🔹 Suporte para requisições HEAD (necessário para monitoramento)
def health_check():
    """Rota de Health Check"""
    return {"status": "ok"}

# 🔹 NOVA ROTA PARA RECEBER AS VAGAS DO INDEED DO FRONTEND
@app.post("/coletar-indeed")
def coletar_vagas_indeed(dados: dict):
    """Recebe as vagas do Indeed capturadas no frontend e armazena no cache"""
    
    vagas = dados.get("vagas", [])

    if not vagas:
        raise HTTPException(status_code=400, detail="Nenhuma vaga recebida")

    # 🔹 Criar chave de cache para as vagas do Indeed
    cache.set("vagas_indeed", str(vagas), ex=3600)  # Cache por 1 hora

    return {"message": "✅ Vagas do Indeed salvas com sucesso!", "total_vagas": len(vagas)}

@app.get("/buscar-indeed")
def buscar_vagas_indeed():
    """Retorna as vagas do Indeed salvas no cache"""
    
    vagas = cache.get("vagas_indeed")
    return {"vagas": eval(vagas) if vagas else []}
