FROM python:3.12.10-slim

WORKDIR /app

# Copiar dependências comuns
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código do dashboard
COPY . .

# Expor porta do Streamlit
EXPOSE 8501

# Rodar o app
CMD ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
