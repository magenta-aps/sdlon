from datetime import date
from unittest.mock import patch, MagicMock, call

from sdclient.responses import GetEmploymentResponse, Person, Employment, EmploymentStatus

from sdlon.scripts.fix_closed_leave_engagements import get_final_sd_employment_end_date


@patch("sdlon.scripts.fix_closed_leave_engagements.get_sd_employments")
def test_get_final_sd_employment_end_date_one_active_status(
        mock_get_sd_employments: MagicMock
):
    # Arrange
    mock_get_sd_employments.side_effect = [
        GetEmploymentResponse(
            Person=[
                Person(
                    PersonCivilRegistrationIdentifier="1111111234",
                    Employment=[
                        Employment(
                            EmploymentIdentifier="12345",
                            EmploymentDate=date(2000, 1, 1),
                            AnniversaryDate=date(2000, 1, 1),
                            EmploymentStatus=EmploymentStatus(
                                ActivationDate=date(2010, 1, 1),
                                DeactivationDate=date(2029, 12, 31),
                                EmploymentStatusCode="1",
                            )
                        )
                    ]
                )
            ]
        ),
        GetEmploymentResponse(
            Person=[
                Person(
                    PersonCivilRegistrationIdentifier="1111111234",
                    Employment=[
                        Employment(
                            EmploymentIdentifier="12345",
                            EmploymentDate=date(2000, 1, 1),
                            AnniversaryDate=date(2000, 1, 1),
                            EmploymentStatus=EmploymentStatus(
                                ActivationDate=date(2030, 1, 1),
                                DeactivationDate=date(9999, 12, 31),
                                EmploymentStatusCode="8",
                            )
                        )]
                )
            ]
        )
    ]

    # Act
    end_date = get_final_sd_employment_end_date(
        "username",
        "password",
        "XY",
        "1111111234",
        "12345",
        date(2020, 1, 1),
    )

    # Assert
    assert end_date == date(2029, 12, 31)
    assert mock_get_sd_employments.call_args_list == [
        call(
            "username",
            "password",
            "XY",
            "1111111234",
            "12345",
            date(2020, 1, 1),
        ),
        call(
            "username",
            "password",
            "XY",
            "1111111234",
            "12345",
            date(2030, 1, 1),
        ),
    ]


@patch("sdlon.scripts.fix_closed_leave_engagements.get_sd_employments")
def test_get_final_sd_employment_end_date_one_active_status_to_infinity(
        mock_get_sd_employments: MagicMock
):
    # Arrange
    mock_get_sd_employments.side_effect = [
        GetEmploymentResponse(
            Person=[
                Person(
                    PersonCivilRegistrationIdentifier="1111111234",
                    Employment=[
                        Employment(
                            EmploymentIdentifier="12345",
                            EmploymentDate=date(2000, 1, 1),
                            AnniversaryDate=date(2000, 1, 1),
                            EmploymentStatus=EmploymentStatus(
                                ActivationDate=date(2010, 1, 1),
                                DeactivationDate=date(9999, 12, 31),
                                EmploymentStatusCode="1",
                            )
                        )
                    ]
                )
            ]
        )
    ]

    # Act
    end_date = get_final_sd_employment_end_date(
        "username",
        "password",
        "XY",
        "1111111234",
        "12345",
        date(2020, 1, 1),
    )

    # Assert
    assert end_date == date(9999, 12, 31)
    assert mock_get_sd_employments.call_args_list == [
        call(
            "username",
            "password",
            "XY",
            "1111111234",
            "12345",
            date(2020, 1, 1),
        )
    ]


@patch("sdlon.scripts.fix_closed_leave_engagements.get_sd_employments")
def test_get_final_sd_employment_end_date_two_active_statuses(mock_get_sd_employments):
    # Arrange
    mock_get_sd_employments.side_effect = [
        GetEmploymentResponse(
            Person=[
                Person(
                    PersonCivilRegistrationIdentifier="1111111234",
                    Employment=[
                        Employment(
                            EmploymentIdentifier="12345",
                            EmploymentDate=date(2000, 1, 1),
                            AnniversaryDate=date(2000, 1, 1),
                            EmploymentStatus=EmploymentStatus(
                                ActivationDate=date(2010, 1, 1),
                                DeactivationDate=date(2029, 12, 31),
                                EmploymentStatusCode="3",
                            )
                        )
                    ]
                )
            ]
        ),
        GetEmploymentResponse(
            Person=[
                Person(
                    PersonCivilRegistrationIdentifier="1111111234",
                    Employment=[
                        Employment(
                            EmploymentIdentifier="12345",
                            EmploymentDate=date(2000, 1, 1),
                            AnniversaryDate=date(2000, 1, 1),
                            EmploymentStatus=EmploymentStatus(
                                ActivationDate=date(2030, 1, 1),
                                DeactivationDate=date(2039, 12, 31),
                                EmploymentStatusCode="1",
                            )
                        )]
                )
            ]
        ),
        GetEmploymentResponse(
            Person=[
                Person(
                    PersonCivilRegistrationIdentifier="1111111234",
                    Employment=[
                        Employment(
                            EmploymentIdentifier="12345",
                            EmploymentDate=date(2000, 1, 1),
                            AnniversaryDate=date(2000, 1, 1),
                            EmploymentStatus=EmploymentStatus(
                                ActivationDate=date(2040, 1, 1),
                                DeactivationDate=date(9999, 12, 31),
                                EmploymentStatusCode="9",
                            )
                        )
                    ]
                )
            ]
        )
    ]

    # Act
    end_date = get_final_sd_employment_end_date(
        "username",
        "password",
        "XY",
        "1111111234",
        "12345",
        date(2020, 1, 1),
    )

    # Assert
    assert end_date == date(2039, 12, 31)
    assert mock_get_sd_employments.call_args_list == [
        call(
            "username",
            "password",
            "XY",
            "1111111234",
            "12345",
            date(2020, 1, 1),
        ),
        call(
            "username",
            "password",
            "XY",
            "1111111234",
            "12345",
            date(2030, 1, 1),
        ),
        call(
            "username",
            "password",
            "XY",
            "1111111234",
            "12345",
            date(2040, 1, 1),
        ),
    ]


@patch("sdlon.scripts.fix_closed_leave_engagements.get_sd_employments")
def test_get_final_sd_employment_end_date_inactive_status(mock_get_sd_employments):
    # Arrange
    mock_get_sd_employments.return_value = GetEmploymentResponse(
        Person=[
            Person(
                PersonCivilRegistrationIdentifier="1111111234",
                Employment=[
                    Employment(
                        EmploymentIdentifier="12345",
                        EmploymentDate=date(2000, 1, 1),
                        AnniversaryDate=date(2000, 1, 1),
                        EmploymentStatus=EmploymentStatus(
                            ActivationDate=date(2010, 1, 1),
                            DeactivationDate=date(2029, 12, 31),
                            EmploymentStatusCode="8",
                        )
                    )
                ]
            )
        ]
    )

    # Act
    end_date = get_final_sd_employment_end_date(
        "username",
        "password",
        "XY",
        "1111111234",
        "12345",
        date(2020, 1, 1),
    )

    # Assert
    assert end_date is None
    assert mock_get_sd_employments.call_args_list == [
        call(
            "username",
            "password",
            "XY",
            "1111111234",
            "12345",
            date(2020, 1, 1),
        )
    ]
