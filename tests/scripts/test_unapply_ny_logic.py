from datetime import date
from datetime import datetime
from datetime import timedelta
from unittest.mock import call
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sdclient.responses import Employment
from sdclient.responses import EmploymentDepartment
from sdclient.responses import EmploymentStatus
from sdclient.responses import EmploymentWithLists
from sdclient.responses import GetEmploymentResponse
from sdclient.responses import Person

from sdlon.mo import MO
from sdlon.scripts.unapply_ny_logic import get_mo_eng_validity_map
from sdlon.scripts.unapply_ny_logic import get_update_interval
from sdlon.scripts.unapply_ny_logic import update_engs_ou
from sdlon.scripts.unapply_ny_logic import Validity
from sdlon.sd import SD

MO_GET_ENGAGEMENT_RESPONSE = [
    {
        "validities": [
            {
                "person": [
                    {
                        "cpr_number": "2112572360",
                        "uuid": "fe0ad6c2-9668-4279-848d-029c2465a15b",
                    }
                ],
                "org_unit": [
                    {
                        "uuid": "1caba8d9-6b9f-506b-b845-9a8c4f5b8a03",
                        "user_key": "Jordrup børnehus",
                        "name": "Jordrup børnehus",
                        "managers": [
                            {
                                "employee": [
                                    {
                                        "uuid": "539391a4-a12b-4f0b-8b79-"
                                        "440118e1522e",
                                        "name": "Chr Christensen",
                                    }
                                ]
                            }
                        ],
                    }
                ],
                "validity": {
                    "from": "1998-12-07T00:00:00+01:00",
                    "to": "2021-11-06T00:00:00+01:00",
                },
                "user_key": "12345",
            },
            {
                "person": [
                    {
                        "cpr_number": "2112572360",
                        "uuid": "fe0ad6c2-9668-4279-848d-029c2465a15b",
                    }
                ],
                "org_unit": [
                    {
                        "uuid": "8909eec1-485b-42fc-9a0f-87e0d02591bf",
                        "user_key": "Jordrup børnehus",
                        "name": "Jordrup børnehus",
                        "managers": [
                            {
                                "employee": [
                                    {
                                        "uuid": "539391a4-a12b-4f0b-8b79-"
                                        "440118e1522e",
                                        "name": "Chr Christensen",
                                    }
                                ]
                            }
                        ],
                    }
                ],
                "validity": {
                    "from": "2024-07-26T00:00:00+02:00",
                    "to": "2024-09-20T00:00:00+02:00",
                },
                "user_key": "12345",
            },
        ],
        "uuid": "009269ec-a78e-4292-a6fa-27fc54af4628",
    }
]


@pytest.mark.parametrize(
    "mo_validity, sd_activation_date, sd_deactivation_date, expected_from, expected_to",
    [
        # MO --------==============================>
        # SD ------+------------------------------->
        # Returns:
        #            +----------------------------->
        (
            Validity(datetime(2000, 1, 1), datetime.max),
            date(1999, 1, 1),
            date.max,
            datetime(2000, 1, 1, 0, 0, 0),
            None,
        ),
        # MO --------==============================>
        # SD --------+----------------------------->
        # Returns:
        #            +----------------------------->
        (
            Validity(datetime(2000, 1, 1), datetime.max),
            date(2000, 1, 1),
            date.max,
            datetime(2000, 1, 1, 0, 0, 0),
            None,
        ),
        # MO --------==============================>
        # SD ----+------------+-------------------->
        # Returns:
        #            +--------+
        (
            Validity(datetime(2000, 1, 1), datetime.max),
            date(1999, 1, 1),
            date(2010, 1, 1),
            datetime(2000, 1, 1, 0, 0, 0),
            datetime(2010, 1, 1, 0, 0, 0),
        ),
        # MO --------==================------------>
        # SD ----+--------------------------------->
        # Returns:
        #            +----------------+
        (
            Validity(
                datetime(2000, 1, 1),
                datetime(2010, 1, 1),
            ),
            date(1999, 1, 1),
            date.max,
            datetime(2000, 1, 1, 0, 0, 0),
            datetime(2010, 1, 1, 0, 0, 0),
        ),
        # MO --------==================------------>
        # SD ----+-----------+--------------------->
        # Returns:
        #            +-------+
        (
            Validity(
                datetime(2000, 1, 1),
                datetime(2010, 1, 1),
            ),
            date(1999, 1, 1),
            date(2005, 1, 1),
            datetime(2000, 1, 1, 0, 0, 0),
            datetime(2005, 1, 1, 0, 0, 0),
        ),
    ],
)
def test_get_update_interval(
    mo_validity: Validity,
    sd_activation_date: date,
    sd_deactivation_date: date,
    expected_from: datetime,
    expected_to: datetime | None,
):
    # Act
    update_from, update_to = get_update_interval(
        mo_validity, sd_activation_date, sd_deactivation_date
    )

    # Assert
    assert expected_from == update_from
    assert expected_to == update_to


def test_get_mo_eng_validity_map():
    # Arrange
    mock_mo = MagicMock(spec=MO)
    mock_mo.get_engagements.return_value = MO_GET_ENGAGEMENT_RESPONSE
    from_date = datetime.now()
    to_date = from_date + timedelta(days=365)

    # Act
    map_ = get_mo_eng_validity_map(mock_mo, from_date, to_date, include_org_unit=True)

    # Assert
    mock_mo.get_engagements.assert_called_once_with(
        from_date, to_date, include_org_unit=True
    )

    assert map_ == {
        ("2112572360", "12345"): {
            Validity(
                from_=datetime.fromisoformat("1998-12-07T00:00:00+01:00"),
                to=datetime.fromisoformat("2021-11-06T00:00:00+01:00"),
            ): {
                "eng_uuid": "009269ec-a78e-4292-a6fa-27fc54af4628",
                "ou_uuid": "1caba8d9-6b9f-506b-b845-9a8c4f5b8a03",
                "person_uuid": "fe0ad6c2-9668-4279-848d-029c2465a15b",
                "cpr": "2112572360",
                "emp_id": "12345",
            },
            Validity(
                from_=datetime.fromisoformat("2024-07-26T00:00:00+02:00"),
                to=datetime.fromisoformat("2024-09-20T00:00:00+02:00"),
            ): {
                "eng_uuid": "009269ec-a78e-4292-a6fa-27fc54af4628",
                "ou_uuid": "8909eec1-485b-42fc-9a0f-87e0d02591bf",
                "person_uuid": "fe0ad6c2-9668-4279-848d-029c2465a15b",
                "cpr": "2112572360",
                "emp_id": "12345",
            },
        }
    }


def test_update_engs_ou():
    # Arrange
    sd_map = {
        ("0101011234", "12345"): EmploymentWithLists(
            EmploymentIdentifier="12345",
            EmploymentDate=date(2024, 3, 1),
            AnniversaryDate=date(2024, 3, 1),
            EmploymentStatus=[
                EmploymentStatus(
                    ActivationDate=date(2024, 3, 1),
                    DeactivationDate=date(9999, 12, 31),
                    EmploymentStatusCode="1",
                )
            ],
            EmploymentDepartment=[
                EmploymentDepartment(
                    ActivationDate=date(2024, 7, 1),
                    DeactivationDate=date(9999, 12, 31),
                    DepartmentIdentifier="EFGH",
                    DepartmentUUIDIdentifier=UUID(
                        "12f4213d-7915-4a44-b9a4-537dcd322e8a"
                    ),
                )
            ],
        )
    }

    mo_map = {
        ("0101011234", "12345"): {
            Validity(from_=datetime(2024, 3, 1), to=datetime(2024, 8, 31),): {
                "eng_uuid": "b1423aa5-5a3d-47bc-9e6e-971543132b22",
                "ou_uuid": "a2816b16-5df8-42ff-99a5-b2fca14ae172",
                "person_uuid": "20426da0-8066-4903-88c9-908347df697e",
                "cpr": "0101011234",
                "emp_id": "12345",
            },
            Validity(from_=datetime(2024, 9, 1), to=datetime(2025, 6, 30)): {
                "eng_uuid": "b1423aa5-5a3d-47bc-9e6e-971543132b22",
                "ou_uuid": "38c6c343-806d-45e9-bff9-e7f29136c613",
                "person_uuid": "20426da0-8066-4903-88c9-908347df697e",
                "cpr": "0101011234",
                "emp_id": "12345",
            },
            Validity(from_=datetime(2025, 7, 1), to=datetime.max): {
                "eng_uuid": "b1423aa5-5a3d-47bc-9e6e-971543132b22",
                "ou_uuid": "915d314d-fec7-40b8-b9fb-fe96630664e2",
                "person_uuid": "20426da0-8066-4903-88c9-908347df697e",
                "cpr": "0101011234",
                "emp_id": "12345",
            },
        }
    }

    mock_sd = MagicMock(spec=SD)
    mock_sd.get_sd_employments.return_value = GetEmploymentResponse(
        Person=[
            Person(
                PersonCivilRegistrationIdentifier="0101011234",
                Employment=[
                    Employment(
                        EmploymentIdentifier="12345",
                        EmploymentDate=date(2000, 1, 1),
                        AnniversaryDate=date(2000, 1, 1),
                        EmploymentStatus=EmploymentStatus(
                            ActivationDate=date(2024, 3, 1),
                            DeactivationDate=date(9999, 12, 31),
                            EmploymentStatusCode="1",
                        ),
                        EmploymentDepartment=EmploymentDepartment(
                            ActivationDate=date(2024, 3, 1),
                            DeactivationDate=date(2024, 6, 30),
                            DepartmentIdentifier="ABCD",
                            DepartmentUUIDIdentifier=UUID(
                                "a9a96a34-b569-48f8-9ef7-8031b53a3bdf"
                            ),
                        ),
                    )
                ],
            )
        ]
    )

    mock_mo = MagicMock(spec=MO)

    # Act
    update_engs_ou(
        sd=mock_sd,
        mo=mock_mo,
        sd_map=sd_map,
        mo_map=mo_map,
        cpr=None,
        dry_run=False,
    )

    # Assert
    calls = mock_mo.update_engagement.call_args_list
    assert len(calls) == 4

    assert calls[0] == call(
        eng_uuid=UUID("b1423aa5-5a3d-47bc-9e6e-971543132b22"),
        from_date=datetime(2024, 3, 1),
        to_date=datetime(2024, 6, 30),
        org_unit=UUID("a9a96a34-b569-48f8-9ef7-8031b53a3bdf"),
    )

    assert calls[1] == call(
        eng_uuid=UUID("b1423aa5-5a3d-47bc-9e6e-971543132b22"),
        from_date=datetime(2024, 7, 1),
        to_date=datetime(2024, 8, 31),
        org_unit=UUID("12f4213d-7915-4a44-b9a4-537dcd322e8a"),
    )

    assert calls[2] == call(
        eng_uuid=UUID("b1423aa5-5a3d-47bc-9e6e-971543132b22"),
        from_date=datetime(2024, 9, 1),
        to_date=datetime(2025, 6, 30),
        org_unit=UUID("12f4213d-7915-4a44-b9a4-537dcd322e8a"),
    )

    assert calls[3] == call(
        eng_uuid=UUID("b1423aa5-5a3d-47bc-9e6e-971543132b22"),
        from_date=datetime(2025, 7, 1),
        to_date=None,
        org_unit=UUID("12f4213d-7915-4a44-b9a4-537dcd322e8a"),
    )
