# Denne snurrebasse har til hensigt at rette op på manglende navn-komponenter
# efter identificering af en fejl i sd changed at, som bevirkede at personer, som
# havde ændret navn (men kun fornavn ELLER efternavn vill stå med en blank
# værdi i den del af navnet, der IKKE var blevet opdateret.
#
# angiv uuider for de berørte på kommandolinien
import datetime
import uuid

import click
from structlog.stdlib import get_logger

from .config import get_settings
from .sd_changed_at import ChangeAtSD
from .sd_common import sd_lookup


logger = get_logger()


def read_person(cat, cpr):
    params = {
        "EffectiveDate": cat.from_date.strftime("%d.%m.%Y"),
        "PersonCivilRegistrationIdentifier": cpr,
        "StatusActiveIndicator": "true",
        "StatusPassiveIndicator": "true",
        "ContactInformationIndicator": "false",
        "PostalAddressIndicator": "false",
    }
    url = "GetPerson20111201"
    request_uuid = uuid.uuid4()
    logger.info("read_person", request_uuid=request_uuid)
    response = sd_lookup(url, params=params, request_uuid=request_uuid, dry_run=True)
    person = response.get("Person", [])

    if not isinstance(person, list):
        person = [person]
    return person


@click.command()
@click.option("--uuid", type=click.UUID, required=True, multiple=True)
def cli(uuid):
    uuids = uuid
    settings = get_settings()
    settings.sd_use_ad_integration = False
    assert isinstance(settings.sd_institution_identifier, str)
    cat = ChangeAtSD(
        settings, settings.sd_institution_identifier, from_date=datetime.date.today()
    )
    mh = cat.helper
    for uuid in uuids:
        mh = cat.helper
        mouser = mh.read_user(uuid)
        if mouser is None:
            raise ValueError
        sdnow = read_person(cat, mouser["cpr_no"])
        if len(sdnow) > 1:
            print(sdnow)
        else:
            person = sdnow[0]
            given_name = person.get("PersonGivenName", mouser.get("givenname", ""))
            sur_name = person.get("PersonSurnameName", mouser.get("surname", ""))
            payload = {
                "uuid": uuid,
                "givenname": given_name,
                "surname": sur_name,
                "cpr_no": mouser["cpr_no"],
                "org": {"uuid": mouser["org"]["uuid"]},
            }

            print(payload)
            mh._mo_post("e/create", payload).json()


if __name__ == "__main__":
    cli()
