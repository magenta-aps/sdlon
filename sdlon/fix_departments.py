import datetime
import json
from typing import Any
from typing import List
from typing import Optional
from typing import OrderedDict
from uuid import UUID
from uuid import uuid4

import requests
from cachetools.func import ttl_cache  # type: ignore
from more_itertools import one
from os2mo_helpers.mora_helpers import MoraHelper
from sdclient.client import SDClient
from sdclient.requests import GetDepartmentParentRequest
from sdclient.requests import GetDepartmentRequest
from sdclient.requests import GetEmploymentRequest
from structlog.stdlib import get_logger

from . import sd_payloads
from .config import get_settings
from .config import Settings
from .date_utils import datetime_to_sd_date
from .date_utils import format_date
from .date_utils import get_mo_validity
from .date_utils import MO_INFINITY
from .date_utils import parse_datetime
from .date_utils import SD_INFINITY
from .date_utils import sd_to_mo_date
from .engagement import get_eng_user_key
from .engagement import re_terminate_engagement
from .exceptions import NoCurrentValdityException
from .log import setup_logging
from .sd_common import ensure_list
from .sd_common import mora_assert
from .sd_common import sd_lookup


logger = get_logger()


class FixDepartments:
    def __init__(self, settings: Settings, current_inst_id: str, dry_run: bool = False):
        logger.info("Start program")
        self.settings = settings
        self.current_inst_id = current_inst_id
        self.dry_run = dry_run

        self.institution_uuid = self.get_institution(current_inst_id)
        self.helper = self._get_mora_helper(self.settings)

        if self.settings.sd_fix_departments_root is not None:
            self.org_uuid = str(settings.sd_fix_departments_root)
        else:
            try:
                self.org_uuid = self.helper.read_organisation()
            except requests.exceptions.RequestException as e:
                logger.error("Problem getting the MO organization", err=e)
                exit()
            except json.decoder.JSONDecodeError as e:
                logger.error("Problem decoding response JSON", err=e)
                exit()

        logger.info("Read org_unit types")
        self.level_types = self.helper.read_classes_in_facet("org_unit_level")[0]
        unit_types = self.helper.read_classes_in_facet("org_unit_type")[0]

        # Currently only a single unit type exists, we will not do anything fancy
        # until it has been decided what the source for types should be.
        self.unit_type = None
        for unit in unit_types:
            if unit["user_key"] == "Enhed":
                self.unit_type = unit

        if self.unit_type is None:
            raise Exception("Unit types not correctly configured")

        self.sd_client = SDClient(
            sd_username=settings.sd_user,
            sd_password=settings.sd_password.get_secret_value(),
        )

    def _get_mora_helper(self, settings):
        return MoraHelper(hostname=self.settings.mora_base, use_cache=False)

    def get_institution(self, inst_id: str):
        """
        Get the institution uuid of the current organisation. It is uniquely
        determined from the InstitutionIdentifier. The identifier is read
        from settings.json. The value is rarely used, but is needed to dertermine
        if a unit is a root unit.
        :param inst_id: The SD InstitutionIdentifier
        :return: The SD institution uuid for the organisation.
        """
        params = {"UUIDIndicator": "true", "InstitutionIdentifier": inst_id}
        request_uuid = uuid4()
        logger.info("get_institution", request_uuid=request_uuid)
        institution_info = sd_lookup(
            "GetInstitution20111201",
            settings=self.settings,
            params=params,
            request_uuid=request_uuid,
            dry_run=self.dry_run,
            institution_identifier=inst_id,
        )
        institution = institution_info["Region"]["Institution"]
        institution_uuid = institution["InstitutionUUIDIdentifier"]
        return institution_uuid

    def create_single_department(
        self, department: OrderedDict, parent_uuid: str | None
    ) -> None:
        """
        Create an organization unit in MO based on the corresponding department info
        from SD.

        Args:
            department: The SD department
            parent_uuid: The parent UUID of the department in SD
        """
        logger.info(
            "Create department", sd_dep_uuid=department["DepartmentUUIDIdentifier"]
        )

        effective_parent_uuid = (
            parent_uuid if parent_uuid is not None else self.org_uuid
        )

        for unit_level in self.level_types:
            if unit_level["user_key"] == department["DepartmentLevelIdentifier"]:
                unit_level_uuid = unit_level["uuid"]

        logger.debug("SD department", department=department)

        assert self.unit_type is not None
        payload = sd_payloads.create_single_org_unit(
            department=department,
            unit_type=self.unit_type["uuid"],
            unit_level=unit_level_uuid,
            parent=effective_parent_uuid,
        )
        logger.debug("Create MO department (ou/create)", payload=payload)
        if not self.dry_run:
            response = self.helper._mo_post("ou/create", payload)
            response.raise_for_status()
            logger.info("Created unit")

    def _create_org_unit_if_missing_in_mo(
        self, department: OrderedDict, parent_uuid: Optional[str]
    ) -> bool:
        """
        Create SD department in MO if it is missing.

        Args:
            department: the SD department
            parent_uuid: UUID of the parent unit

        Returns:
            Boolean indicating whether the unit was created in MO or not.
        """

        logger.debug("_create_org_unit_if_missing_in_mo called")

        # This is a hack which should be removed once
        # https://redmine.magenta-aps.dk/issues/56846 has been resolved
        date_at = parse_datetime(department["ActivationDate"])
        if date_at <= datetime.datetime(1930, 1, 1):
            date_at = datetime.datetime(1930, 1, 2)
        date_at_str = format_date(date_at)

        logger.debug(
            "Read OU from MO",
            org_unit=department["DepartmentUUIDIdentifier"],
            at=date_at_str,
        )
        mo_response = self.helper.read_ou(
            department["DepartmentUUIDIdentifier"], at=date_at_str
        )
        logger.debug("Response", mo_response=mo_response)

        ou_created = False
        if mo_response.get("status") == 404:
            # TODO: create_single_department should return the boolean value of ou_created   # noqa
            self.create_single_department(department, parent_uuid)
            ou_created = True

        logger.debug("OU created", ou_created=ou_created)

        return ou_created

    def _update_org_unit_for_single_sd_dep_registration(
        self, department: OrderedDict, parent_uuid: Optional[str]
    ) -> None:
        # Get SD department data
        unit_uuid = department["DepartmentUUIDIdentifier"]
        name = department["DepartmentName"]
        shortname = department["DepartmentIdentifier"]
        department_level_identifier = department["DepartmentLevelIdentifier"]
        from_date = department["ActivationDate"]
        to_date = department["DeactivationDate"]
        to_date = MO_INFINITY if to_date == SD_INFINITY else to_date

        unit_level_uuid = None
        for unit_level in self.level_types:
            if unit_level["user_key"] == department_level_identifier:
                unit_level_uuid = unit_level["uuid"]
        if unit_level_uuid is None:
            logger.exception(
                "Unknown department level!!",
                department_level_identifier=department_level_identifier,
            )
            raise Exception("Unknown department level!!")

        parent = parent_uuid if parent_uuid is not None else self.org_uuid

        logger.info("Unit parent at from_date", from_date=from_date, parent_uuid=parent)

        assert self.unit_type is not None
        payload = sd_payloads.edit_org_unit(
            user_key=shortname,
            name=name,
            unit_uuid=unit_uuid,
            parent=parent,
            ou_level=unit_level_uuid,
            ou_type=self.unit_type["uuid"],
            from_date=from_date,
            to_date=to_date,
        )
        logger.debug("Edit payload to fix unit (details/edit)", payload=payload)
        if not self.dry_run:
            response = self.helper._mo_post("details/edit", payload)
            logger.debug("Edit response status: {}".format(response.status_code))
            if response.status_code == 400:
                assert response.text.find("raise to a new registration") > 0
            else:
                response.raise_for_status()

    def fix_department(self, unit_uuid: str, validity_date: datetime.date) -> None:
        """
        Synchronize the state of a MO unit to the current and future state(s) in SD.
        :param unit_uuid: uuid of the unit to be updated.
        :param validity_date: The validity date to read the department info from SD.
        """

        logger.info("Fix department", unit_uuid=unit_uuid, validity_date=validity_date)
        validity = {
            "from_date": validity_date.strftime("%d.%m.%Y"),
            "to_date": datetime_to_sd_date(parse_datetime(SD_INFINITY)),
        }

        departments = self.get_department(validity, uuid=unit_uuid)
        for department in departments:
            # Get the UUID of the parent unit
            parent_lookup_date = max(
                validity_date, parse_datetime(department["ActivationDate"]).date()
            )
            parent_uuid = self.get_parent(unit_uuid, parent_lookup_date)

            # Create org unit if missing in MO
            ou_created = self._create_org_unit_if_missing_in_mo(department, parent_uuid)

            # ... and fix the parent before updating the unit itself
            if parent_uuid is not None:
                self.fix_department(parent_uuid, validity_date)

            if not ou_created:
                self._update_org_unit_for_single_sd_dep_registration(
                    department, parent_uuid
                )
        logger.info(
            "Fixed department", unit_uuid=unit_uuid, validity_date=validity_date
        )

    def get_department(
        self, validity, shortname=None, uuid=None
    ) -> List[OrderedDict[str, Any]]:
        """
        Read department information from SD.
        NOTICE: Shortnames are not universally unique in SD, and even a request
        spanning a single date might return more than one row if searched by
        shortname.
        :param validity: Validity dictionaty.
        :param shortname: Shortname for the unit(s).
        :param uuid: uuid for the unit.
        :return: A list of information about the unit(s).
        """
        params = {
            "ActivationDate": validity["from_date"],
            "DeactivationDate": validity["to_date"],
            "ContactInformationIndicator": "true",
            "DepartmentNameIndicator": "true",
            "PostalAddressIndicator": "false",
            "ProductionUnitIndicator": "false",
            "UUIDIndicator": "true",
            "EmploymentDepartmentIndicator": "false",
        }
        if uuid is not None:
            params["DepartmentUUIDIdentifier"] = uuid
        if shortname is not None:
            params["DepartmentIdentifier"] = shortname

        if uuid is None and shortname is None:
            raise Exception("Provide either uuid or shortname")

        request_uuid = uuid4()
        logger.info("get_department", request_uuid=request_uuid)
        department_info = sd_lookup(
            "GetDepartment20111201",
            settings=self.settings,
            params=params,
            request_uuid=request_uuid,
            dry_run=self.dry_run,
            institution_identifier=self.current_inst_id,
        )
        department = department_info.get("Department")
        if department is None:
            raise NoCurrentValdityException()
        if isinstance(department, OrderedDict):
            department = [department]
        return department

    # Notice! Similar code also exists in sd_changed_at
    def _find_engagement(self, mo_engagements, user_key):
        """
        Given a list of engagements for a person, find the one with a specific
        job_id. If several elements covering the same engagement is in the list
        an unspecified element will be returned.
        :param mo_engagements: A list of engagements as returned by MO.
        :param user_key: The MO engagement user_key
        :return: Some element in the list that has the correct job_id. If no
        engagement is found, None is returned.
        """
        relevant_engagement = None

        for mo_eng in mo_engagements:
            if mo_eng["user_key"] == user_key:
                relevant_engagement = mo_eng

        if relevant_engagement is None:
            logger.info(
                "Fruitlessly searched for employment_id in MO engagements",
                user_key=user_key,
                mo_engagements=mo_engagements,
            )
        return relevant_engagement

    def _read_department_engagements(self, unit_uuid, validity_date):
        """
        Retrive a list from SD with all engagements in a given department.
        All current (as of validity_date) and future engagements are retrived,
        since GetEngagement does not support time ranges, we ask for three
        points in time that should cover all known future.
        :param unit_uuid: uuid of the relevant department.
        :param validity_date: The origin of the query, all engagements newer than
        this will be retrieved.
        :return: Dict with cpr as key and SD Person objects as values.
        """
        fix_date = validity_date + datetime.timedelta(weeks=80)
        too_deep = self.settings.sd_import_too_deep
        sd_validity = {
            "from_date": fix_date.strftime("%d.%m.%Y"),
            "to_date": fix_date.strftime("%d.%m.%Y"),
        }
        department = self.get_department(sd_validity, uuid=unit_uuid)[0]
        if not department["DepartmentLevelIdentifier"] in too_deep:
            logger.info(
                "Enhed regnes ikke som et SD afdelingsniveau", unit_uuid=unit_uuid
            )
            return {}

        params = {
            "DepartmentIdentifier": department["DepartmentIdentifier"],
            "DepartmentLevelIdentifier": department["DepartmentLevelIdentifier"],
            "StatusActiveIndicator": True,
            "StatusPassiveIndicator": False,
            "DepartmentIndicator": True,
            "UUIDIndicator": True,
        }

        # We need to catch all current and future engagements, this is an attempt to
        # do so, without making too many calls to the api.
        time_deltas = [0, 90, 365]

        all_people = {}
        logger.debug("Perform GetEmployments", time_deltas=time_deltas)
        for time_delta in time_deltas:
            effective_date = validity_date + datetime.timedelta(days=time_delta)
            params["EffectiveDate"] = (effective_date.strftime("%d.%m.%Y"),)
            request_uuid = uuid4()
            logger.info(
                "_read_department_engagements",
                request_uuid=request_uuid,
                time_delta=time_delta,
            )
            employments = sd_lookup(
                "GetEmployment20111201",
                settings=self.settings,
                params=params,
                request_uuid=request_uuid,
                dry_run=self.dry_run,
                institution_identifier=self.current_inst_id,
            )
            people = employments.get("Person", [])
            if not isinstance(people, list):
                people = [people]

            for person in people:
                cpr = person["PersonCivilRegistrationIdentifier"]
                if cpr not in all_people:
                    all_people[cpr] = person
        logger.debug("Department engagements", all_people=all_people.keys())
        return all_people

    @ttl_cache(ttl=1800)
    def _get_sd_ny_logic_unit(self, unit: UUID, lookup_date: datetime.date) -> UUID:
        """
        Get the UUID of the correct NY-logic elevated unit at a given time.
        """
        effective_lookup_date = max(lookup_date, datetime.date.today())
        logger.debug(
            "Get NY-logic unit",
            unit=str(unit),
            lookup_date=lookup_date,
            effective_lookup_date=effective_lookup_date,
        )

        def get_unit_level(unit_: UUID) -> str:
            r_get_department = self.sd_client.get_department(
                GetDepartmentRequest(
                    InstitutionIdentifier=self.current_inst_id,
                    DepartmentUUIDIdentifier=unit_,
                    ActivationDate=effective_lookup_date,
                    DeactivationDate=effective_lookup_date,
                    UUIDIndicator=True,
                )
            )
            department = one(r_get_department.Department)
            return department.DepartmentLevelIdentifier

        unit_level = get_unit_level(unit)

        destination_unit = unit
        while unit_level in self.settings.sd_import_too_deep:
            r_get_department_parent = self.sd_client.get_department_parent(
                GetDepartmentParentRequest(
                    EffectiveDate=effective_lookup_date,
                    DepartmentUUIDIdentifier=destination_unit,
                )
            )
            parent_uuid = (
                r_get_department_parent.DepartmentParent.DepartmentUUIDIdentifier
            )
            unit_level = get_unit_level(parent_uuid)
            destination_unit = parent_uuid

        logger.debug(
            "Got NY-logic unit",
            unit_level=unit_level,
            destination_unit=str(destination_unit),
        )

        return destination_unit

    def _get_sd_employment_data(
        self, cpr: str, emp_id: str, lookup_date: datetime.date
    ) -> tuple[UUID, datetime.date]:
        """
        Get the SD department unit and department end date for the given employment.
        """
        # This is necessary due to bad data in MO
        effective_lookup_date = max(lookup_date, datetime.date.today())
        logger.debug(
            "Get SD employment",
            cpr=cpr,
            emp_id=emp_id,
            lookup_date=lookup_date,
            effective_lookup_date=effective_lookup_date,
        )
        r_get_employment = self.sd_client.get_employment(
            GetEmploymentRequest(
                InstitutionIdentifier=self.current_inst_id,
                EffectiveDate=effective_lookup_date,
                PersonCivilRegistrationIdentifier=cpr,
                EmploymentIdentifier=emp_id,
                EmploymentStatusIndicator=True,
                ProfessionIndicator=True,
                DepartmentIndicator=True,
                UUIDIndicator=True,
            )
        )

        employment_department = one(
            one(r_get_employment.Person).Employment
        ).EmploymentDepartment

        return (
            employment_department.DepartmentUUIDIdentifier,
            employment_department.DeactivationDate,
        )

    def fix_NY_logic(self, unit_uuid, validity_date, eng_user_key: str | None = None):
        """
        Read all engagements in a unit and ensure that the position in MO is correct
        according to the rules of the import (ie, move engagement up from
        'Afdeling'). This is mainly relevant if an 'Afdeling' is moved to have a new
        NY-department as parent.
        Notice that this should be called AFTER the recursive fix of the department
        tree to ensure that the logic is applied to a self-consistent tree.

        If an engagement is already correct, it will not be moved, if it is currently
        in a wrong unit, it will be corrected.
        :param unit_uuid: uuid of the unit to check.
        :validity_date: The validity_date of the operation, moved engagements will
        be moved as of this date.
        """
        logger.info(
            "fix_NY_logic",
            unit_uuid=unit_uuid,
            validity_date=validity_date,
            eng_user_key=eng_user_key,
        )
        all_people = self._read_department_engagements(unit_uuid, validity_date)

        # We now have a list of all current and future people in the unit,
        # they should all be unconditionally moved if they are not already
        # in destination_unit.
        for person in all_people.values():
            cpr = person["PersonCivilRegistrationIdentifier"]

            if not isinstance(person["Employment"], list):
                person["Employment"] = [person["Employment"]]

            for employment in person["Employment"]:
                user_key = get_eng_user_key(
                    employment["EmploymentIdentifier"],
                    self.current_inst_id,
                    self.settings.sd_prefix_eng_user_key_with_inst_id,
                )

                if eng_user_key is not None and not user_key == eng_user_key:
                    continue

                logger.info("Processing engagement", cpr=cpr, user_key=user_key)
                sd_uuid = employment["EmploymentDepartment"]["DepartmentUUIDIdentifier"]
                if not sd_uuid == unit_uuid:
                    # This employment is not from the current department,
                    # but is inherited from a lower level. Can happen if this
                    # tool is initiated on a level higher than Afdelings-niveau.
                    continue

                mo_person = self.helper.read_user(user_cpr=cpr, org_uuid=self.org_uuid)
                if mo_person is None:
                    logger.warning("MO person is None", user_key=user_key)
                    continue

                mo_engagements = self.helper.read_user_engagement(
                    mo_person["uuid"], read_all=True, only_primary=True, skip_past=True
                )

                # Find the uuid of the relevant engagement and update all current and
                # future rows.
                mo_engagement = self._find_engagement(mo_engagements, user_key)
                if mo_engagement is None:
                    logger.warning(
                        "MO engagement is None",
                        user_key=user_key,
                        mo_person_uuid=mo_person["uuid"],
                    )
                    continue

                # We need to find the engagement with the latest validity, so we can
                # re-terminate below if necessary. This variable is declared with a
                # dummy validity with a low "to" date for the sake of the comparisons
                # in the loop below
                last_eng = {
                    "validity": {
                        "from": format_date(datetime.date.min),  # Not used
                        "to": format_date(datetime.date.min),
                    }
                }

                # Engagement UUIDs to re-terminate
                engs_to_re_terminate: set[str] = set()

                for eng in mo_engagements:
                    if not eng["uuid"] == mo_engagement["uuid"]:
                        # This engagement is not relevant for this unit
                        continue

                    eng_validity = get_mo_validity(eng)
                    from_date, to_date = eng_validity["from"], eng_validity["to"]
                    from_date_str = format_date(from_date)

                    logger.info(
                        "Processing MO engagement",
                        eng_uuid=eng["uuid"],
                        from_date=from_date,
                        to_date=to_date,
                    )

                    last_eng_validity = get_mo_validity(last_eng)
                    if to_date >= last_eng_validity["to"]:
                        last_eng = eng

                    sd_emp_dep_unit, sd_emp_dep_end_date = self._get_sd_employment_data(
                        cpr=cpr,
                        emp_id=employment["EmploymentIdentifier"],
                        lookup_date=from_date,
                    )

                    destination_unit = self._get_sd_ny_logic_unit(
                        unit=sd_emp_dep_unit, lookup_date=from_date
                    )

                    if eng["org_unit"]["uuid"] == str(destination_unit):
                        # This engagement is already in the correct unit
                        logger.info("Engagement already in the correct unit")
                        continue

                    if from_date < validity_date:
                        from_date_str = format_date(validity_date)

                    data = {
                        "org_unit": {"uuid": str(destination_unit)},
                        "validity": {
                            "from": from_date_str,
                            "to": sd_to_mo_date(format_date(sd_emp_dep_end_date)),
                        },
                    }
                    payload = sd_payloads.engagement(data, mo_engagement)
                    logger.debug(
                        "Move engagement payload (details/edit)", payload=payload
                    )
                    if not self.dry_run:
                        response = self.helper._mo_post("details/edit", payload)
                        mora_assert(response)

                    engs_to_re_terminate.add(eng["uuid"])

                if last_eng.get("uuid") in engs_to_re_terminate:
                    re_terminate_engagement(
                        self.helper,
                        last_eng,
                        employment["EmploymentDepartment"],
                        ensure_list(employment.get("EmploymentStatus", [])),
                        self.dry_run,
                    )

    def get_parent(self, unit_uuid, validity_date) -> Optional[str]:
        """
        Return the parent of a given department at at given point in time.
        Notice that the query is perfomed against SD, not against MO.
        It is generally not possible to predict whether this call will succeed, since
        this depends on the internal start-date at SD, which cannot be read from the
        API; the user of this function should be prepared to handle
        NoCurrentValdityException, unless the validity of the unit is known from
        other sources. In general queries to the future and near past should always
        be safe if the unit exists at the point in time.
        :param unit_uuid: uuid of the unit to be queried.
        :param validity_date: python datetime object with the date to query.
        :return: uuid of the parent department, None if the department is a root.
        """
        params = {
            "EffectiveDate": validity_date.strftime("%d.%m.%Y"),
            "DepartmentUUIDIdentifier": unit_uuid,
        }
        request_uuid = uuid4()
        logger.info("get_parent", request_uuid=request_uuid)
        parent_response = sd_lookup(
            "GetDepartmentParent20190701",
            settings=self.settings,
            params=params,
            request_uuid=request_uuid,
            dry_run=self.dry_run,
            institution_identifier=self.current_inst_id,
        )
        if "DepartmentParent" not in parent_response:
            logger.error(
                "No parent found at this date",
                unit_uuid=unit_uuid,
                validity_date=validity_date,
            )
            raise NoCurrentValdityException()
        parent = parent_response["DepartmentParent"]["DepartmentUUIDIdentifier"]
        if parent == self.institution_uuid:
            parent = None
        return parent

    def get_all_parents(self, leaf_uuid, validity_date):
        """
        Find all parents from leaf unit up to the root of the tree.
        Notice, this is a query to SD, not to MO.
        :param leaf_uuid: The starting point of the chain, this does not stictly need
        to be a leaf node.
        :validity_date: The validity date of the fix.
        :return: A list of tuples containing short names and unit uuids sorted from
        leaf to root.
        """
        validity = {
            "from_date": validity_date.strftime("%d.%m.%Y"),
            "to_date": validity_date.strftime("%d.%m.%Y"),
        }
        department_branch = []
        department = self.get_department(validity=validity, uuid=leaf_uuid)[0]
        department_branch.append((department["DepartmentIdentifier"], leaf_uuid))

        current_uuid = self.get_parent(
            department["DepartmentUUIDIdentifier"], validity_date=validity_date
        )

        while current_uuid is not None:
            current_uuid = self.get_parent(
                department["DepartmentUUIDIdentifier"], validity_date=validity_date
            )
            department = self.get_department(validity=validity, uuid=current_uuid)[0]
            shortname = department["DepartmentIdentifier"]
            level = department["DepartmentLevelIdentifier"]
            uuid = department["DepartmentUUIDIdentifier"]
            department_branch.append((shortname, uuid))
            current_uuid = self.get_parent(current_uuid, validity_date=validity_date)
            logger.debug("Department", shortname=shortname, uuid=uuid, level=level)
        return department_branch

    def sd_uuid_from_short_code(self, validity_date, shortname):
        validity = {
            "from_date": validity_date.strftime("%d.%m.%Y"),
            "to_date": validity_date.strftime("%d.%m.%Y"),
        }
        department = self.get_department(validity, shortname=shortname)[0]
        return department["DepartmentUUIDIdentifier"]


def unit_fixer(ou_uuid: UUID):
    """Sync SD department information to MO."""
    settings = get_settings()
    setup_logging(
        settings.log_level,
        settings.log_to_file,
        settings.log_file,
        settings.log_file_backup_count,
    )

    if ou_uuid == settings.sd_fix_departments_root:
        logger.info("Cannot fix the root unit!")
        return

    assert isinstance(settings.sd_institution_identifier, str)
    unit_fixer = FixDepartments(settings, settings.sd_institution_identifier)

    today = datetime.datetime.today().date()

    logger.info("Calling fix_departments", ou_uuid=ou_uuid)
    unit_fixer.fix_department(str(ou_uuid), today)

    logger.info("Calling fix_NY_logic", ou_uuid=ou_uuid)
    unit_fixer.fix_NY_logic(str(ou_uuid), today)

    logger.info("unit_fixer done!")
