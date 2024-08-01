# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from sdlon.config import get_settings
from sdlon.config import Settings


def get_db_url(settings: Settings) -> str:
    return f"postgresql+psycopg2://{settings.app_dbuser}:{settings.app_dbpassword.get_secret_value()}@{settings.pghost}/{settings.app_database}"  # noqa


def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(get_db_url(settings))
