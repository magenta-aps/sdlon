import unittest.mock
from collections import OrderedDict
from copy import deepcopy
from datetime import date

import pytest
from freezegun import freeze_time
from more_itertools import one

from .fixtures import get_read_employment_changed_fixture
from sdlon.engagement import _is_external
from sdlon.engagement import create_engagement
from sdlon.engagement import filtered_professions
from sdlon.engagement import get_last_day_of_sd_work
from sdlon.engagement import is_employment_id_and_no_salary_minimum_consistent


class TestIsExternal(unittest.TestCase):
    def test_is_external_is_false_for_number_employment_id(self):
        assert not _is_external("12345")
        assert not _is_external("1")

    def test_is_external_is_true_for_non_number_employment_id(self):
        assert _is_external("ABCDE")


class TestIsEmploymentIdAndNoSalaryMinimumConsistent:
    @pytest.mark.parametrize(
        "no_salary_minimum,employment_id,job_pos_id,expected",
        [
            (None, "12345", 1, True),
            (9000, "External", 10000, True),
            (9000, "External", 8000, False),
            (9000, "12345", 8000, True),
            (9000, "12345", 10000, False),
        ],
    )
    def test_return_values(
        self, no_salary_minimum, employment_id, job_pos_id, expected
    ):
        engagement = one(
            get_read_employment_changed_fixture(
                employment_id=employment_id,
                job_pos_id=job_pos_id,
            )
        )["Employment"]

        assert (
            is_employment_id_and_no_salary_minimum_consistent(
                engagement, no_salary_minimum
            )
            == expected
        )

    @pytest.mark.parametrize(
        "job_pos_id2,expected",
        [
            ("1001", True),
            ("9001", False),
        ],
    )
    def test_job_pos_ids_consistent_but_different(self, job_pos_id2, expected):
        # Arrange
        engagement = one(get_read_employment_changed_fixture())["Employment"]

        profession1 = deepcopy(engagement.get("Profession"))
        profession2 = deepcopy(engagement.get("Profession"))
        profession2["JobPositionIdentifier"] = job_pos_id2
        engagement.update({"Profession": [profession1, profession2]})

        # Assert
        assert (
            is_employment_id_and_no_salary_minimum_consistent(engagement, 9000)
            == expected
        )


class TestCreateEngagement(unittest.TestCase):
    @freeze_time("2000-01-01")
    @unittest.mock.patch("sdlon.engagement.read_employment_at")
    def test_return_none_when_sd_employment_not_found(self, mock_read_employment_at):
        # Arrange
        mock_read_employment_at.return_value = None

        mock_sd_updater = unittest.mock.MagicMock()
        mock_sd_updater.settings = {"some": "settings"}
        mock_sd_updater.current_inst_id = "II"
        mock_sd_updater.dry_run = False

        # Act
        create_engagement(
            mock_sd_updater, "12345", "person_uuid", "0101011234", date(2000, 1, 1)
        )

        # Assert
        mock_read_employment_at.assert_called_once_with(
            effective_date=date(2000, 1, 1),
            settings={"some": "settings"},
            inst_id="II",
            employment_id="12345",
            cpr="0101011234",
            status_passive_indicator=False,
            dry_run=False,
        )
        mock_sd_updater.create_new_engagement.assert_not_called()

    @unittest.mock.patch("sdlon.engagement.read_employment_at")
    def test_use_correct_sd_lookup_date(self, mock_read_employment_at):
        # Arrange
        mock_sd_updater = unittest.mock.MagicMock()
        mock_sd_updater.settings = {"some": "settings"}
        mock_sd_updater.current_inst_id = "II"
        mock_sd_updater.dry_run = False

        # Act
        create_engagement(
            mock_sd_updater, "12345", "person_uuid", "0101011234", date(2000, 1, 1)
        )

        # Assert
        mock_read_employment_at.assert_called_once_with(
            effective_date=date(2000, 1, 1),
            settings={"some": "settings"},
            inst_id="II",
            cpr="0101011234",
            employment_id="12345",
            status_passive_indicator=False,
            dry_run=False,
        )


def test_filter_multiple_professions():
    # Arrange
    sd_employment = OrderedDict(
        {
            "EmploymentIdentifier": "12345",
            "Profession": [
                {"JobPositionIdentifier": "1"},
                {"JobPositionIdentifier": "2"},
                {"JobPositionIdentifier": "3"},
                {"JobPositionIdentifier": "4"},
                {"JobPositionIdentifier": "5"},
            ],
        }
    )

    # Act
    filtered_employment = filtered_professions(sd_employment, ["1", "2"])

    # Assert
    assert filtered_employment == OrderedDict(
        {
            "EmploymentIdentifier": "12345",
            "Profession": [
                {"JobPositionIdentifier": "3"},
                {"JobPositionIdentifier": "4"},
                {"JobPositionIdentifier": "5"},
            ],
        }
    )


def test_filter_single_professions():
    # Arrange
    sd_employment = OrderedDict(
        {
            "EmploymentIdentifier": "12345",
            "Profession": {"JobPositionIdentifier": "3"},
        }
    )

    # Act
    filtered_employment = filtered_professions(sd_employment, ["1", "2"])

    # Assert
    assert filtered_employment == OrderedDict(
        {
            "EmploymentIdentifier": "12345",
            "Profession": [{"JobPositionIdentifier": "3"}],
        }
    )


@pytest.mark.parametrize(
    "emp_status_list, expected",
    [
        ([], None),
        (
            [
                {
                    "ActivationDate": "2000-01-01",
                    "DeactivationDate": "2000-12-31",
                    "EmploymentStatusCode": "1",
                },
                {
                    "ActivationDate": "2001-01-01",
                    "DeactivationDate": "2001-12-31",
                    "EmploymentStatusCode": "3",
                },
                {
                    "ActivationDate": "2002-01-01",
                    "DeactivationDate": "9999-12-31",
                    "EmploymentStatusCode": "8",
                },
            ],
            date(2001, 12, 31),
        ),
        (
            [
                {
                    "ActivationDate": "2002-01-01",
                    "DeactivationDate": "9999-12-31",
                    "EmploymentStatusCode": "8",
                },
            ],
            date(2001, 12, 31),
        ),
        (
            [
                {
                    "ActivationDate": "2002-01-01",
                    "DeactivationDate": "2002-08-29",
                    "EmploymentStatusCode": "9",
                },
                {
                    "ActivationDate": "2002-09-01",
                    "DeactivationDate": "9999-12-31",
                    "EmploymentStatusCode": "8",
                },
            ],
            date(2001, 12, 31),
        ),
    ],
)
def test_get_last_day_of_sd_work(
    emp_status_list: list[dict[str, str]],
    expected: date | None,
) -> None:
    # Act
    last_day_of_work = get_last_day_of_sd_work(emp_status_list)

    # Assert
    assert last_day_of_work == expected
