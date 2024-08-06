from datetime import date

import pytest
from sdclient.responses import Employment
from sdclient.responses import EmploymentDepartment
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
    EmploymentDepartment=EmploymentDepartment(
        ActivationDate=date(2000, 1, 1),
        DeactivationDate=date(2000, 12, 31),
        DepartmentIdentifier="ABCD",
        DepartmentUUIDIdentifier="6220a7b8-db38-46d6-9a36-e1f432db2726",
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

FUTURE_EMPLOYMENT_DEPARTMENTS = [
    EmploymentDepartment(
        ActivationDate=date(2001, 1, 1),
        DeactivationDate=date(2005, 12, 31),
        DepartmentIdentifier="BCDE",
        DepartmentUUIDIdentifier="123457b8-db38-46d6-9a36-e1f432db2726",
    ),
    EmploymentDepartment(
        ActivationDate=date(2006, 1, 1),
        DeactivationDate=date(9999, 12, 31),
        DepartmentIdentifier="ABCD",
        DepartmentUUIDIdentifier="6220a7b8-db38-46d6-9a36-e1f432db2726",
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
        EmploymentIdentifier="12345",
        EmploymentStatus=emp_status_list,
        EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
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
        EmploymentDepartment=[
            EmploymentDepartment(
                ActivationDate=date(2000, 1, 1),
                DeactivationDate=date(2000, 12, 31),
                DepartmentIdentifier="ABCD",
                DepartmentUUIDIdentifier="6220a7b8-db38-46d6-9a36-e1f432db2726",
            )
        ]
        + FUTURE_EMPLOYMENT_DEPARTMENTS,
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
        EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
    )

    # Act + Assert
    with pytest.raises(AssertionError):
        get_emp_status_timeline(CURRENT_EMPLOYMENT_STATUS, employment_changed)


def test_get_emp_status_timeline_status8() -> None:
    # Arrange
    emp_status_list = [
        EmploymentStatus(
            ActivationDate=date(2001, 1, 1),
            DeactivationDate=date(2001, 12, 31),
            EmploymentStatusCode=3,
        ),
        EmploymentStatus(
            ActivationDate=date(2002, 1, 1),
            DeactivationDate=date(2003, 12, 31),
            EmploymentStatusCode=1,
        ),
        EmploymentStatus(
            ActivationDate=date(2004, 1, 1),
            DeactivationDate=date(9999, 12, 31),
            EmploymentStatusCode=8,
        ),
    ]

    employment_changed = EmploymentWithLists(
        EmploymentIdentifier="12345",
        EmploymentStatus=emp_status_list,
        EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
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
        + emp_status_list[:-1],
        EmploymentDepartment=[
            EmploymentDepartment(
                ActivationDate=date(2000, 1, 1),
                DeactivationDate=date(2000, 12, 31),
                DepartmentIdentifier="ABCD",
                DepartmentUUIDIdentifier="6220a7b8-db38-46d6-9a36-e1f432db2726",
            )
        ]
        + FUTURE_EMPLOYMENT_DEPARTMENTS,
    )


def test_get_emp_status_timeline_no_current_employment() -> None:
    # Arrange
    employment_changed = EmploymentWithLists(
        EmploymentIdentifier="12345",
        EmploymentStatus=FUTURE_EMPLOYMENT_STATUSES,
        EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
    )

    # Act
    emp_timeline = get_emp_status_timeline(None, employment_changed)

    # Assert
    assert emp_timeline == EmploymentWithLists(
        EmploymentIdentifier="12345",
        EmploymentStatus=FUTURE_EMPLOYMENT_STATUSES,
        EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
    )


def test_get_sd_employment_map_only_currently_active_emps() -> None:
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
                        EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
                    )
                ],
            )
        ]
    )

    # Act
    emp_map = get_sd_employment_map(
        sd_employments,
        sd_employments_changed,
        only_timelines_for_currently_active_emps=True,
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
            ]
            + FUTURE_EMPLOYMENT_STATUSES,
            EmploymentDepartment=[
                EmploymentDepartment(
                    ActivationDate=date(2000, 1, 1),
                    DeactivationDate=date(2000, 12, 31),
                    DepartmentIdentifier="ABCD",
                    DepartmentUUIDIdentifier="6220a7b8-db38-46d6-9a36-e1f432db2726",
                )
            ]
            + FUTURE_EMPLOYMENT_DEPARTMENTS,
        )
    }


def test_get_sd_employment_map_only_currently_active_emps_empty_future() -> None:
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
        sd_employments,
        GetEmploymentChangedResponse(),  # Nothing in the future
        only_timelines_for_currently_active_emps=True,
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
            EmploymentDepartment=[
                EmploymentDepartment(
                    ActivationDate=date(2000, 1, 1),
                    DeactivationDate=date(2000, 12, 31),
                    DepartmentIdentifier="ABCD",
                    DepartmentUUIDIdentifier="6220a7b8-db38-46d6-9a36-e1f432db2726",
                )
            ],
        )
    }


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
                        EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
                    )
                ]
                + [
                    EmploymentWithLists(
                        EmploymentIdentifier="54321",
                        EmploymentStatus=FUTURE_EMPLOYMENT_STATUSES,
                        EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
                    )
                ],
            )
        ]
    )

    # Act
    emp_map = get_sd_employment_map(
        sd_employments,
        sd_employments_changed,
        only_timelines_for_currently_active_emps=False,
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
            ]
            + FUTURE_EMPLOYMENT_STATUSES,
            EmploymentDepartment=[
                EmploymentDepartment(
                    ActivationDate=date(2000, 1, 1),
                    DeactivationDate=date(2000, 12, 31),
                    DepartmentIdentifier="ABCD",
                    DepartmentUUIDIdentifier="6220a7b8-db38-46d6-9a36-e1f432db2726",
                )
            ]
            + FUTURE_EMPLOYMENT_DEPARTMENTS,
        ),
        ("0101011234", "54321"): EmploymentWithLists(
            EmploymentIdentifier="54321",
            EmploymentStatus=FUTURE_EMPLOYMENT_STATUSES,
            EmploymentDepartment=FUTURE_EMPLOYMENT_DEPARTMENTS,
        ),
    }
