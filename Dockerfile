FROM python:3.11-slim

WORKDIR /app

COPY warehouse_bot.py .

RUN pip install --no-cache-dir aiogram==2.25.1

CMD ["python", "warehouse_bot.py"]
