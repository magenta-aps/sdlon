from datetime import datetime
from zoneinfo import ZoneInfo

from sdlon.scripts.fix_departments import get_mo_eng_holes
from sdlon.scripts.unapply_ny_logic import Validity


def test_get_mo_eng_holes():
    # Arrange
    validities = [
        Validity(
            datetime.fromisoformat("2025-01-21T00:00:00+01:00"),
            datetime.fromisoformat("2025-01-27T00:00:00+01:00"),
        ),
        Validity(
            datetime.fromisoformat("2025-01-28T00:00:00+01:00"),
            datetime.fromisoformat("2025-02-20T00:00:00+01:00"),
        ),
        Validity(datetime.fromisoformat("2030-02-21T00:00:00+01:00"), datetime.max),
    ]

    # Act
    holes = get_mo_eng_holes(validities)

    # Assert
    assert holes == [
        Validity(
            from_=datetime(2025, 2, 21, 0, 0, 0, tzinfo=ZoneInfo("Europe/Copenhagen")),
            to=datetime(2030, 2, 20, 0, 0, 0, tzinfo=ZoneInfo("Europe/Copenhagen")),
        )
    ]
