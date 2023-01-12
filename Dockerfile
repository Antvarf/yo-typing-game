FROM python:3

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get -y install daphne python3-dev build-essential libmariadbclient-dev

COPY . /app/
WORKDIR /app/
RUN python3 -m pip install -r requirements.txt
