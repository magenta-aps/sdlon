import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from pytest import MonkeyPatch

from sdlon.config import Settings
from sdlon.engagement import get_eng_user_key
from sdlon.models import JobFunction
from sdlon.sd_common import read_employment_at
from sdlon.sd_common import sd_lookup


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        municipality_name="name",
        municipality_code=100,
        sd_global_from_date=date(2000, 1, 1),
        sd_institution_identifier="dummy",
        sd_user="user",
        sd_password="password",
        sd_job_function=JobFunction.employment_name,
        sd_monthly_hourly_divide=1,
        app_dbpassword="secret",
    )


@patch("sdlon.sd_common.sd_lookup")
def test_return_none_when_sd_employment_empty(
    mock_sd_lookup,
    settings: Settings,
) -> None:
    mock_sd_lookup.return_value = OrderedDict()
    assert isinstance(settings.sd_institution_identifier, str)
    assert (
        read_employment_at(
            date(2000, 1, 1), settings, settings.sd_institution_identifier
        )
        is None
    )


@dataclass
class _MockResponse:
    text: str
    status_code: int


def test_sd_lookup_logs_payload_to_db(
    monkeypatch: MonkeyPatch,
    settings: Settings,
) -> None:
    # Arrange
    test_request_uuid = uuid.uuid4()
    test_url: str = "test_url"
    test_params: dict[str, Any] = {"params": "mocked"}
    test_response: str = f"""<{test_url}><Foo bar="baz"></Foo></{test_url}>"""
    test_status_code = 200

    def mock_requests_get(url: str, **kwargs: Any):
        return _MockResponse(text=test_response, status_code=test_status_code)

    def mock_log_payload(
        request_uuid: uuid.UUID,
        full_url: str,
        params: str,
        response: str,
        status_code: int,
    ):
        # Assert
        assert request_uuid == test_request_uuid
        assert full_url.endswith(test_url)
        assert params == str(test_params)
        assert response == test_response
        assert status_code == test_status_code

    monkeypatch.setattr("sdlon.sd_common.requests.get", mock_requests_get)
    monkeypatch.setattr("sdlon.sd_common.log_payload", mock_log_payload)

    # Act
    sd_lookup(test_url, settings, test_params, request_uuid=test_request_uuid)


@patch("sdlon.sd_common.requests")
@patch("sdlon.sd_common.log_payload")
def test_sd_lookup_does_not_persist_payload_when_disabled_in_settings(
    mock_log_payload: MagicMock,
    mock_requests: MagicMock,
    settings: Settings,
):
    # Arrange
    settings.sd_persist_payloads = False

    mock_requests.get.return_value = _MockResponse(
        text="<SomeSDEndpoint><foo></foo></SomeSDEndpoint>", status_code=200
    )

    # Act
    sd_lookup("SomeSDEndpoint", settings)

    # Assert
    mock_log_payload.assert_not_called()


@patch("sdlon.sd_common.requests")
@patch("sdlon.sd_common.log_payload")
def test_sd_lookup_does_not_persist_payload_when_dry_run(
    mock_log_payload: MagicMock,
    mock_requests: MagicMock,
    settings: Settings,
):
    # Arrange
    mock_requests.get.return_value = _MockResponse(
        text="<SomeSDEndpoint><foo></foo></SomeSDEndpoint>", status_code=200
    )

    # Act
    sd_lookup("SomeSDEndpoint", settings, dry_run=True)

    # Assert
    mock_log_payload.assert_not_called()


@pytest.mark.parametrize(
    "prefix_enabled, sd_emp_id, sd_inst_id, expected",
    [
        (False, "12345", "II", "12345"),
        (False, "45", "II", "00045"),
        (True, "23456", "AB", "AB-23456"),
        (True, "56", "AB", "AB-00056"),
    ],
)
def test_get_eng_user_key(
    prefix_enabled: bool,
    sd_emp_id: str,
    sd_inst_id: str,
    expected: str,
):
    # Act
    user_key = get_eng_user_key(sd_emp_id, sd_inst_id, prefix_enabled)

    # Assert
    assert user_key == expected
