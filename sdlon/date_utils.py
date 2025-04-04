import re
from datetime import date
from datetime import datetime
from datetime import timedelta
from itertools import chain
from itertools import takewhile
from typing import Any
from typing import Iterator
from typing import Optional
from typing import OrderedDict
from typing import Tuple
from typing import Union

from more_itertools import first
from more_itertools import pairwise
from more_itertools import tabulate
from structlog.stdlib import get_logger

from .sd_common import EmploymentStatus

# TODO: move constants elsewhere
# TODO: set back to "infinity" when MO can handle this
# MO_INFINITY: str = "infinity"

MO_INFINITY = None
SD_INFINITY: str = "9999-12-31"
DATE_REGEX_STR = "[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[0-1])"

logger = get_logger()


def date_to_datetime(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def format_date(d: datetime | date) -> str:
    return d.strftime("%Y-%m-%d").zfill(10)


def parse_datetime(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def datetime_to_sd_date(date_time: Union[datetime, date]) -> str:
    return date_time.strftime("%d.%m.%Y")


def _get_employment_from_date(employment: OrderedDict) -> datetime:
    """
    Get the latest date of all the dates in the payload from the SD
    GetEmployment endpoint (see https://redmine.magenta-aps.dk/issues/51898)

    Args:
        employment: the SD employment

    Returns: the maximum of all the date in the SD payload

    """
    MIN_DATE = format_date(datetime.min)

    employment_date = employment.get("EmploymentDate", MIN_DATE)
    employment_department_date = employment.get("EmploymentDepartment", dict()).get(
        "ActivationDate", MIN_DATE
    )
    employment_status_date = employment.get("EmploymentStatus", dict()).get(
        "ActivationDate", MIN_DATE
    )
    profession_date = employment.get("Profession", dict()).get(
        "ActivationDate", MIN_DATE
    )
    working_time_date = employment.get("WorkingTime", dict()).get(
        "ActivationDate", MIN_DATE
    )

    return max(
        parse_datetime(employment_date),
        parse_datetime(employment_department_date),
        parse_datetime(employment_status_date),
        parse_datetime(profession_date),
        parse_datetime(working_time_date),
    )


def get_employment_datetimes(employment: OrderedDict) -> Tuple[datetime, datetime]:
    """
    Get the "from" and "to" date from the SD employment

    Args:
        employment: The SD employment

    Returns:
        Tuple containing the "from" and "to" dates.
    """

    status = EmploymentStatus(employment["EmploymentStatus"]["EmploymentStatusCode"])

    if status in EmploymentStatus.let_go():
        datetime_from = parse_datetime(employment["EmploymentDate"])
        termination_date = str(
            sd_to_mo_date(employment["EmploymentStatus"]["ActivationDate"])
        )
        datetime_to = parse_datetime(termination_date)
        return datetime_from, datetime_to

    datetime_from = _get_employment_from_date(employment)
    datetime_to = parse_datetime(employment["EmploymentStatus"]["DeactivationDate"])

    return datetime_from, datetime_to


# TODO: Create "MoValidity" and "SdValidity" classes based on the RA Models
#  "Validity" class and use these as input to the function below


def sd_to_mo_date(sd_date: str) -> Optional[str]:
    """
    Convert SD date to MO date.

    Args:
        sd_date: SD date formatted as "YYYY-MM-DD"

    Returns:
        MO termination date formatted as "YYYY-MM-DD"
    """

    assert isinstance(sd_date, str)
    assert re.compile(DATE_REGEX_STR).match(sd_date)

    if sd_date == SD_INFINITY:
        return MO_INFINITY

    return sd_date


def get_mo_validity(mo_eng: dict[str, Any]) -> dict[str, date]:
    """
    Get the MO engagement validity from an engagement dictionary.
    "None" is converted to date(9999, 12, 31) to ease comparisons
    with SD dates.

    Args:
        mo_eng: the MO engagement dict, e.g.
        {
            "uuid": "9bef2405-9527-4e28-85cf-de4139782987",
            "validity": {
                "from": "2000-01-01",
                "to": None
            }
        }

    Returns:
        The MO validity, e.g.
        {
            "from": date(2000, 1, 1),
            "to": date(9999, 12, 31)
        }
        for the example above.
    """
    validity = mo_eng["validity"]
    from_ = validity["from"]
    to = validity["to"]

    return {
        "from": parse_datetime(from_).date(),
        "to": parse_datetime(to).date() if to is not None else date.max,
    }


def get_sd_validity(engagement_info_obj: dict[str, Any]) -> dict[str, date]:
    """
    Convert the SD validity (ActivationDate and DeactivationDate) to a MO
    validity.

    Args:
        engagement_info_obj: the "engagement_info" object, e.g. in the case of a
                             department:
        {
            "ActivationDate": "1999-01-01",
            "DeactivationDate": "9999-12-31",
            "DepartmentIdentifier": "dep1",
            "DepartmentLevelIdentifier": "NY1-niveau",
            "DepartmentName": "Department 1",
            "DepartmentUUIDIdentifier": "eb25d197-d278-41ac-abc1-cc7802093130",
            "PostalAddress": {
                "StandardAddressIdentifier": "Paradisæblevej 13",
                "PostalCode": 1000,
                "DistrictName": "Andeby",
            },
            "ProductionUnitIdentifier": 1234567890,
        }

    Returns:
        The SD validity, e.g.
        {
            "from": "1999-01-01",
            "to": "9999-12-31"
        }
        for the example above.
    """
    return {
        "from": parse_datetime(engagement_info_obj["ActivationDate"]).date(),
        "to": parse_datetime(engagement_info_obj["DeactivationDate"]).date(),
    }


def sd_to_mo_validity(engagement_info: dict[str, Any]) -> dict[str, str | None]:
    """
    Convert the SD validity (ActivationDate and DeactivationDate) to a MO
    validity.

    Args:
        engagement_info: the "engagement_info" object, e.g.
        {
            "ActivationDate": "1999-01-01",
            "DeactivationDate": "9999-12-31",
            "DepartmentIdentifier": "dep1",
            "DepartmentLevelIdentifier": "NY1-niveau",
            "DepartmentName": "Department 1",
            "DepartmentUUIDIdentifier": "eb25d197-d278-41ac-abc1-cc7802093130",
            "PostalAddress": {
                "StandardAddressIdentifier": "Paradisæblevej 13",
                "PostalCode": 1000,
                "DistrictName": "Andeby",
            },
            "ProductionUnitIdentifier": 1234567890,
        }

    Returns:
        The MO validity, e.g.
        {
            "from": "1999-01-01",
            "to": None
        }
        for the example above.
    """

    return {
        "from": sd_to_mo_date(engagement_info["ActivationDate"]),
        "to": sd_to_mo_date(engagement_info["DeactivationDate"]),
    }


def to_midnight(dt: datetime) -> datetime:
    """Get previous midnight from datetime."""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def is_midnight(dt: datetime) -> bool:
    """Check if datetime is at midnight."""
    return dt == to_midnight(dt)


def gen_cut_dates(from_datetime: datetime, to_datetime: datetime) -> Iterator[datetime]:
    """Get iterator of cut-dates between from_datetime and to_datetime.

    Args:
        from_datetime: the start date
        to_datetime: the end date

    Yields:
        The from_datetime, then all intermediate midnight datetimes and the to_datetime.
    """
    assert from_datetime < to_datetime

    # Tabulate to infinite iterator of midnights starting after from_datetime
    def midnight_at_offset(offset: int) -> datetime:
        return to_midnight(from_datetime) + timedelta(days=offset)

    midnights = takewhile(
        lambda midnight: midnight < to_datetime, tabulate(midnight_at_offset, start=1)
    )
    return chain([from_datetime], midnights, [to_datetime])


def gen_date_intervals(
    from_datetime: datetime, to_datetime: datetime
) -> Iterator[Tuple[datetime, datetime]]:
    """
    Get iterator capable of generating a sequence of datetime pairs
    incrementing one day at a time. The latter date in a pair is
    advanced by exactly one day compared to the former date in the pair.

    Args:
        from_datetime: the start date
        to_datetime: the end date

    Yields:
        The next date pair in the sequence of pairs
    """
    return pairwise(gen_cut_dates(from_datetime, to_datetime))


def create_eng_lookup_date(
    engagement_components: dict[str, list[dict[str, Any]]]
) -> date:
    """
    This is only "best effort" to obtain the relevant SD lookup date for creating
    a new (missing) engagement during an "edit_engagement" operation. There is no
    guarantee that we will retrieve the full picture in this way. The situation could
    be more complex, but it would be quite difficult to obtain the full picture at
    the point in the code where this function is used.

    Args:
        engagement_components: The SD payload engagement components.

    Returns:
        Best effort SD lookup date for getting the SD employment data.
    """
    min_comp_date = min(
        parse_datetime(
            first(
                component,
                {
                    "ActivationDate": SD_INFINITY,
                    "DeactivationDate": SD_INFINITY,
                },
            )["ActivationDate"]
        )
        for component in engagement_components.values()
    )
    return max(min_comp_date, datetime.now()).date()
