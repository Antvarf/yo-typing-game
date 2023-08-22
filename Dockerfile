FROM python:3.10
ARG GIT_VERSION_TAG=unspecified
SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get -y install daphne python3-dev build-essential libmariadb-dev

COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

ENV VERSION=$GIT_VERSION_TAG

COPY . /app/
WORKDIR /app/
RUN python3 /app/manage.py collectstatic --no-input
