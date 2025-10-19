# 1. Usa uma imagem base oficial do Python 3.10.
FROM python:3.10-slim

# 2. Define o diretório de trabalho dentro do container.
WORKDIR /app

# 3. Copia o arquivo de dependências primeiro para otimizar o cache.
COPY requirements.txt .

# 4. Instala as dependências.
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia todo o código do projeto para o diretório de trabalho.
COPY . .

# 6. Comando para executar o bot quando o container iniciar.
CMD ["python", "main.py"]

