import datetime
import hashlib
import uuid
from enum import Enum
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import OrderedDict
from typing import Union

import requests
import xmltodict

from .config import Settings
from .log import get_logger
from db.queries import log_payload

logger = get_logger()


def sd_lookup(
    url: str,
    settings: Settings,
    params: Optional[Dict[str, Any]] = None,
    request_uuid: uuid.UUID = uuid.uuid4(),
    dry_run: bool = False,
    institution_identifier: str | None = None,
) -> OrderedDict:
    """Fire a requests against SD."""
    # TODO: this could potentially log CPRs - to be fixed
    logger.info("Retrieve: {}".format(url))
    logger.debug("Params: {}".format(params))

    params = params or dict()

    BASE_URL = "https://service.sd.dk/sdws/"
    full_url = BASE_URL + url

    payload = {
        "InstitutionIdentifier": institution_identifier
        if institution_identifier is not None
        else settings.sd_institution_identifier
    }
    payload.update(params)
    auth = (settings.sd_user, settings.sd_password.get_secret_value())
    response = requests.get(
        full_url,
        params=payload,
        auth=auth,
    )

    if settings.sd_persist_payloads and not dry_run:
        try:
            log_payload(
                request_uuid=request_uuid,
                full_url=full_url,
                params=str(payload),
                response=response.text,
                status_code=response.status_code,
            )
        except Exception:
            logger.exception("could not save SD response to payload database")

    dict_response = xmltodict.parse(response.text)

    if url in dict_response:
        xml_response = dict_response[url]
    else:
        msg = "SD api error, envelope: {}, response: {}"
        logger.error(msg.format(dict_response["Envelope"], response.text))
        raise Exception(msg.format(dict_response["Envelope"], response.text))
    logger.debug("Done with {}".format(url))
    return xml_response


def calc_employment_id(employment):
    employment_id = employment["EmploymentIdentifier"]
    try:
        employment_number = int(employment_id)
    except ValueError:  # Job id is not a number?
        employment_number = 999999

    employment_id = {"id": employment_id, "value": employment_number}
    return employment_id


def mora_assert(response):
    """Check response is as expected."""
    assert response.status_code in (200, 201, 400, 404), response.status_code
    if response.status_code == 400:
        # Check actual response
        assert (
            response.text.find("not give raise to a new registration") > 0
        ), response.text
        logger.debug("Request had no effect")
    return None


def generate_uuid(value, org_id_prefix, org_name=None):
    """
    Code almost identical to this also lives in the Opus importer.
    """
    # TODO: Refactor to avoid duplication
    if org_id_prefix:
        base_hash = hashlib.md5(org_id_prefix.encode())
    else:
        base_hash = hashlib.md5(org_name.encode())

    base_digest = base_hash.hexdigest()
    base_uuid = uuid.UUID(base_digest)

    combined_value = (str(base_uuid) + str(value)).encode()
    value_hash = hashlib.md5(combined_value)
    value_digest = value_hash.hexdigest()
    value_uuid = str(uuid.UUID(value_digest))
    return value_uuid


class EmploymentStatus(Enum):
    """Corresponds to EmploymentStatusCode from SD.

    Employees usually start in AnsatUdenLoen, and then change to AnsatMedLoen.
    This will usually happen once they actually have their first day at work.

    From AnsatMedLoen they can somewhat freely transfer to the other statusses.
    This includes transfering back to AnsatMedLoen from any other status.

    Note for instance, that it is entirely possible to be Ophoert and then get
    hired back, and thus go from Ophoert to AnsatMedLoen.

    There is only one terminal state, namely Slettet, wherefrom noone will
    return. This state is invoked from status 7-8-9 after a few years.

    Status Doed will probably only migrate to status slettet, but there are no
    guarantees given.
    """

    # This status represent not yet being at work
    # It is treated as a regular engagement to ensure all it-accounts can be
    # ready for when the engagement starts
    AnsatUdenLoen = "0"

    # These statusses represent being at work
    AnsatMedLoen = "1"
    Orlov = "3"

    # These statusses represent being let go
    Migreret = "7"
    Ophoert = "8"
    Doed = "9"

    # This status is the special terminal state
    Slettet = "S"

    @staticmethod
    def employeed() -> List["EmploymentStatus"]:
        return [
            EmploymentStatus.AnsatUdenLoen,
            EmploymentStatus.AnsatMedLoen,
            EmploymentStatus.Orlov,
        ]

    @staticmethod
    def let_go() -> List["EmploymentStatus"]:
        return [
            EmploymentStatus.Migreret,
            EmploymentStatus.Ophoert,
            EmploymentStatus.Doed,
        ]

    @staticmethod
    def on_payroll() -> List["EmploymentStatus"]:
        return [EmploymentStatus.AnsatMedLoen, EmploymentStatus.Orlov]


def ensure_list(element):
    if not isinstance(element, list):
        return [element]
    return element


# We will get to the Pydantic models later...
def read_employment_at(
    effective_date: datetime.date,
    settings: Settings,
    inst_id: str,
    employment_id: Optional[str] = None,
    status_active_indicator: bool = True,
    status_passive_indicator: bool = True,
    dry_run: bool = False,
) -> Union[OrderedDict, List[OrderedDict], None]:
    url = "GetEmployment20111201"
    params = {
        "EffectiveDate": effective_date.strftime("%d.%m.%Y"),
        "StatusActiveIndicator": str(status_active_indicator).lower(),
        "StatusPassiveIndicator": str(status_passive_indicator).lower(),
        "DepartmentIndicator": "true",
        "EmploymentStatusIndicator": "true",
        "ProfessionIndicator": "true",
        "WorkingTimeIndicator": "true",
        "UUIDIndicator": "true",
        "SalaryAgreementIndicator": "false",
        "SalaryCodeGroupIndicator": "false",
    }

    if employment_id:
        params.update({"EmploymentIdentifier": employment_id})

    request_uuid = uuid.uuid4()
    logger.info("read_employment_at", request_uuid=request_uuid)
    response = sd_lookup(
        url,
        settings=settings,
        institution_identifier=inst_id,
        params=params,
        request_uuid=request_uuid,
        dry_run=dry_run,
    )
    return response.get("Person")
