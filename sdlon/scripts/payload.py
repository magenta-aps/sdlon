from datetime import datetime

import click
from lxml import etree
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from db.engine import get_engine
from db.models import Payload

GET_EMPLOYMENT_CHANGED_AT_DATE = "https://service.sd.dk/sdws/GetEmploymentChangedAtDate20111201"


def get_payloads(engine: Engine, cpr: str) -> list[tuple[datetime, str]]:
    """
    Get payloads containing the CPR from the payload DB
    """
    stmt = select(
        Payload.timestamp, Payload.response
    ).where(
        Payload.response.contains(cpr),
        Payload.full_url == GET_EMPLOYMENT_CHANGED_AT_DATE
    )

    with Session(engine) as session:
        result = session.execute(stmt)

    return [(row[0], row[1]) for row in result]


def get_sd_persons(payload: str, cpr: str):
    """
    Convert payload string to XML object
    """
    root = etree.fromstring(payload.encode("utf-8"))

    persons = root.findall("Person")
    return [
        person for person in persons
        if person.find("PersonCivilRegistrationIdentifier").text.strip() == cpr
    ]


@click.command()
@click.option(
    "--cpr",
    required=True,
    help="CPR number of person to payloads for"
)
def main(cpr: str):
    engine = get_engine()

    payloads = get_payloads(engine, cpr)

    for timestamp, payload in payloads:
        print(f"---------- {timestamp.strftime('%Y-%m-%d')} ----------")
        persons = get_sd_persons(payload, cpr)
        for person in persons:
            output = etree.tostring(person, pretty_print=True)
            print(output.decode(), end="")


if __name__ == "__main__":
    main()
