from datetime import date

import pytest
from sdclient.responses import Employment, EmploymentStatus, \
    EmploymentWithLists

from sdlon.scripts.fix_terminated_engagements import get_emp_status_timeline


@pytest.mark.parametrize(
    "emp_status_list",
    [
        [
            EmploymentStatus(
                ActivationDate=date(2001, 1, 1),
                DeactivationDate=date(2001, 12, 31),
                EmploymentStatusCode=3
            ),
            EmploymentStatus(
                ActivationDate=date(2002, 1, 1),
                DeactivationDate=date(9999, 12, 31),
                EmploymentStatusCode=1
            )
        ],
        [],
    ]
)
def test_get_emp_status_timeline(
    emp_status_list: list[EmploymentStatus]
) -> None:
    # Arrange
    employment = Employment(
        EmploymentIdentifier="12345",
        EmploymentDate=date(1999, 1, 1),
        AnniversaryDate=date(1999, 1, 1),
        EmploymentStatus=EmploymentStatus(
            ActivationDate=date(2000, 1, 1),
            DeactivationDate=date(2000, 12, 31),
            EmploymentStatusCode=1
        )
    )
    employment_changed = EmploymentWithLists(
        EmploymentIdentifier="12345",
        EmploymentStatus=emp_status_list
    )

    # Act
    emp_timeline = get_emp_status_timeline(employment, employment_changed)

    # Assert
    assert emp_timeline == EmploymentWithLists(
        EmploymentIdentifier="12345",
        EmploymentDate=date(1999, 1, 1),
        AnniversaryDate=date(1999, 1, 1),
        EmploymentStatus=[
            EmploymentStatus(
                ActivationDate=date(2000, 1, 1),
                DeactivationDate=date(2000, 12, 31),
                EmploymentStatusCode=1
            ),
        ] + emp_status_list
    )
