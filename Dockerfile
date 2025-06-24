# Usar uma imagem oficial e leve de Python
FROM python:3.11-slim

# Definir o diretório de trabalho dentro do contentor
WORKDIR /app

# ### ATUALIZAÇÃO ### Instalar o 'curl' para que o Health Check do Coolify funcione
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copiar primeiro o ficheiro de requisitos para otimizar o cache
COPY requirements.txt .

# Instalar as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o resto do código do seu projeto para o contentor
COPY . .

# Expor as portas para o WebSocket e para o Health Check
EXPOSE 8765
EXPOSE 8080

# Comando que será executado quando o contentor iniciar
CMD ["python", "botsock.py"]
