# Python3 Application

Лаба дисциплины "Базы данных" (модуль 4)

## Стек технологий

- Python 3 (фреймворк tornado)
- Redis в качестве хранилки
- uv для управления зависимостями и версионирования

## Быстрый старт

```bash
# 1. Запустить Redis через Docker
docker-compose up -d

# 2. Установить зависимости
uv sync

# 3. Запустить приложение
uv run python main.py
```

Приложение будет доступно по адресу http://localhost:8888

## Установка uv

Для установки uv выполните одну из команд:

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Или через pip
pip install uv
```

## Локальный запуск

*примеры команд ниже указаны для unix-подобных ОС, с виндой разбирайтесь сами*

### С использованием uv (рекомендуется)

1. **Запускаем Redis** (выберите один из вариантов):

   **Вариант A: Через Docker (рекомендуется)**
   ```bash
   # Запустить Redis в фоновом режиме
   docker-compose up -d
   
   # Проверить статус
   docker-compose ps
   
   # Остановить Redis
   docker-compose down
   ```

   **Вариант B: Установка Redis локально**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install redis-server
   sudo systemctl start redis-server
   
   # macOS (с Homebrew)
   brew install redis
   brew services start redis
   
   # Проверить подключение
   redis-cli ping  # Должен вернуть PONG
   ```

2. Устанавливаем зависимости и создаем виртуальное окружение:
   ```bash
   uv sync
   ```
   Эта команда создаст виртуальное окружение и установит все зависимости из `pyproject.toml`

3. Активируем виртуальное окружение:
   ```bash
   source .venv/bin/activate  # Linux/macOS
   # или
   .venv\Scripts\activate  # Windows
   ```

4. При необходимости, меняем адрес сервера Redis в 12 строке файла `main.py`

5. Запускаем веб-сервис:
   ```bash
   python main.py
   ```
   Или используя uv:
   ```bash
   uv run python main.py
   ```

### Традиционный способ (с pip)

1. **Запускаем Redis** (см. инструкции выше в разделе "С использованием uv")

2. Устанавливаем Python 3 и пакетный менеджер pip для своей ОС

3. При необходимости, меняем адрес сервера Redis в 12 строке файла `main.py`

4. Ставим необходимые зависимости:
   ```bash
   pip3 install -r requirements.txt
   ```

5. Запускаем веб-сервис:
   ```bash
   python3 main.py
   ```

## Управление зависимостями с uv

```bash
# Установить все зависимости (включая dev)
uv sync

# Установить только production зависимости
uv sync --no-dev

# Добавить новую зависимость
uv add package-name

# Добавить dev зависимость
uv add --dev package-name

# Обновить зависимости
uv sync --upgrade

# Показать дерево зависимостей
uv tree
```

## Запуск тестов

```bash
# С использованием uv
uv run pytest test_main.py -v

# Или после активации виртуального окружения
pytest test_main.py -v
```

## Версионирование проекта

Версия проекта указана в `pyproject.toml` в секции `[project]`:
```toml
version = "1.0.0"
```

Для обновления версии измените значение в `pyproject.toml` и выполните:
```bash
uv sync
```

## Дополнительно

Сервис доступен по адресу http://localhost:8888
