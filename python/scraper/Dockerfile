FROM python:3.12.10-slim-bookworm

# Evitar prompts durante instalação
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências do Chromium e Selenium
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxrender1 \
    libxext6 \
    libx11-xcb1 \
    libxcb1 \
    libdbus-1-3 \
    fonts-liberation \
    libappindicator3-1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar dependências do projeto
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o restante do código
COPY . .

# Comando padrão
CMD ["python", "cpsc_scraper.py"]
