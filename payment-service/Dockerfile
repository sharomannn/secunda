# Образ на основе Python 3.11 slim для меньшего размера
FROM python:3.11-slim

# Установка рабочей директории
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Установка Poetry
RUN pip install poetry==1.7.1

# Копирование файлов зависимостей
COPY pyproject.toml poetry.lock* ./

# Установка зависимостей
# Отключаем создание виртуального окружения, т.к. мы уже в контейнере
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Копирование кода приложения
COPY . .

# Установка приложения
RUN poetry install --no-interaction --no-ansi

# Открытие порта для API
EXPOSE 8000

# Команда по умолчанию (может быть переопределена в docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
