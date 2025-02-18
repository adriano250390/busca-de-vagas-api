import requests
import json

# Chave da API Jooble
API_KEY = "814146c8-68bb-45cd-acd7-cd907162dc28"

# URL da API do Jooble
url = f"https://br.jooble.org/api/{API_KEY}"

# Parâmetros da busca
payload = {
    "keywords": "engenheiro",
    "location": "Campinas",
    "page": 1
}

# Fazendo a requisição para a API
response = requests.post(url, json=payload)

# Verificando a resposta
if response.status_code == 200:
    data = response.json()
    print(json.dumps(data, indent=4, ensure_ascii=False))  # Exibe o JSON formatado
else:
    print(f"Erro na requisição: {response.status_code}")
    print(response.text)
