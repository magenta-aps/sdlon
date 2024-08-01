from datetime import date

import pytest
from sdclient.responses import Employment
from sdclient.responses import EmploymentStatus
from sdclient.responses import EmploymentWithLists
from sdclient.responses import GetEmploymentChangedResponse
from sdclient.responses import GetEmploymentResponse
from sdclient.responses import Person
from sdclient.responses import PersonWithLists

from sdlon.scripts.fix_terminated_engagements import get_emp_status_timeline
from sdlon.scripts.fix_terminated_engagements import get_sd_employment_map

CURRENT_EMPLOYMENT_STATUS = Employment(
    EmploymentIdentifier="12345",
    EmploymentDate=date(1999, 1, 1),
    AnniversaryDate=date(1999, 1, 1),
    EmploymentStatus=EmploymentStatus(
        ActivationDate=date(2000, 1, 1),
        DeactivationDate=date(2000, 12, 31),
        EmploymentStatusCode=1,
    ),
)

FUTURE_EMPLOYMENT_STATUSES = [
    EmploymentStatus(
        ActivationDate=date(2001, 1, 1),
        DeactivationDate=date(2001, 12, 31),
        EmploymentStatusCode=3,
    ),
    EmploymentStatus(
        ActivationDate=date(2002, 1, 1),
        DeactivationDate=date(9999, 12, 31),
        EmploymentStatusCode=1,
    ),
]


@pytest.mark.parametrize(
    "emp_status_list",
    [
        FUTURE_EMPLOYMENT_STATUSES,
        [],
    ],
)
def test_get_emp_status_timeline(emp_status_list: list[EmploymentStatus]) -> None:
    # Arrange
    employment_changed = EmploymentWithLists(
        EmploymentIdentifier="12345", EmploymentStatus=emp_status_list
    )

    # Act
    emp_timeline = get_emp_status_timeline(
        CURRENT_EMPLOYMENT_STATUS, employment_changed
    )

    # Assert
    assert emp_timeline == EmploymentWithLists(
        EmploymentIdentifier="12345",
        EmploymentDate=date(1999, 1, 1),
        AnniversaryDate=date(1999, 1, 1),
        EmploymentStatus=[
            EmploymentStatus(
                ActivationDate=date(2000, 1, 1),
                DeactivationDate=date(2000, 12, 31),
                EmploymentStatusCode=1,
            ),
        ]
        + emp_status_list,
    )


def test_get_emp_status_timeline_holes() -> None:
    # Arrange
    employment_changed = EmploymentWithLists(
        EmploymentIdentifier="12345",
        EmploymentStatus=[
            EmploymentStatus(
                # Hole in timeline here
                ActivationDate=date(2001, 1, 2),
                DeactivationDate=date(2001, 12, 31),
                EmploymentStatusCode=3,
            ),
        ],
    )

    # Act + Assert
    with pytest.raises(AssertionError):
        get_emp_status_timeline(CURRENT_EMPLOYMENT_STATUS, employment_changed)


def test_get_sd_employment_map() -> None:
    # Arrange
    sd_employments = GetEmploymentResponse(
        Person=[
            Person(
                PersonCivilRegistrationIdentifier="0101011234",
                Employment=[CURRENT_EMPLOYMENT_STATUS],
            )
        ]
    )
    sd_employments_changed = GetEmploymentChangedResponse(
        Person=[
            PersonWithLists(
                PersonCivilRegistrationIdentifier="0101011234",
                Employment=[
                    EmploymentWithLists(
                        EmploymentIdentifier="12345",
                        EmploymentStatus=FUTURE_EMPLOYMENT_STATUSES,
                    )
                ],
            )
        ]
    )

    # Act
    emp_map = get_sd_employment_map(sd_employments, sd_employments_changed)

    # Assert
    assert emp_map == {
        ("0101011234", "12345"): EmploymentWithLists(
            EmploymentIdentifier="12345",
            EmploymentDate=date(1999, 1, 1),
            AnniversaryDate=date(1999, 1, 1),
            EmploymentStatus=[
                EmploymentStatus(
                    ActivationDate=date(2000, 1, 1),
                    DeactivationDate=date(2000, 12, 31),
                    EmploymentStatusCode=1,
                ),
            ]
            + FUTURE_EMPLOYMENT_STATUSES,
        )
    }


def test_get_sd_employment_map_empty_future() -> None:
    # Arrange
    sd_employments = GetEmploymentResponse(
        Person=[
            Person(
                PersonCivilRegistrationIdentifier="0101011234",
                Employment=[CURRENT_EMPLOYMENT_STATUS],
            )
        ]
    )

    # Act
    emp_map = get_sd_employment_map(
        sd_employments, GetEmploymentChangedResponse()  # Nothing in the future
    )

    # Assert
    assert emp_map == {
        ("0101011234", "12345"): EmploymentWithLists(
            EmploymentIdentifier="12345",
            EmploymentDate=date(1999, 1, 1),
            AnniversaryDate=date(1999, 1, 1),
            EmploymentStatus=[
                EmploymentStatus(
                    ActivationDate=date(2000, 1, 1),
                    DeactivationDate=date(2000, 12, 31),
                    EmploymentStatusCode=1,
                ),
            ],
        )
    }
