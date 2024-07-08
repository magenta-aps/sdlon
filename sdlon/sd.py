from datetime import date

from sdclient.client import SDClient
from sdclient.requests import GetEmploymentRequest
from sdclient.responses import GetEmploymentResponse


class SD:
    def __init__(self, username: str, password: str, institution_identifier: str):
        self.institution_identifier = institution_identifier
        self.client = SDClient(username, password)

    def get_sd_employments(
        self,
        effective_date: date,
        cpr: str | None = None,
        employment_identifier: str | None = None,
        status_active_indicator: bool = True,
        status_passive_indicator: bool = False,
    ) -> GetEmploymentResponse:
        """
        Get SD employments from SD.

        Args:
            effective_date: the SD effective date
            cpr: CPR-number of the employee
            employment_identifier: SDs EmploymentIdentifier
            status_active_indicator: if True, get active engagements
            status_passive_indicator: if True, get passive engagements

        Returns:
            The SD employments
        """

        sd_employments = self.client.get_employment(
            GetEmploymentRequest(
                InstitutionIdentifier=self.institution_identifier,
                EffectiveDate=effective_date,
                PersonCivilRegistrationIdentifier=cpr,
                EmploymentIdentifier=employment_identifier,
                StatusActiveIndicator=status_active_indicator,
                StatusPassiveIndicator=status_passive_indicator,
                EmploymentStatusIndicator=True,
                DepartmentIndicator=True,
                UUIDIndicator=True,
            )
        )
        return sd_employments
