# Usa uma imagem base oficial do Python.
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container.
WORKDIR /app

# Copia o arquivo de dependências para o diretório de trabalho.
COPY requirements.txt .

# Instala as dependências.
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto para o diretório de trabalho.
COPY . .

# Expõe a porta para métricas Prometheus (opcional).
# EXPOSE 8000

# Comando para executar o bot quando o container iniciar.
# Aponta para o novo ponto de entrada da aplicação.
CMD ["python", "main.py"]
