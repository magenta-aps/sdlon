# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0

FROM python:3.11
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get -y install unixodbc-dev freetds-dev unixodbc tdsodbc libkrb5-dev libmariadb-dev
# These need to be installed manually ALL THE TIME for debugging, so let's
# include them here for now until we have a more stable application
RUN apt-get -y install vim screen
# `./docker/start.sh` requires `psql`
RUN apt-get -y install postgresql-client

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    POETRY_HOME=/opt/poetry \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_VERSION=1.3.1 \
    ENVIRONMENT=production

RUN curl -sSL https://install.python-poetry.org | python3 -
COPY pyproject.toml poetry.lock ./

RUN POETRY_NO_INTERACTION=1 /opt/poetry/bin/poetry install --no-root --no-dev

COPY docker ./docker
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY sdlon ./sdlon
COPY sdtool ./sdtool
COPY db ./db
COPY tests ./tests

CMD ["./docker/start.sh"]
