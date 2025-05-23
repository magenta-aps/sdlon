from collections import OrderedDict
from copy import deepcopy
from datetime import date
from datetime import datetime
from typing import Dict
from typing import Optional
from unittest import mock
from unittest import TestCase
from unittest.mock import call
from unittest.mock import MagicMock
from uuid import UUID
from uuid import uuid4

import pytest
from freezegun import freeze_time
from os2mo_helpers.mora_helpers import MoraHelper
from requests import Response
from sdclient.client import SDClient
from sdclient.responses import Department
from sdclient.responses import DepartmentParent
from sdclient.responses import Employment
from sdclient.responses import EmploymentDepartment
from sdclient.responses import EmploymentStatus
from sdclient.responses import GetDepartmentParentResponse
from sdclient.responses import GetDepartmentResponse
from sdclient.responses import GetEmploymentResponse
from sdclient.responses import Person

from .test_config import DEFAULT_CHANGED_AT_SETTINGS
from sdlon.config import Settings
from sdlon.fix_departments import FixDepartments


def mock_sd_lookup(service_name, expected_params, response):
    base_responses = {
        "GetDepartment20111201": {
            "Department": [
                {
                    "DepartmentLevelIdentifier": _TestableFixDepartments.MO_CLASS_USER_KEY,  # noqa
                    "DepartmentIdentifier": _TestableFixDepartments.SD_DEPARTMENT_SHORTNAME,  # noqa
                    "DepartmentName": _TestableFixDepartments.SD_DEPARTMENT_NAME,
                    "DepartmentUUIDIdentifier": "99999999-9999-9999-9999-999999999999",
                    "ActivationDate": "2019-01-01",
                    "DeactivationDate": "9999-12-31",
                }
            ],
        }
    }

    _response = deepcopy(base_responses[service_name])
    _response.update(response)
    sd_lookup_path = "sdlon.fix_departments.sd_lookup"
    sd_lookup_mock = mock.patch(sd_lookup_path, return_value=_response)
    return sd_lookup_mock


class _TestableFixDepartments(FixDepartments):
    MO_ORG_ROOT = "00000000-0000-0000-0000-000000000000"
    MO_CLASS_USER_KEY = "Enhed"
    MO_CLASS_UUID = str(uuid4())
    SD_INSTITUTION_UUID = str(uuid4())
    SD_DEPARTMENT_NAME = "some department name"
    SD_DEPARTMENT_SHORTNAME = "some department short name"
    SD_DEPARTMENT_PARENT_UUID = str(uuid4())

    @classmethod
    def get_instance(cls, settings_dict: Optional[Dict] = None):
        all_settings_dict = deepcopy(DEFAULT_CHANGED_AT_SETTINGS)
        if settings_dict is not None:
            all_settings_dict.update(settings_dict)
        settings = Settings.parse_obj(all_settings_dict)

        read_mo_org = "sdlon.fix_departments.MoraHelper.read_organisation"
        with mock.patch(read_mo_org, return_value=cls.MO_ORG_ROOT):
            return cls(settings, settings.sd_institution_identifier)

    def get_institution(self, institution_identifier: str):
        return self.SD_INSTITUTION_UUID

    def get_parent(self, unit_uuid, validity_date):
        return self.SD_DEPARTMENT_PARENT_UUID

    def _get_mora_helper(self, settings):
        mock_helper = mock.MagicMock(spec=MoraHelper)
        mock_helper.read_organisation = mock.Mock(
            return_value=_TestableFixDepartments.MO_ORG_ROOT
        )
        mock_helper.read_classes_in_facet = mock.Mock(
            return_value=[
                [{"user_key": self.MO_CLASS_USER_KEY, "uuid": self.MO_CLASS_UUID}]
            ]
        )
        return mock_helper


class TestFixDepartmentsRootSetting:
    alternate_root = str(uuid4())

    @pytest.mark.parametrize(
        "settings,expected_root",
        [
            # Case 1: Default root
            (
                {},
                _TestableFixDepartments.MO_ORG_ROOT,
            ),
            # Case 2: Alternate root
            (
                {
                    "sd_fix_departments_root": alternate_root,
                },
                alternate_root,
            ),
        ],
    )
    def test_root(self, settings, expected_root):
        instance = _TestableFixDepartments.get_instance(settings_dict=settings)
        assert instance.org_uuid == expected_root


class TestFixDepartment(TestCase):
    def test_update_root_unit(self):
        instance = _TestableFixDepartments.get_instance()
        instance.get_parent = MagicMock(return_value=None)
        instance._create_org_unit_if_missing_in_mo = MagicMock(return_value=False)
        with mock_sd_lookup("GetDepartment20111201", {}, {}):
            instance.fix_department(
                "99999999-9999-9999-9999-999999999999", date(2020, 1, 1)
            )
            instance.helper._mo_post.assert_called_with(
                "details/edit",
                {
                    "type": "org_unit",
                    "data": {
                        "uuid": "99999999-9999-9999-9999-999999999999",
                        "user_key": instance.SD_DEPARTMENT_SHORTNAME,
                        "name": instance.SD_DEPARTMENT_NAME,
                        "parent": {"uuid": instance.MO_ORG_ROOT},
                        "org_unit_level": {"uuid": instance.MO_CLASS_UUID},
                        "org_unit_type": {"uuid": instance.MO_CLASS_UUID},
                        "validity": {"from": "2019-01-01", "to": None},
                    },
                },
            )

    def test_multiple_sd_root_department_registrations(self):
        instance = _TestableFixDepartments.get_instance()
        instance.get_parent = MagicMock(return_value=None)
        instance._create_org_unit_if_missing_in_mo = MagicMock(return_value=False)
        sd_response = {
            "Department": [
                {
                    "DepartmentLevelIdentifier": _TestableFixDepartments.MO_CLASS_USER_KEY,  # noqa
                    "DepartmentIdentifier": _TestableFixDepartments.SD_DEPARTMENT_SHORTNAME,  # noqa
                    "DepartmentUUIDIdentifier": "uuid",
                    "DepartmentName": _TestableFixDepartments.SD_DEPARTMENT_NAME,
                    "ActivationDate": "2019-01-01",
                    "DeactivationDate": "2023-12-31",
                },
                {
                    "DepartmentLevelIdentifier": _TestableFixDepartments.MO_CLASS_USER_KEY,  # noqa
                    "DepartmentIdentifier": _TestableFixDepartments.SD_DEPARTMENT_SHORTNAME,  # noqa
                    "DepartmentUUIDIdentifier": "uuid",
                    "DepartmentName": "new name",
                    "ActivationDate": "2024-01-01",
                    "DeactivationDate": "9999-12-31",
                },
            ]
        }
        with mock_sd_lookup("GetDepartment20111201", dict(), sd_response):
            instance.fix_department("uuid", date(2020, 1, 1))

        call_list = instance.helper._mo_post.mock_calls

        first_mo_call = call(
            "details/edit",
            {
                "type": "org_unit",
                "data": {
                    "uuid": "uuid",
                    "user_key": instance.SD_DEPARTMENT_SHORTNAME,
                    "name": instance.SD_DEPARTMENT_NAME,
                    "parent": {"uuid": instance.MO_ORG_ROOT},
                    "org_unit_level": {"uuid": instance.MO_CLASS_UUID},
                    "org_unit_type": {"uuid": instance.MO_CLASS_UUID},
                    "validity": {"from": "2019-01-01", "to": "2023-12-31"},
                },
            },
        )
        second_mo_call = call(
            "details/edit",
            {
                "type": "org_unit",
                "data": {
                    "uuid": "uuid",
                    "user_key": instance.SD_DEPARTMENT_SHORTNAME,
                    "name": "new name",
                    "parent": {"uuid": instance.MO_ORG_ROOT},
                    "org_unit_level": {"uuid": instance.MO_CLASS_UUID},
                    "org_unit_type": {"uuid": instance.MO_CLASS_UUID},
                    "validity": {"from": "2024-01-01", "to": None},
                },
            },
        )

        assert first_mo_call in call_list
        assert second_mo_call in call_list

    def test_create_root_org_unit_if_unit_does_not_exists_in_mo(self):
        # Arrange
        instance = _TestableFixDepartments.get_instance()
        instance.get_parent = MagicMock(
            return_value=None
        )  # Meaning the unit is a root unit
        instance.helper.read_ou = MagicMock(return_value={"status": 404})
        instance._update_org_unit_for_single_sd_dep_registration = MagicMock()

        # Act
        with mock_sd_lookup("GetDepartment20111201", dict(), dict()):
            instance.fix_department(
                "99999999-9999-9999-9999-999999999999", datetime.today().date()
            )

        # Assert
        instance.helper._mo_post.assert_called_once_with(
            "ou/create",
            {
                "uuid": "99999999-9999-9999-9999-999999999999",
                "user_key": _TestableFixDepartments.SD_DEPARTMENT_SHORTNAME,
                "name": _TestableFixDepartments.SD_DEPARTMENT_NAME,
                "parent": {"uuid": _TestableFixDepartments.MO_ORG_ROOT},
                "org_unit_type": {"uuid": _TestableFixDepartments.MO_CLASS_UUID},
                "org_unit_level": {"uuid": _TestableFixDepartments.MO_CLASS_UUID},
                "validity": {
                    "from": "2019-01-01",
                    "to": None,
                },
            },
        )
        instance._update_org_unit_for_single_sd_dep_registration.assert_not_called()

    def test_create_parent_org_unit_if_unit_does_not_exists_in_mo(self):
        # Arrange
        instance = _TestableFixDepartments.get_instance()

        unit_uuid = "11111111-1111-1111-1111-111111111111"
        parent_uuid = "22222222-2222-2222-2222-222222222222"
        today = datetime.today().date()

        instance.get_parent = MagicMock(side_effect=[parent_uuid, None])
        instance.get_department = MagicMock(
            side_effect=[
                [
                    {
                        "DepartmentLevelIdentifier": _TestableFixDepartments.MO_CLASS_USER_KEY,  # noqa
                        "DepartmentIdentifier": _TestableFixDepartments.SD_DEPARTMENT_SHORTNAME,  # noqa
                        "DepartmentUUIDIdentifier": unit_uuid,
                        "DepartmentName": _TestableFixDepartments.SD_DEPARTMENT_NAME,
                        "ActivationDate": "2019-01-01",
                        "DeactivationDate": "9999-12-31",
                    }
                ],
                [
                    {
                        "DepartmentLevelIdentifier": _TestableFixDepartments.MO_CLASS_USER_KEY,  # noqa
                        "DepartmentIdentifier": "Parent shortname",
                        "DepartmentUUIDIdentifier": parent_uuid,
                        "DepartmentName": "Parent",
                        "ActivationDate": "2019-01-01",
                        "DeactivationDate": "9999-12-31",
                    }
                ],
            ]
        )

        instance.helper.read_ou = MagicMock(side_effect=[dict(), {"status": 404}])

        expected_calls = [
            call(
                "ou/create",
                {
                    "uuid": "22222222-2222-2222-2222-222222222222",
                    "user_key": "Parent shortname",
                    "name": "Parent",
                    "parent": {"uuid": "00000000-0000-0000-0000-000000000000"},
                    "org_unit_type": {"uuid": _TestableFixDepartments.MO_CLASS_UUID},
                    "org_unit_level": {"uuid": _TestableFixDepartments.MO_CLASS_UUID},
                    "validity": {"from": "2019-01-01", "to": None},
                },
            ),
            call(
                "details/edit",
                {
                    "type": "org_unit",
                    "data": {
                        "uuid": "11111111-1111-1111-1111-111111111111",
                        "user_key": "some department short name",
                        "name": "some department name",
                        "parent": {"uuid": "22222222-2222-2222-2222-222222222222"},
                        "org_unit_level": {
                            "uuid": _TestableFixDepartments.MO_CLASS_UUID
                        },
                        "org_unit_type": {
                            "uuid": _TestableFixDepartments.MO_CLASS_UUID
                        },
                        "validity": {"from": "2019-01-01", "to": None},
                    },
                },
            ),
        ]

        # Act
        instance.fix_department(unit_uuid, today)

        # Assert
        actual_calls = instance.helper._mo_post.call_args_list
        assert expected_calls == actual_calls

        get_parent_calls = instance.get_parent.call_args_list
        assert get_parent_calls == [
            call("11111111-1111-1111-1111-111111111111", today),
            call("22222222-2222-2222-2222-222222222222", today),
        ]

    def test_fix_department_called_recursively(self):
        # Arrange
        instance = _TestableFixDepartments.get_instance()

        unit_uuid = "11111111-1111-1111-1111-111111111111"
        parent_uuid = "22222222-2222-2222-2222-222222222222"

        instance.get_parent = MagicMock(side_effect=[parent_uuid, None])
        instance.get_department = MagicMock(
            side_effect=[
                [
                    {
                        "DepartmentLevelIdentifier": _TestableFixDepartments.MO_CLASS_USER_KEY,  # noqa
                        "DepartmentIdentifier": _TestableFixDepartments.SD_DEPARTMENT_SHORTNAME,  # noqa
                        "DepartmentUUIDIdentifier": unit_uuid,
                        "DepartmentName": _TestableFixDepartments.SD_DEPARTMENT_NAME,
                        "ActivationDate": "2019-01-01",
                        "DeactivationDate": "9999-12-31",
                    }
                ],
                [
                    {
                        "DepartmentLevelIdentifier": _TestableFixDepartments.MO_CLASS_USER_KEY,  # noqa
                        "DepartmentIdentifier": "Parent shortname",
                        "DepartmentUUIDIdentifier": parent_uuid,
                        "DepartmentName": "Parent",
                        "ActivationDate": "2019-01-01",
                        "DeactivationDate": "9999-12-31",
                    }
                ],
            ]
        )

        instance._create_org_unit_if_missing_in_mo = MagicMock(return_value=False)
        instance._update_org_unit_for_single_sd_dep_registration = MagicMock()

        # Act
        instance.fix_department(str(unit_uuid), date(2020, 1, 1))

        # Assert
        create_org_unit_calls = instance._create_org_unit_if_missing_in_mo.mock_calls
        update_calls = (
            instance._update_org_unit_for_single_sd_dep_registration.mock_calls
        )

        assert create_org_unit_calls == [
            call(
                {
                    "DepartmentLevelIdentifier": "Enhed",
                    "DepartmentIdentifier": "some department short name",
                    "DepartmentUUIDIdentifier": "11111111-1111-1111-1111-111111111111",
                    "DepartmentName": "some department name",
                    "ActivationDate": "2019-01-01",
                    "DeactivationDate": "9999-12-31",
                },
                parent_uuid,
            ),
            call(
                {
                    "DepartmentLevelIdentifier": "Enhed",
                    "DepartmentIdentifier": "Parent shortname",
                    "DepartmentUUIDIdentifier": "22222222-2222-2222-2222-222222222222",
                    "DepartmentName": "Parent",
                    "ActivationDate": "2019-01-01",
                    "DeactivationDate": "9999-12-31",
                },
                None,
            ),
        ]

        assert update_calls == [
            call(
                {
                    "DepartmentLevelIdentifier": "Enhed",
                    "DepartmentIdentifier": "Parent shortname",
                    "DepartmentUUIDIdentifier": parent_uuid,
                    "DepartmentName": "Parent",
                    "ActivationDate": "2019-01-01",
                    "DeactivationDate": "9999-12-31",
                },
                None,
            ),
            call(
                {
                    "DepartmentLevelIdentifier": "Enhed",
                    "DepartmentIdentifier": "some department short name",
                    "DepartmentUUIDIdentifier": unit_uuid,
                    "DepartmentName": "some department name",
                    "ActivationDate": "2019-01-01",
                    "DeactivationDate": "9999-12-31",
                },
                parent_uuid,
            ),
        ]

        get_parent_calls = instance.get_parent.call_args_list
        assert get_parent_calls == [
            call("11111111-1111-1111-1111-111111111111", date(2020, 1, 1)),
            call("22222222-2222-2222-2222-222222222222", date(2020, 1, 1)),
        ]

    def test_fix_ny_logic_elevates_engagement_from_too_deep_levels(self) -> None:
        """
        Test that an engagement is elevated from the "too deep" OU levels to
        the appropriate NY-levels above (happens when the SDTool button is
        pressed). Note: this was the first test of the "apply_NY_logic" function -
        we just test that (parts of it) is works "as is". We really should
        1) Find out what the function should actually do
        2) Test that the engagements dates are set correctly!
        """

        # Arrange
        unit_uuid = str(uuid4())
        parent_unit_uuid = str(uuid4())
        eng_uuid = str(uuid4())
        validity_date = date(2023, 8, 1)
        cpr = "0101901111"

        instance = _TestableFixDepartments.get_instance(
            {"sd_import_too_deep": ["Afdelings-niveau"]}
        )

        instance.helper.read_ou = MagicMock(
            return_value={
                "uuid": unit_uuid,
                "org_unit_level": {
                    "user_key": "Afdelings-niveau",
                },
                "parent": {
                    "uuid": parent_unit_uuid,
                    "org_unit_level": {
                        "user_key": "NY1-niveau",
                    },
                },
            }
        )
        instance._read_department_engagements = MagicMock(
            return_value={
                cpr: OrderedDict(
                    {
                        "PersonCivilRegistrationIdentifier": cpr,
                        "Employment": {
                            "EmploymentIdentifier": "12345",
                            "EmploymentDate": "2020-11-10",
                            "AnniversaryDate": "2004-08-15",
                            "EmploymentDepartment": {
                                "ActivationDate": "2020-11-10",
                                "DeactivationDate": "9999-12-31",
                                "DepartmentIdentifier": "department_id",
                                "DepartmentUUIDIdentifier": unit_uuid,
                            },
                            "Profession": {
                                "ActivationDate": "2020-11-10",
                                "DeactivationDate": "9999-12-31",
                                "JobPositionIdentifier": "2",
                                "EmploymentName": "Title",
                                "AppointmentCode": "0",
                            },
                            "EmploymentStatus": {
                                "ActivationDate": "2020-11-10",
                                "DeactivationDate": "9999-12-31",
                                "EmploymentStatusCode": "1",
                            },
                        },
                    }
                )
            }
        )

        mock_sd_client = MagicMock(spec=SDClient)
        mock_sd_client.get_employment.return_value = GetEmploymentResponse(
            Person=[
                Person(
                    PersonCivilRegistrationIdentifier=cpr,
                    Employment=[
                        Employment(
                            EmploymentIdentifier="12345",
                            EmploymentDate=date(2020, 11, 10),
                            AnniversaryDate=date(2004, 8, 15),
                            EmploymentStatus=EmploymentStatus(
                                ActivationDate=date(2020, 11, 10),
                                DeactivationDate=date(9999, 12, 31),
                                EmploymentStatusCode="1",
                            ),
                            EmploymentDepartment=EmploymentDepartment(
                                ActivationDate=date(2020, 11, 10),
                                DeactivationDate=date(9999, 12, 31),
                                DepartmentIdentifier="department_id",
                                DepartmentUUIDIdentifier=UUID(unit_uuid),
                            ),
                        )
                    ],
                )
            ]
        )
        mock_sd_client.get_department.side_effect = [
            GetDepartmentResponse(
                RegionIdentifier="RI",
                InstitutionIdentifier="II",
                Department=[
                    Department(
                        ActivationDate=date(2020, 11, 10),
                        DeactivationDate=date(9999, 12, 31),
                        DepartmentIdentifier="department_id",
                        DepartmentLevelIdentifier="Afdelings-niveau",
                        DepartmentUUIDIdentifier=UUID(unit_uuid),
                    )
                ],
            ),
            GetDepartmentResponse(
                RegionIdentifier="RI",
                InstitutionIdentifier="II",
                Department=[
                    Department(
                        ActivationDate=date(2020, 11, 10),
                        DeactivationDate=date(9999, 12, 31),
                        DepartmentIdentifier="parent_department_id",
                        DepartmentLevelIdentifier="NY1-niveau",
                        DepartmentUUIDIdentifier=UUID(parent_unit_uuid),
                    )
                ],
            ),
        ]
        mock_sd_client.get_department_parent.return_value = GetDepartmentParentResponse(
            DepartmentParent=DepartmentParent(
                DepartmentUUIDIdentifier=UUID(parent_unit_uuid)
            )
        )
        instance.sd_client = mock_sd_client

        instance.helper.read_user = MagicMock(
            return_value={
                "uuid": str(uuid4()),
            }
        )
        instance.helper.read_user_engagement = MagicMock(
            return_value=[
                {
                    "uuid": eng_uuid,
                    "org_unit": {"uuid": str(uuid4())},
                    "user_key": "12345",
                    "validity": {
                        "from": "2023-01-01",
                        "to": None,
                    },
                }
            ]
        )

        r = Response()
        r.status_code = 200

        instance.helper._mo_post.return_value = r

        # Act
        instance.fix_NY_logic(unit_uuid, validity_date)

        # Assert
        instance.helper._mo_post.assert_called_once_with(
            "details/edit",
            {
                "type": "engagement",
                "uuid": eng_uuid,
                "data": {
                    "org_unit": {"uuid": parent_unit_uuid},
                    "validity": {
                        "from": validity_date.strftime("%Y-%m-%d"),
                        "to": None,
                    },
                },
            },
        )

    @freeze_time("2025-01-25")
    def test_fix_ny_logic_use_sd_department_end_date_and_re_terminate(self) -> None:
        """
        Test that:
        1) We use the SD employment department end date instead of the one on the MO
           engagement when applying the NY-logic.
        2) The above may result in the re-opening of an already terminated engagement in
           MO, why we should call the re-terminate logic from "fix_NY_logic".
        """

        # Arrange
        unit_uuid = str(uuid4())
        parent_unit_uuid = str(uuid4())
        eng_uuid = str(uuid4())
        validity_date = date(2023, 8, 1)
        cpr = "0101901111"

        instance = _TestableFixDepartments.get_instance(
            {"sd_import_too_deep": ["Afdelings-niveau"]}
        )

        instance.helper.read_ou = MagicMock(
            return_value={
                "uuid": unit_uuid,
                "org_unit_level": {
                    "user_key": "Afdelings-niveau",
                },
                "parent": {
                    "uuid": parent_unit_uuid,
                    "org_unit_level": {
                        "user_key": "NY1-niveau",
                    },
                },
            }
        )
        instance._read_department_engagements = MagicMock(
            return_value={
                cpr: OrderedDict(
                    {
                        "PersonCivilRegistrationIdentifier": cpr,
                        "Employment": {
                            "EmploymentIdentifier": "12345",
                            "EmploymentDate": "2020-11-10",
                            "AnniversaryDate": "2004-08-15",
                            "EmploymentDepartment": {
                                "ActivationDate": "2020-11-10",
                                # Department change is valid to infinity
                                "DeactivationDate": "9999-12-31",
                                "DepartmentIdentifier": "department_id",
                                "DepartmentUUIDIdentifier": unit_uuid,
                            },
                            "Profession": {
                                "ActivationDate": "2020-11-10",
                                "DeactivationDate": "9999-12-31",
                                "JobPositionIdentifier": "2",
                                "EmploymentName": "Title",
                                "AppointmentCode": "0",
                            },
                            "EmploymentStatus": {
                                "ActivationDate": "2020-11-10",
                                # Employment ends *before* infinity
                                "DeactivationDate": "2040-12-31",
                                "EmploymentStatusCode": "1",
                            },
                        },
                    }
                )
            }
        )

        mock_sd_client = MagicMock(spec=SDClient)
        mock_sd_client.get_employment.return_value = GetEmploymentResponse(
            Person=[
                Person(
                    PersonCivilRegistrationIdentifier=cpr,
                    Employment=[
                        Employment(
                            EmploymentIdentifier="12345",
                            EmploymentDate=date(2020, 11, 10),
                            AnniversaryDate=date(2004, 8, 15),
                            EmploymentStatus=EmploymentStatus(
                                ActivationDate=date(2020, 11, 10),
                                # Employment ends *before* infinity
                                DeactivationDate=date(2040, 12, 31),
                                EmploymentStatusCode="1",
                            ),
                            EmploymentDepartment=EmploymentDepartment(
                                ActivationDate=date(2020, 11, 10),
                                # Department change is valid to infinity
                                DeactivationDate=date(9999, 12, 31),
                                DepartmentIdentifier="department_id",
                                DepartmentUUIDIdentifier=UUID(unit_uuid),
                            ),
                        )
                    ],
                )
            ]
        )
        mock_sd_client.get_department.side_effect = [
            GetDepartmentResponse(
                RegionIdentifier="RI",
                InstitutionIdentifier="II",
                Department=[
                    Department(
                        ActivationDate=date(2020, 11, 10),
                        DeactivationDate=date(9999, 12, 31),
                        DepartmentIdentifier="department_id",
                        DepartmentLevelIdentifier="Afdelings-niveau",
                        DepartmentUUIDIdentifier=UUID(unit_uuid),
                    )
                ],
            ),
            GetDepartmentResponse(
                RegionIdentifier="RI",
                InstitutionIdentifier="II",
                Department=[
                    Department(
                        ActivationDate=date(2020, 11, 10),
                        DeactivationDate=date(9999, 12, 31),
                        DepartmentIdentifier="parent_department_id",
                        DepartmentLevelIdentifier="NY1-niveau",
                        DepartmentUUIDIdentifier=UUID(parent_unit_uuid),
                    )
                ],
            ),
        ]
        mock_sd_client.get_department_parent.return_value = GetDepartmentParentResponse(
            DepartmentParent=DepartmentParent(
                DepartmentUUIDIdentifier=UUID(parent_unit_uuid)
            )
        )
        instance.sd_client = mock_sd_client

        instance.helper.read_user = MagicMock(
            return_value={
                "uuid": str(uuid4()),
            }
        )
        instance.helper.read_user_engagement = MagicMock(
            return_value=[
                {
                    "uuid": eng_uuid,
                    "org_unit": {"uuid": str(uuid4())},
                    "user_key": "12345",
                    "validity": {
                        "from": "2023-01-01",
                        # The engagement ends *before* infinity
                        "to": "2040-12-31",
                    },
                },
                # Add random engagement placed in another unit
                # (should not be re-terminated)
                {
                    "uuid": str(uuid4()),
                    "org_unit": {"uuid": str(uuid4())},
                    "user_key": "54321",
                    "validity": {
                        "from": "2022-01-01",
                        "to": None,
                    },
                },
            ]
        )

        r = Response()
        r.status_code = 200

        instance.helper._mo_post.return_value = r

        # Act
        instance.fix_NY_logic(unit_uuid, validity_date)

        # Assert
        calls = instance.helper._mo_post.call_args_list
        assert calls == [
            call(
                "details/edit",
                {
                    "type": "engagement",
                    "uuid": eng_uuid,
                    "data": {
                        "org_unit": {"uuid": parent_unit_uuid},
                        "validity": {
                            "from": validity_date.strftime("%Y-%m-%d"),
                            "to": None,
                        },
                    },
                },
            ),
            call(
                "details/terminate",
                {
                    "type": "engagement",
                    "uuid": eng_uuid,
                    "validity": {"from": "2041-01-01", "to": None},
                },
            ),
        ]
