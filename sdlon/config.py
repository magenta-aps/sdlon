#!/usr/bin/env python3
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
from datetime import date
from functools import lru_cache
from typing import List
from typing import Optional

from pydantic import AnyHttpUrl
from pydantic import BaseSettings
from pydantic import conint
from pydantic import constr
from pydantic import Field
from pydantic import PositiveInt
from pydantic import SecretStr
from pydantic import UUID4
from ra_utils.job_settings import JobSettings

from .log import LogLevel
from .models import JobFunction


class Settings(BaseSettings):  # type: ignore
    """
    Settings common to both the SD importer and SD-changed-at
    """

    mora_base: AnyHttpUrl = Field("http://mo-service:5000")
    mox_base: AnyHttpUrl = Field("http://mo-service:5000/lora")

    sd_employment_field: Optional[str] = Field(default=None, regex="extension_[0-9]+")
    sd_global_from_date: date
    sd_import_too_deep: List[str] = []
    sd_institution_identifier: str | list[str]
    sd_password: SecretStr
    sd_user: str
    sd_job_function: JobFunction
    sd_monthly_hourly_divide: PositiveInt

    # Persist SD payloads in the SD payloads DB
    sd_persist_payloads: bool = True

    # List of SD JobPositionIdentifiers which should not result in creation
    # of engagements
    sd_skip_employment_types: List[str] = []

    # If true, the <TelephoneNumberIdentifier> in <ContactInformation> in
    # <Employment> in the <Person> tag will be used to set a value that can
    # trigger AD-creation of the user
    # (see https://redmine.magenta-aps.dk/issues/56089)
    sd_phone_number_id_for_ad_creation: bool = False
    # SD can only set <TelephoneNumberIdentifier> to an integer value, hence
    # the value 14 is used (letters A=1 and D=4 for "AD")
    sd_phone_number_id_trigger: str = "14"
    sd_phone_number_id_for_ad_string: str = "AD-bruger fra SD"

    cpr_uuid_map_path: str = (
        "/opt/dipex/os2mo-data-import-and-export/settings/cpr_uuid_map.csv"
    )

    log_level: LogLevel = LogLevel.DEBUG

    job_settings: JobSettings = JobSettings()

    municipality_code: conint(ge=100, le=999)  # type: ignore
    municipality_name: str
    sd_importer_create_associations: bool = True
    sd_importer_create_email_addresses: bool = True

    sd_no_salary_minimum_id: Optional[int] = None
    sd_use_ad_integration: bool = True

    sd_fix_departments_root: Optional[UUID4] = None
    sd_overwrite_existing_employment_name = True

    # List of CRPs to either include OR exclude in the run
    sd_cprs: List[constr(regex="^[0-9]{10}$")] = []  # type: ignore # noqa

    # If true, the sd_cprs will be excluded and if false, only the
    # CPRs in sd_cprs will be included in the run
    sd_exclude_cprs_mode: bool = True

    sd_read_forced_uuids: bool = True

    sd_skip_leave_creation_if_no_engagement: bool = False

    # Prefix engagement user key with InstitutionIdentifier
    sd_prefix_eng_user_key_with_inst_id: bool = False

    # Settings for the SD payload database
    pghost: str = "sd-db"
    app_database: str = "sd"
    app_dbuser: str = "sd"
    app_dbpassword: SecretStr


@lru_cache()
def get_settings(*args, **kwargs) -> Settings:
    return Settings(*args, **kwargs)
