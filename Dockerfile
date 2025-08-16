# Usa uma imagem base oficial do Python.
FROM python:3.10-slim

# 1. Instala as dependências do sistema necessárias para o Chrome e ChromeDriver
# O RUN é executado como root por padrão, então não precisamos de 'sudo'.
RUN apt-get update -y && \
    apt-get install -y \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libatspi2.0-0 \
    libgtk-3-0 && \
    # Limpa o cache do apt para manter a imagem pequena
    rm -rf /var/lib/apt/lists/*

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
