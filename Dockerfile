FROM python:3.12-slim-bookworm

WORKDIR /app

# Instala git e build-essential necessários para compilar o pandas-ta
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Atualiza o pip e instala as dependências
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main_shock.py"]
