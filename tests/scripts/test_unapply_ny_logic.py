from datetime import date
from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from sdlon.mo import MO
from sdlon.scripts.unapply_ny_logic import get_mo_eng_validity_map
from sdlon.scripts.unapply_ny_logic import get_update_interval
from sdlon.scripts.unapply_ny_logic import Validity


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
            },
            Validity(
                from_=datetime.fromisoformat("2024-07-26T00:00:00+02:00"),
                to=datetime.fromisoformat("2024-09-20T00:00:00+02:00"),
            ): {
                "eng_uuid": "009269ec-a78e-4292-a6fa-27fc54af4628",
                "ou_uuid": "8909eec1-485b-42fc-9a0f-87e0d02591bf",
            },
        }
    }
