from datetime import date
from datetime import datetime

import pytest

from sdlon.scripts.unapply_ny_logic import get_update_interval
from sdlon.scripts.unapply_ny_logic import Validity


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
