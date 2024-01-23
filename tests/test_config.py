import json
from copy import deepcopy
from typing import Any
from typing import Dict
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from sdlon.config import Settings, json_file_settings, get_settings


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("SD_INSTITUTION_IDENTIFIER", "institution_id")
    monkeypatch.setenv("SD_USER", "env_user")
    monkeypatch.setenv("SD_PASSWORD", "env_pwd")
    monkeypatch.setenv("SD_JOB_FUNCTION", "EmploymentName")
    monkeypatch.setenv("SD_MONTHLY_HOURLY_DIVIDE", "80000")
    monkeypatch.setenv("SD_IMPORT_RUN_DB", "env_run_db")
    monkeypatch.setenv("SD_GLOBAL_FROM_DATE", "2022-01-09")
    monkeypatch.setenv("APP_DBPASSWORD", "secret")
    monkeypatch.setenv("MUNICIPALITY_NAME", "name")
    monkeypatch.setenv("MUNICIPALITY_CODE", 100)


DEFAULT_MOCK_SETTINGS = {
    "integrations.SD_Lon.employment_field": "extension_1",
    "integrations.SD_Lon.global_from_date": "2022-01-09",
    "integrations.SD_Lon.import.run_db": "run_db.sqlite",
    "integrations.SD_Lon.institution_identifier": "XYZ",
    "integrations.SD_Lon.job_function": "EmploymentName",
    "integrations.SD_Lon.monthly_hourly_divide": 50000,
    "integrations.SD_Lon.sd_user": "user",
    "integrations.SD_Lon.sd_password": "password",
    "municipality.code": 740,
    "municipality.name": "Kolding Kommune",
    "app_dbpassword": "secret",
}

DEFAULT_EXPECTED_SETTINGS: Dict[str, Any] = {
    "mora_base": "http://mo-service:5000",
    "mox_base": "http://mo-service:5000/lora",
    "municipality_code": 740,
    "municipality_name": "Kolding Kommune",
    "cpr_uuid_map_path": "/opt/dipex/os2mo-data-import-and-export/settings/cpr_uuid_map.csv",
    "sd_employment_field": "extension_1",
    "sd_global_from_date": "2022-01-09",
    "sd_import_too_deep": [],
    "sd_importer_create_associations": True,
    "sd_importer_create_email_addresses": True,
    "sd_institution_identifier": "XYZ",
    "sd_job_function": "EmploymentName",
    "sd_monthly_hourly_divide": 50000,
    "sd_no_salary_minimum_id": None,
    "sd_password": "**********",
    "sd_skip_employment_types": [],
    "sd_use_ad_integration": True,
    "sd_phone_number_id_for_ad_creation": False,
    "sd_phone_number_id_for_ad_string": "AD-bruger fra SD",
    "sd_phone_number_id_trigger": "14",
    "sd_user": "user",
    "log_level": "DEBUG",
    "sd_persist_payloads": True,
    "job_settings": {
        "auth_realm": "mo",
        "auth_server": "http://keycloak:8080/auth",
        "client_id": "dipex",
        "client_secret": None,
        "log_format": "%(levelname)s %(asctime)s %(filename)s:%(lineno)d:%(name)s: %(message)s",
        "log_level": "ERROR",
        "mora_base": "http://mo:5000",
        "sentry_dsn": None,
    },
    "app_database": "sd",
    "app_dbuser": "sd",
    "app_dbpassword": "**********",
    "pghost": "sd-db",
    "sd_cprs": [],
    "sd_exclude_cprs_mode": True,
    "sd_fix_departments_root": None,
    "sd_overwrite_existing_employment_name": True,
    "sd_read_forced_uuids": True,
    "sd_update_primary_engagement": True,
}

DEFAULT_FILTERED_JSON_SETTINGS = {
    "sd_employment_field": "extension_1",
    "sd_global_from_date": "2022-01-09",
    "sd_institution_identifier": "XYZ",
    "sd_job_function": "EmploymentName",
    "sd_monthly_hourly_divide": 50000,
    "sd_user": "user",
    "sd_password": "password",
    "municipality_code": 740,
    "municipality_name": "Kolding Kommune",
    "app_dbpassword": "secret",
}

DEFAULT_CHANGED_AT_SETTINGS = {
    "municipality_name": "Kommune",
    "municipality_code": 100,
    "sd_employment_field": "extension_1",
    "sd_global_from_date": "2022-01-09",
    "sd_institution_identifier": "XY",
    "sd_job_function": "EmploymentName",
    "sd_monthly_hourly_divide": 9000,
    "sd_password": "secret",
    "sd_user": "user",
    "pghost": "sd-db",
    "app_database": "sd_payload",
    "app_dbuser": "sd_payload",
    "app_dbpassword": "secret",
}


def test_forbid_extra_settings():
    with pytest.raises(ValidationError):
        Settings(
            municipality_name="name",
            municipality_code=100,
            sd_global_from_date="1970-01-01",
            sd_employment_field="extension_1",
            sd_institution_identifier="XY",
            sd_job_function="EmploymentName",
            sd_monthly_hourly_divide=9000,
            sd_password="secret",
            sd_user="user",
            forbidden="property",
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("mora_base", "Not a URL"),
        ("mox_base", "Not a URL"),
        ("municipality_code", 98),
        ("municipality_code", 1000),
        ("sd_employment_field", "extension_"),
        ("sd_employment_field", "Invalid string"),
        ("sd_global_from_date", "Invalid string"),
        ("sd_job_function", "not allowed"),
        ("sd_monthly_hourly_divide", -1),
    ],
)
def test_special_values(key, value):
    # Arrange
    mock_settings = deepcopy(DEFAULT_MOCK_SETTINGS)
    mock_settings[key] = value

    # Act and assert
    with pytest.raises(ValidationError):
        Settings.parse_obj(mock_settings)


@pytest.mark.parametrize("job_function", ["JobPositionIdentifier", "EmploymentName"])
def test_job_function_enums_allowed(job_function):
    assert Settings(
        municipality_name="name",
        municipality_code=100,
        sd_global_from_date="1970-01-01",
        sd_employment_field="extension_1",
        sd_institution_identifier="XY",
        sd_job_function=job_function,
        sd_monthly_hourly_divide=9000,
        sd_password="secret",
        sd_user="user",
        app_dbpassword="secret",
    )


@pytest.mark.parametrize(
    "key,valid_value,invalid_value",
    [
        ("sd_fix_departments_root", str(uuid4()), "not a UUID"),
        ("sd_cprs", ["1234561234", "6543214321"], ["Not CPR"]),
        ("sd_cprs", ["0000000000"], "Not list of CPRs"),
        ("sd_exclude_cprs_mode", False, "Not a boolean"),
    ],
)
def test_changed_at_settings(key, valid_value, invalid_value):
    settings = deepcopy(DEFAULT_CHANGED_AT_SETTINGS)

    # The setting is optional or has a default
    assert Settings.parse_obj(settings)

    # ... and can be set to a valid_value
    settings.update({key: valid_value})
    assert Settings.parse_obj(settings)

    # ... but not an invalid_value
    settings.update({key: invalid_value})
    with pytest.raises(ValidationError):
        Settings.parse_obj(settings)


@patch("sdlon.config.load_settings")
def test_json_file_settings(mock_load_settings):
    # Arrange
    mock_load_settings.return_value = DEFAULT_MOCK_SETTINGS

    # Act
    settings = json_file_settings(None)

    # Assert
    assert settings == DEFAULT_FILTERED_JSON_SETTINGS


@patch("sdlon.config.load_settings")
def test_json_file_settings_remove_unknown_settings(mock_load_settings):
    # Arrange
    mock_settings = deepcopy(DEFAULT_MOCK_SETTINGS)
    mock_settings.update({"unknown": "property"})
    mock_load_settings.return_value = mock_settings

    # Act
    settings = json_file_settings(None)

    # Assert
    assert settings == DEFAULT_FILTERED_JSON_SETTINGS


@patch("sdlon.config.load_settings")
def test_empty_dict_on_file_not_found_error(mock_load_settings):
    # Arrange
    mock_load_settings.side_effect = FileNotFoundError()

    # Act
    json_settings = json_file_settings(None)

    # Assert
    assert json_settings == dict()


@patch("sdlon.config.load_settings")
def test_set_defaults(mock_load_settings):
    # Arrange
    mock_load_settings.return_value = DEFAULT_MOCK_SETTINGS

    # Act
    get_settings.cache_clear()
    settings_input = get_settings()

    # Assert
    assert json.loads(settings_input.json()) == DEFAULT_EXPECTED_SETTINGS


def test_env_settings_takes_precedence(mock_env):
    # Act
    get_settings.cache_clear()
    settings = get_settings()

    # Assert
    assert settings.sd_user == "env_user"


def test_pydantic_settings_set_correctly_when_json_settings_not_found(mock_env):
    # Act
    get_settings.cache_clear()
    with patch("sdlon.config.load_settings") as mock_load_settings:
        mock_load_settings.side_effect = FileNotFoundError()
        settings = get_settings()

    # Assert
    assert settings.sd_institution_identifier == "institution_id"
    assert settings.sd_user == "env_user"
    assert settings.sd_password.get_secret_value() == "env_pwd"
    assert settings.sd_job_function == "EmploymentName"
    assert settings.sd_monthly_hourly_divide == 80000


@patch("sdlon.config.load_settings")
def test_override_default(mock_load_settings):
    # Arrange
    mock_settings = deepcopy(DEFAULT_MOCK_SETTINGS)
    mock_settings.update({"integrations.SD_Lon.sd_importer.create_associations": False})
    mock_load_settings.return_value = mock_settings

    # Act
    get_settings.cache_clear()
    settings = get_settings()

    # Assert
    assert not settings.sd_importer_create_associations
