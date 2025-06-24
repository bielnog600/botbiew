# Use uma imagem base oficial do Python.
# Usar uma versão específica (ex: 3.10-slim) é uma boa prática para consistência.
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia o arquivo de dependências para o diretório de trabalho
COPY requirements.txt .

# Instala as dependências listadas no requirements.txt
# --no-cache-dir reduz o tamanho da imagem
# --upgrade pip garante que temos a versão mais recente do pip
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copia o resto dos arquivos da sua aplicação para o diretório de trabalho
COPY . .

# Comando que será executado quando o container iniciar
# Isso executa o seu script do bot.
CMD ["python", "trading_bot.py"]
