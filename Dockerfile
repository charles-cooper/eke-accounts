FROM python:3.6-slim

WORKDIR /app

RUN apt-get update -qq
RUN apt-get install -qq -y --fix-missing --no-install-recommends \
      build-essential \
      sqlite3

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt
