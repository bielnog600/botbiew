# ----------------------------------------
# FASE 1: Build
# ----------------------------------------
# Define a imagem base do Python. A versão 'slim' é mais leve.
FROM python:3.10-slim AS builder

# Define o diretório de trabalho dentro do contêiner.
WORKDIR /app

# Instala as dependências do sistema necessárias para o Selenium e o Chrome.
# A adição de 'build-essential' permite a compilação de pacotes a partir do código-fonte.
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    tini \
    wget \
    unzip \
    build-essential \
    libglib2.0-0 libnss3 libfontconfig1 libx11-6 libx11-xcb1 \
    libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 \
    libxi6 libxrandr2 libxrender1 libxss1 libxtst6 libasound2 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdbus-1-3 libatspi2.0-0 libgtk-3-0 && \
    rm -rf /var/lib/apt/lists/*

# Baixa e instala o Google Chrome para o Selenium.
RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/139.0.7258.68/linux64/chrome-linux64.zip -O chrome.zip && \
    unzip chrome.zip && \
    rm chrome.zip && \
    mv chrome-linux64 /opt/chrome

# Baixa e instala o ChromeDriver correspondente.
RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/139.0.7258.68/linux64/chromedriver-linux64.zip -O chromedriver.zip && \
    unzip chromedriver.zip && \
    rm chromedriver.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver

# Copia o arquivo de dependências para o contêiner.
COPY requirements.txt .

# Instala as dependências Python.
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------
# FASE 2: Final
# ----------------------------------------
# Define a imagem final, mais leve que a de build.
FROM python:3.10-slim

WORKDIR /app

# Copia as dependências do sistema instaladas na fase de build.
COPY --from=builder /usr/lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu
COPY --from=builder /lib/x86_64-linux-gnu /lib/x86_64-linux-gnu

# Copia o Chrome e o ChromeDriver da fase de build.
COPY --from=builder /opt/chrome /opt/chrome
COPY --from=builder /usr/local/bin/chromedriver /usr/local/bin/chromedriver

# Copia as bibliotecas Python instaladas da fase de build.
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

# Copia o Tini para ser o entrypoint.
COPY --from=builder /usr/bin/tini /usr/bin/tini

# Copia todo o código do projeto para o diretório de trabalho.
COPY . .

# Define o entrypoint para usar o Tini, que gerencia processos zumbis.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Comando para executar a aplicação quando o contêiner iniciar.
CMD ["python", "main.py"]
