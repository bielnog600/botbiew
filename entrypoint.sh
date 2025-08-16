#!/bin/sh

# Garante que o script pare se algum comando falhar
set -e

echo "--- A executar o Entrypoint Script ---"

# 1. Atualiza a lista de pacotes do sistema
echo "-> A atualizar a lista de pacotes (apt update)..."
apt-get update -y

# 2. Instala as dependências do sistema necessárias para o Chrome e ChromeDriver
echo "-> A instalar dependências do sistema para o navegador..."
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
    libgtk-3-0

echo "-> Dependências do sistema instaladas com sucesso."

# 3. Instala as dependências Python do seu projeto
echo "-> A instalar dependências Python do requirements.txt..."
pip install --no-cache-dir -r requirements.txt

echo "--- Entrypoint Script concluído. A iniciar o bot... ---"

# 4. Executa o comando principal da sua aplicação
# Este comando executa o seu ficheiro main.py. O "$@" passa quaisquer
# argumentos extras que possa ter configurado no Coolify.
exec "$@"
