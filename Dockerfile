FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY server.py gunicorn_config.py ./

CMD gunicorn --config gunicorn_config.py server:app 