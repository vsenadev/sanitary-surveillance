FROM python:3.12.10-slim

WORKDIR /app

# Copiar dependências comuns
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da API
COPY . .

# Expor porta da API
EXPOSE 8000

# Rodar com Uvicorn
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
