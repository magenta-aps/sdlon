from collections import OrderedDict
from copy import deepcopy

import pytest
from parameterized import parameterized

from .test_config import DEFAULT_CHANGED_AT_SETTINGS
from sdlon.config import Settings
from sdlon.skip import cpr_env_filter
from sdlon.skip import skip_job_position_id


class TestCprEnvFilter:
    @parameterized.expand(
        [
            (True, [], True),
            (True, ["5555555555"], False),
            (False, [], False),
            (False, ["5555555555"], True),
        ]
    )
    def test_return_true_for_exclude_mode_when_cpr_not_in_list(
        self, exclude_mode, cprs, expected
    ):
        settings_dict = deepcopy(DEFAULT_CHANGED_AT_SETTINGS)
        settings_dict.update({"sd_exclude_cprs_mode": exclude_mode, "sd_cprs": cprs})
        settings = Settings.parse_obj(settings_dict)

        entity = {"PersonCivilRegistrationIdentifier": "5555555555"}

        assert cpr_env_filter(settings, entity) == expected


@pytest.mark.parametrize(
    "profession,job_pos_ids_to_skip,expected",
    [
        ({}, ["1", "2", "3"], False),
        ({"JobPositionIdentifier": "4"}, ["1", "2", "3"], False),
        ({"JobPositionIdentifier": "1"}, ["1", "2", "3"], True),
        ({"JobPositionIdentifier": "1"}, [], False),
    ],
)
def test_profession_job_position_id_filter(
    profession: dict,
    job_pos_ids_to_skip: list[str],
    expected: bool,
):
    """
    Test sdlon.skip.skip_job_position_id.

    Args:
        profession: the <Profession> part of the <Employment> of the SD payload
        expected: the expected return value of skip_job_position_id
        job_pos_ids_to_skip: the JobPositionIdentifiers to skip
    """

    # Act
    result = skip_job_position_id(OrderedDict(profession), job_pos_ids_to_skip)

    # Assert
    assert result is expected
