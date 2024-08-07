# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from unittest.mock import MagicMock
from unittest.mock import patch

from pytest import MonkeyPatch
from sqlalchemy.engine import Engine

from db import engine
from sdlon.config import Settings
from tests.test_config import DEFAULT_CHANGED_AT_SETTINGS


def test_get_db_url_success(monkeypatch: MonkeyPatch) -> None:
    # Arrange
    settings = Settings.parse_obj(DEFAULT_CHANGED_AT_SETTINGS)

    # Act
    db_url: str = engine.get_db_url(settings)

    # Assert
    assert db_url == "postgresql+psycopg2://sd_payload:secret@sd-db/sd_payload"


@patch(
    "db.engine.get_settings",
    return_value=Settings.parse_obj(DEFAULT_CHANGED_AT_SETTINGS),
)
def test_get_engine(mock_get_settings: MagicMock) -> None:
    result: Engine = engine.get_engine()
    assert isinstance(result, Engine)
