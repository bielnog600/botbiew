# Stage final
FROM python:3.10-slim

WORKDIR /app

# Instala as libs nativas do TA-Lib
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libta-lib0 \
      libta-lib-dev \
 && rm -rf /var/lib/apt/lists/*

# Copia requirements e instala tudo (incluindo TA-Lib)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "app.main"]
