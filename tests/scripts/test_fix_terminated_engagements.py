from datetime import date

from sdclient.responses import Employment, EmploymentStatus, \
    EmploymentWithLists

from sdlon.scripts.fix_terminated_engagements import get_emp_status_timeline


def test_get_emp_status_timeline() -> None:
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
        EmploymentStatus=[
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
        ]
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
        ]
    )
