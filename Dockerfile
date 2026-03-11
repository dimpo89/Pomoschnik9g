FROM python:3.9-slim

WORKDIR /app

# Устанавливаем только необходимые системные библиотеки
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем только requirements.txt сначала для кэширования
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .

CMD ["python", "bot.py"]
