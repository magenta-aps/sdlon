import re
from datetime import date
from datetime import datetime
from datetime import timedelta
from operator import itemgetter
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import OrderedDict
from typing import Tuple

from integrations.SD_Lon.sdlon.sd_common import EmploymentStatus as EmploymentStatusEnum
from more_itertools import last
from more_itertools import one
from more_itertools import partition

from .date_utils import parse_datetime
from .sd_common import ensure_list
from .sd_common import read_employment_at
from .skip import skip_job_position_id

INTERNAL_EMPLOYEE_REGEX = re.compile("[0-9]+")


def engagement_components(engagement_info) -> Tuple[str, Dict[str, List[Any]]]:
    employment_id = engagement_info["EmploymentIdentifier"]

    return employment_id, {
        "status_list": ensure_list(engagement_info.get("EmploymentStatus", [])),
        "professions": ensure_list(engagement_info.get("Profession", [])),
        "departments": ensure_list(engagement_info.get("EmploymentDepartment", [])),
        "working_time": ensure_list(engagement_info.get("WorkingTime", [])),
    }


def update_existing_engagement(
    sd_updater, mo_engagement, sd_engagement, person_uuid
) -> None:
    sd_updater.edit_engagement_department(sd_engagement, mo_engagement, person_uuid)
    if sd_updater.settings.sd_overwrite_existing_employment_name:
        sd_updater.edit_engagement_profession(sd_engagement, mo_engagement)
    sd_updater.edit_engagement_type(sd_engagement, mo_engagement)
    sd_updater.edit_engagement_worktime(sd_engagement, mo_engagement)


def create_engagement(sd_updater, employment_id, person_uuid) -> None:
    # Call SD to get SD employment
    sd_employment_payload = read_employment_at(
        datetime.now().date(),
        settings=sd_updater.settings,
        employment_id=employment_id,
        dry_run=sd_updater.dry_run,
    )
    if sd_employment_payload is None:
        return

    assert not isinstance(sd_employment_payload, list)

    cpr = sd_employment_payload["PersonCivilRegistrationIdentifier"]
    sd_employment = sd_employment_payload.get("Employment")
    status = sd_employment.get("EmploymentStatus")  # type: ignore

    # Is it possible that sd_employment or status is None?...
    assert sd_employment
    assert status

    # Not sure what to do if several statuses are returned...
    assert not isinstance(status, list)

    # Call MO to create corresponding engagement in MO
    sd_updater.create_new_engagement(sd_employment, status, cpr, person_uuid)


def _is_external(employment_id: str) -> bool:
    """
    Check if the SD employee is an external employee. This is the
    case (at least in some municipalities...) if the EmploymentIdentifier
    contains letters.

    Args:
         employment_id: the SD EmploymentIdentifier

    Returns:
        True of the employment_id contains letters and False otherwise
    """

    match = INTERNAL_EMPLOYEE_REGEX.match(employment_id)
    return match is None


def is_employment_id_and_no_salary_minimum_consistent(
    engagement: OrderedDict, no_salary_minimum: Optional[int] = None
) -> bool:
    """
    Check that the external SD employees have JobPositionIdentifiers
    consistent with no_salary_limit
    (see https://os2web.atlassian.net/browse/MO-245).

    Args:
        engagement: the SD employment
        no_salary_minimum: the minimum allowed JobPositionIdentifier
          for external SD employees.

    Returns:
        True if the provided values are consistent and False otherwise.
    """

    if no_salary_minimum is None:
        return True

    employment_id, eng_components = engagement_components(engagement)
    professions = eng_components["professions"]
    if not professions:
        return True

    job_pos_ids_strings = map(itemgetter("JobPositionIdentifier"), professions)
    job_pos_ids = map(int, job_pos_ids_strings)

    def is_consistent(job_pos_id: int) -> bool:
        if _is_external(employment_id):
            return job_pos_id >= no_salary_minimum  # type: ignore
        return job_pos_id < no_salary_minimum  # type: ignore

    consistent = map(is_consistent, job_pos_ids)

    return all(consistent)


def filtered_professions(
    sd_employment: OrderedDict, job_pos_ids_to_skip: list[str]
) -> OrderedDict:
    """
    Remove any professions with a JobPositionIdentifier in the
    job_pos_ids_to_skip list (provided via the setting sd_skip_employment_types
    or the environment variable SD_SKIP_EMPLOYMENT_TYPES).

    Args:
        sd_employment: the SD employment
        job_pos_ids_to_skip: list of JobPositionIdentifiers to remove from
          "Professions" in the SD employment payload

    Returns:
        The SD employment payload where the professions to be skipped
        are removed.
    """

    professions = ensure_list(sd_employment.get("Profession", []))
    sd_employment["Profession"] = [
        profession
        for profession in professions
        if not skip_job_position_id(profession, job_pos_ids_to_skip)
    ]

    return sd_employment


def has_active_status(emp_status: dict[str, str]) -> bool:
    return emp_status["EmploymentStatusCode"] in (
        status.value for status in EmploymentStatusEnum.employeed()
    )


def get_last_day_of_sd_work(emp_status_list: list[dict[str, str]]) -> date | None:
    inactive_emp_statuses_gen, active_emp_statuses_gen = partition(
        has_active_status, emp_status_list
    )
    active_emp_statuses = list(active_emp_statuses_gen)
    inactive_emp_statuses = list(inactive_emp_statuses_gen)

    if active_emp_statuses:
        # This will not handle the (possible but unlikely) situation where active
        # (status 0, 1 and 3) and passive (status 8, 9 and S) SD statuses are mixed,
        # e.g.
        # |------ 1 ------|--- 8 ---|---- 1 ----|----- 8 -----
        return parse_datetime(last(active_emp_statuses)["DeactivationDate"]).date()

    if inactive_emp_statuses:
        # First day of non-work (e.g. retirement (status 8))
        activation_date = parse_datetime(
            one(inactive_emp_statuses)["ActivationDate"]
        ).date()
        # Last day of work
        return activation_date - timedelta(days=1)

    return None
