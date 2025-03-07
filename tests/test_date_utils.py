from collections import OrderedDict
from datetime import date
from datetime import datetime
from datetime import timedelta
from uuid import uuid4

import pytest
from freezegun import freeze_time
from hypothesis import given
from hypothesis import strategies as st
from more_itertools import pairwise

from sdlon.date_utils import _get_employment_from_date
from sdlon.date_utils import create_eng_lookup_date
from sdlon.date_utils import date_to_datetime
from sdlon.date_utils import datetime_to_sd_date
from sdlon.date_utils import format_date
from sdlon.date_utils import gen_cut_dates
from sdlon.date_utils import gen_date_intervals
from sdlon.date_utils import get_employment_datetimes
from sdlon.date_utils import get_mo_validity
from sdlon.date_utils import get_sd_validity
from sdlon.date_utils import is_midnight
from sdlon.date_utils import SD_INFINITY
from sdlon.date_utils import sd_to_mo_date
from sdlon.date_utils import sd_to_mo_validity
from sdlon.date_utils import to_midnight


@given(st.dates())
def test_date_to_datetime(d: date) -> None:
    dt = date_to_datetime(d)
    assert isinstance(dt, datetime)
    assert d.year == dt.year
    assert d.month == dt.month
    assert d.day == dt.day
    assert 0 == dt.hour
    assert 0 == dt.minute
    assert 0 == dt.second
    assert 0 == dt.microsecond


@st.composite
def from_to_datetime(draw):
    """Generate date-intervals from 1930-->2060, where from < to."""
    from_datetimes = st.datetimes(
        min_value=datetime(1930, 1, 1),
        max_value=datetime(2050, 1, 1),
    )
    min_datetime = draw(from_datetimes)

    to_datetimes = st.datetimes(
        min_value=min_datetime + timedelta(seconds=1),
        max_value=datetime(2060, 1, 1),
    )
    max_datetime = draw(to_datetimes)

    return min_datetime, max_datetime


class TestSdToMoDate:
    def test_assert_string(self):
        with pytest.raises(AssertionError):
            sd_to_mo_date(list())

    def test_assert_date_format_string(self):
        with pytest.raises(AssertionError):
            sd_to_mo_date("invalid string")

    def test_assert_invalid_date(self):
        with pytest.raises(AssertionError):
            sd_to_mo_date("2021-13-01")
        with pytest.raises(AssertionError):
            sd_to_mo_date("2021-12-32")

    def test_conversion(self):
        assert sd_to_mo_date("2000-01-01") == "2000-01-01"
        assert sd_to_mo_date("9999-12-31") is None


@pytest.mark.parametrize(
    "from_,to,expected",
    [
        (
            "2000-01-01",
            "2010-01-01",
            {"from": date(2000, 1, 1), "to": date(2010, 1, 1)},
        ),
        ("2000-01-01", None, {"from": date(2000, 1, 1), "to": date.max}),
    ],
)
def test_get_mo_validity(
    from_: str,
    to: str | None,
    expected: dict[str, str | None],
) -> None:
    # Arrange
    mo_eng = {
        "uuid": uuid4(),
        "validity": {
            "from": from_,
            "to": to,
        },
    }

    # Act
    actual = get_mo_validity(mo_eng)

    # Assert
    assert expected == actual


@pytest.mark.parametrize(
    "activation_date,deactivation_date,expected",
    [
        (
            "2000-01-01",
            "2010-01-01",
            {"from": date(2000, 1, 1), "to": date(2010, 1, 1)},
        ),
        ("2000-01-01", "9999-12-31", {"from": date(2000, 1, 1), "to": date.max}),
    ],
)
def test_get_sd_validity(
    activation_date: str,
    deactivation_date: str,
    expected: dict[str, str | None],
) -> None:
    # Arrange
    engagement_info = {
        "ActivationDate": activation_date,
        "DeactivationDate": deactivation_date,
    }

    # Act
    actual = get_sd_validity(engagement_info)

    # Assert
    assert expected == actual


@pytest.mark.parametrize(
    "activation_date,deactivation_date,expected",
    [
        ("2000-01-01", "2010-01-01", {"from": "2000-01-01", "to": "2010-01-01"}),
        ("2000-01-01", "9999-12-31", {"from": "2000-01-01", "to": None}),
    ],
)
def test_sd_to_mo_validity(
    activation_date: str,
    deactivation_date: str,
    expected: dict[str, str | None],
) -> None:
    # Arrange
    engagement_info = {
        "ActivationDate": activation_date,
        "DeactivationDate": deactivation_date,
    }

    # Act
    actual = sd_to_mo_validity(engagement_info)

    # Assert
    assert expected == actual


@pytest.mark.parametrize(
    "emp_date,emp_dep_date,emp_status_date,prof_date,working_time_date,expected_date",
    [
        (
            datetime(2020, 1, 1),
            datetime(2001, 1, 1),
            datetime(2002, 1, 1),
            datetime(2003, 1, 1),
            datetime(2004, 1, 1),
            datetime(2020, 1, 1),
        ),
        (
            datetime(2001, 1, 1),
            datetime(2021, 1, 1),
            datetime(2002, 1, 1),
            datetime(2003, 1, 1),
            datetime(2004, 1, 1),
            datetime(2021, 1, 1),
        ),
        (
            datetime(2001, 1, 1),
            datetime(2002, 1, 1),
            datetime(2022, 1, 1),
            datetime(2003, 1, 1),
            datetime(2004, 1, 1),
            datetime(2022, 1, 1),
        ),
        (
            datetime(2001, 1, 1),
            datetime(2002, 1, 1),
            datetime(2003, 1, 1),
            datetime(2023, 1, 1),
            datetime(2004, 1, 1),
            datetime(2023, 1, 1),
        ),
        (
            datetime(2020, 1, 1),
            datetime(2002, 1, 1),
            datetime(2003, 1, 1),
            datetime(2004, 1, 1),
            datetime(2024, 1, 1),
            datetime(2024, 1, 1),
        ),
    ],
)
def test_get_from_date_return_max_date(
    emp_date: datetime,
    emp_dep_date: datetime,
    emp_status_date: datetime,
    prof_date: datetime,
    working_time_date: datetime,
    expected_date: datetime,
):
    employment = OrderedDict(
        [
            ("EmploymentDate", format_date(emp_date)),
            (
                "EmploymentDepartment",
                OrderedDict([("ActivationDate", format_date(emp_dep_date))]),
            ),
            (
                "EmploymentStatus",
                OrderedDict([("ActivationDate", format_date(emp_status_date))]),
            ),
            ("Profession", OrderedDict([("ActivationDate", format_date(prof_date))])),
            (
                "WorkingTime",
                OrderedDict([("ActivationDate", format_date(working_time_date))]),
            ),
        ]
    )

    from_date = _get_employment_from_date(employment)

    assert from_date == expected_date


def test_get_from_date_always_return_date():
    assert _get_employment_from_date(OrderedDict()) == datetime.min


@pytest.mark.parametrize(
    "emp_date,act_date,exp_datetime",
    [
        ("1960-01-01", "1970-01-01", datetime(1970, 1, 1)),
        ("1970-01-01", "1960-01-01", datetime(1970, 1, 1)),
        ("1970-01-01", "1970-01-01", datetime(1970, 1, 1)),
    ],
)
def test_get_employment_from_date_when_status_is_leave(
    emp_date,
    act_date,
    exp_datetime,
):
    employment = OrderedDict(
        [
            (
                "EmploymentDate",
                emp_date,
            ),
            (
                "AnniversaryDate",
                "2004-08-15",
            ),
            (
                "EmploymentStatus",
                OrderedDict(
                    [
                        (
                            "EmploymentStatusCode",
                            "3",
                        ),
                        (
                            "ActivationDate",
                            act_date,
                        ),
                        (
                            "DeactivationDate",
                            "9999-12-31",
                        ),
                    ]
                ),
            ),
        ]
    )

    datetime_from, datetime_to = get_employment_datetimes(employment)

    assert datetime_from == exp_datetime


@pytest.mark.parametrize(
    "deactivation_date,exp_datetime",
    [
        ("1960-01-01", datetime(1960, 1, 1)),
        ("1970-01-01", datetime(1970, 1, 1)),
    ],
)
def test_get_employment_to_date_when_status_is_leave(
    deactivation_date,
    exp_datetime,
):
    employment = OrderedDict(
        [
            (
                "EmploymentDate",
                "1970-01-01",
            ),
            (
                "AnniversaryDate",
                "2004-08-15",
            ),
            (
                "EmploymentStatus",
                OrderedDict(
                    [
                        (
                            "EmploymentStatusCode",
                            "3",
                        ),
                        (
                            "ActivationDate",
                            "1975-01-01",
                        ),
                        (
                            "DeactivationDate",
                            deactivation_date,
                        ),
                    ]
                ),
            ),
        ]
    )

    datetime_from, datetime_to = get_employment_datetimes(employment)

    assert datetime_to == exp_datetime


@pytest.mark.parametrize(
    "datetime,expected",
    [
        [datetime(1960, 1, 1, 0, 0, 0, 0), datetime(1960, 1, 1, 0, 0, 0, 0)],
        [datetime(1960, 1, 1, 0, 0, 0, 1), datetime(1960, 1, 1, 0, 0, 0, 0)],
        [datetime(1960, 1, 1, 8, 0, 0, 0), datetime(1960, 1, 1, 0, 0, 0, 0)],
        [datetime(1960, 1, 1, 23, 59, 59, 999), datetime(1960, 1, 1, 0, 0, 0, 0)],
        [datetime(1960, 1, 2, 0, 0, 0, 0), datetime(1960, 1, 2, 0, 0, 0, 0)],
    ],
)
def test_to_midnight_parameterized(datetime, expected):
    assert to_midnight(datetime) == expected


@given(datetime=st.datetimes())
def test_to_midnight(datetime):
    midnight = to_midnight(datetime)
    assert midnight.date() == datetime.date()
    assert midnight.hour == 0
    assert midnight.minute == 0
    assert midnight.second == 0
    assert midnight.microsecond == 0


@pytest.mark.parametrize(
    "datetime,expected",
    [
        [datetime(1960, 1, 1, 0, 0, 0, 0), True],
        [datetime(1960, 1, 1, 0, 0, 0, 1), False],
        [datetime(1960, 1, 1, 8, 0, 0, 0), False],
        [datetime(1960, 1, 1, 23, 59, 59, 999), False],
        [datetime(1960, 1, 2, 0, 0, 0, 0), True],
    ],
)
def test_is_midnight(datetime, expected):
    assert is_midnight(datetime) is expected


@given(datetime=st.datetimes())
def test_to_midnight_is_midnight(datetime):
    assert is_midnight(to_midnight(datetime))


@pytest.mark.parametrize(
    "from_date,to_date,expected",
    [
        (
            datetime(1960, 1, 1, 8, 0, 0),
            datetime(1960, 1, 1, 9, 0, 0),
            [(datetime(1960, 1, 1, 8, 0, 0), datetime(1960, 1, 1, 9, 0, 0))],
        ),
        (
            datetime(1960, 1, 1, 8, 0, 0),
            datetime(1960, 1, 2, 9, 0, 0),
            [
                (datetime(1960, 1, 1, 8, 0, 0), datetime(1960, 1, 2, 0, 0, 0)),
                (datetime(1960, 1, 2, 0, 0, 0), datetime(1960, 1, 2, 9, 0, 0)),
            ],
        ),
        (
            datetime(1960, 1, 1, 8, 0, 0),
            datetime(1960, 1, 3, 9, 0, 0),
            [
                (datetime(1960, 1, 1, 8, 0, 0), datetime(1960, 1, 2, 0, 0, 0)),
                (datetime(1960, 1, 2, 0, 0, 0), datetime(1960, 1, 3, 0, 0, 0)),
                (datetime(1960, 1, 3, 0, 0, 0), datetime(1960, 1, 3, 9, 0, 0)),
            ],
        ),
    ],
)
def test_gen_date_intervals(from_date, to_date, expected):
    dates = gen_date_intervals(from_date, to_date)
    assert list(dates) == expected


def midnights_apart(from_datetime, to_datetime) -> int:
    """Return the number of day changes between from_datetime and to_datetime."""
    return (to_datetime.date() - from_datetime.date()).days


@given(datetimes=from_to_datetime())
def test_date_tuples(datetimes):
    from_datetime, to_datetime = datetimes

    dates = list(gen_cut_dates(from_datetime, to_datetime))
    assert dates[0] == from_datetime
    assert dates[-1] == to_datetime

    num_days_apart = midnights_apart(from_datetime, to_datetime)
    # Remove from_datetime and to_datetime from count, remove 1 if to is midnight
    assert len(dates) - 2 == num_days_apart - (1 if is_midnight(to_datetime) else 0)

    # We always expect intervals to be exactly one day long
    for from_datetime, to_datetime in pairwise(dates[1:-1]):
        num_days_apart = midnights_apart(from_datetime, to_datetime)
        assert type(from_datetime) == datetime
        assert type(to_datetime) == datetime
        assert num_days_apart == 1
        assert (to_datetime - from_datetime).total_seconds() == 86400


@pytest.mark.parametrize(
    "date_time,expected",
    [
        (datetime(2022, 1, 1), "2022-01-01"),
        (datetime(100, 10, 1), "0100-10-01"),
        (datetime(10, 1, 10), "0010-01-10"),
        (datetime(1, 1, 1), "0001-01-01"),
    ],
)
def test_format_date_zero_fill(date_time: datetime, expected: str):
    assert format_date(date_time) == expected


@pytest.mark.parametrize(
    "date_time,expected",
    [
        (datetime(2022, 1, 1), "01.01.2022"),
        (datetime(2100, 10, 1), "01.10.2100"),
        (datetime(1000, 1, 10), "10.01.1000"),
        (datetime(3000, 10, 10), "10.10.3000"),
        (datetime(9999, 12, 31), "31.12.9999"),
    ],
)
def test_datetime_to_sd_date(date_time: datetime, expected: str):
    assert datetime_to_sd_date(date_time) == expected


@freeze_time("2000-01-01")
@pytest.mark.parametrize(
    "activation_date, expected",
    [("2020-01-01", date(2020, 1, 1)), ("1999-01-01", date(2000, 1, 1))],
)
def test_create_eng_lookup_date(activation_date: str, expected: date):
    # Arrange
    eng_components = {
        "professions": [
            {
                "ActivationDate": activation_date,
                "DeactivationDate": "2024-12-31",
            },
            {
                "ActivationDate": "2025-01-01",
                "DeactivationDate": SD_INFINITY,
            },
        ],
        "departments": [
            {
                "ActivationDate": "2026-01-01",
                "DeactivationDate": SD_INFINITY,
            },
        ],
    }

    # Act
    sd_lookup_date = create_eng_lookup_date(eng_components)

    # Assert
    assert sd_lookup_date == expected
