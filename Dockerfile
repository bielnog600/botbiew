# Usa uma imagem base oficial do Python.
FROM python:3.10-slim

# --- CORREÇÃO: Define a versão exata e compatível do Chrome/ChromeDriver ---
ENV CHROME_VERSION="139.0.7258.68"

# 1. Instala as dependências do sistema e utilitários (wget, unzip)
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    wget \
    unzip \
    # Dependências do Chrome (com o pacote obsoleto removido)
    libglib2.0-0 libnss3 libfontconfig1 libx11-6 libx11-xcb1 \
    libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 \
    libxi6 libxrandr2 libxrender1 libxss1 libxtst6 libasound2 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdbus-1-3 libatspi2.0-0 libgtk-3-0 && \
    # Limpa o cache do apt para manter a imagem pequena
    rm -rf /var/lib/apt/lists/*

# 2. Descarrega e instala o Google Chrome
RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip -O chrome.zip && \
    unzip chrome.zip && \
    rm chrome.zip && \
    mv chrome-linux64 /opt/chrome

# 3. Descarrega e instala o ChromeDriver
RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip -O chromedriver.zip && \
    unzip chromedriver.zip && \
    rm chromedriver.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver

# Adiciona o Chrome ao PATH do sistema
ENV PATH="/opt/chrome:${PATH}"

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# Copia o arquivo de dependências para o diretório de trabalho.
COPY requirements.txt .

# Instala as dependências Python.
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto para o diretório de trabalho.
COPY . .

# Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]
