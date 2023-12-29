from sqlite3 import Error
from unittest.mock import patch, MagicMock

import pytest

from sdlon.config import ChangedAtSettings
from sdlon.metrics import RunDBState, get_run_db_state
from tests.test_config import DEFAULT_CHANGED_AT_SETTINGS


@pytest.mark.parametrize(
    "run_db_status_line, expected",
    [
        ("Running since", RunDBState.RUNNING),
        ("Update finished", RunDBState.COMPLETED),
        ("Unknown", RunDBState.UNKNOWN),
    ],
)
@patch("sdlon.metrics.DBOverview._read_last_line")
def test_get_run_db_state(
    mock_read_last_line: MagicMock,
    run_db_status_line: str,
    expected: RunDBState,
):
    # Arrange
    mock_read_last_line.return_value = run_db_status_line

    # Act
    state = get_run_db_state(ChangedAtSettings.parse_obj(DEFAULT_CHANGED_AT_SETTINGS))

    # Assert
    assert state == expected


@patch("sdlon.metrics.DBOverview._read_last_line")
def test_get_run_db_state_exception(
    mock_read_last_line: MagicMock,
):
    # Arrange
    mock_read_last_line.side_effect = Error()

    # Act
    state = get_run_db_state(ChangedAtSettings.parse_obj(DEFAULT_CHANGED_AT_SETTINGS))

    # Assert
    assert state == RunDBState.UNKNOWN
