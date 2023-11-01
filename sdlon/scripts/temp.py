from datetime import datetime

import click
from sdclient.client import SDClient
from sdclient.requests import GetEmploymentRequest


@click.command()
@click.option(
    "--username",
    "username",
    type=click.STRING,
    envvar="SD_USER",
    # required=True,
    help="SD username"
)
@click.option(
    "--password",
    "password",
    type=click.STRING,
    envvar="SD_PASSWORD",
    # required=True,
    help="SD password"
)
@click.option(
    "--institution-identifier",
    "institution_identifier",
    type=click.STRING,
    envvar="SD_INSTITUTION_IDENTIFIER",
    # required=True,
    help="SD institution identifier"
)
@click.option(
    "--cpr",
    help="Only run script for this CPR"
)
def main(
        username: str,
        password: str,
        institution_identifier: str,
        cpr: str,
):
    sd_client = SDClient(username, password)
    sd_employments = sd_client.get_employment(
        GetEmploymentRequest(
            InstitutionIdentifier=institution_identifier,
            PersonCivilRegistrationIdentifier=cpr,
            EmploymentIdentifier="12345",
            EffectiveDate=datetime.now().date(),
            EmploymentStatusIndicator=True,
        )
    )
    print(sd_employments)


if __name__ == "__main__":
    main()
