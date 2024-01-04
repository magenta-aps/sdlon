from datetime import datetime
from unittest.mock import patch, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from sdlon.main import create_app
from tests.test_fix_departments import _TestableFixDepartments


@patch("sdlon.main.FixDepartments")
@patch("sdlon.main.sd_changed_at_state")
@patch("sdlon.main.dipex_last_success_timestamp")
@patch("sdlon.main.get_changed_at_settings")
@patch("sdlon.main.changed_at")
def test_trigger(
    mock_changed_at: MagicMock,
    mock_get_changed_at_settings: MagicMock,
    mock_dipex_last_success_timestamp: MagicMock,
    mock_sd_changed_at_state: MagicMock,
    mock_fix_departments: MagicMock,
) -> None:
    # Arrange
    app = create_app()
    client = TestClient(app)

    # Act
    r = client.post("/trigger")

    # Assert
    mock_changed_at.assert_called_once_with(
        mock_dipex_last_success_timestamp, mock_sd_changed_at_state
    )
    assert r.json() == {"msg": "SD-changed-at started in background"}


@patch("sdlon.main.get_changed_at_settings")
@patch("sdlon.main.FixDepartments")
def test_trigger_fix_departments(
    mock_fix_dep: MagicMock,
    mock_get_changed_at_settings: MagicMock,
):
    # Arrange
    fix_departments = _TestableFixDepartments.get_instance()
    fix_departments.fix_department = MagicMock()
    fix_departments.fix_NY_logic = MagicMock()
    mock_fix_dep.return_value = fix_departments

    app = create_app()
    client = TestClient(app)

    ou = str(uuid4())
    today = datetime.today().date()

    # Act
    r = client.post(f"/trigger/apply-ny-logic/{ou}")

    # Assert
    fix_departments.fix_NY_logic.assert_called_once_with(ou, today)

    assert r.status_code == 200
    assert r.json() == {"msg": "success"}


@patch("sdlon.main.get_changed_at_settings")
@patch("sdlon.main.FixDepartments")
def test_trigger_fix_departments_on_error(
    mock_fix_dep: MagicMock,
    mock_get_changed_at_settings: MagicMock,
):
    # Arrange
    fix_departments = _TestableFixDepartments.get_instance()
    error = Exception("some error")
    fix_departments.fix_NY_logic = MagicMock(side_effect=error)
    mock_fix_dep.return_value = fix_departments

    app = create_app()
    client = TestClient(app)

    # Act
    r = client.post(f"/trigger/apply-ny-logic/{str(uuid4())}")

    # Assert
    assert r.status_code == 500
    assert r.json() == {"msg": str(error)}
