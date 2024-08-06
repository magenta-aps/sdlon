from datetime import date

from sdclient.client import SDClient
from sdclient.requests import GetEmploymentChangedRequest
from sdclient.requests import GetEmploymentRequest
from sdclient.responses import GetEmploymentChangedResponse
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

    def get_sd_employments_changed(
        self,
        activation_date: date,
        deactivation_date: date,
        cpr: str | None = None,
        employment_identifier: str | None = None,
        department_identifier: str | None = None,
        department_level_identifier: str | None = None,
    ) -> GetEmploymentChangedResponse:
        """
        Get SD "employments changed" from SD via the GetEmploymentChanged
        endpoint.

        Args:
            activation_date: SDs ActivationDate
            deactivation_date: SDs DeactivationDate
            cpr: CPR-number of the employee
            employment_identifier: SDs EmploymentIdentifier
            department_identifier: SDs DepartmentIdentifier
            department_level_identifier: SDs DepartmentLevelIdentifier

        Returns:
            The SD employments
        """

        sd_employments = self.client.get_employment_changed(
            GetEmploymentChangedRequest(
                InstitutionIdentifier=self.institution_identifier,
                PersonCivilRegistrationIdentifier=cpr,
                EmploymentIdentifier=employment_identifier,
                DepartmentIdentifier=department_identifier,
                DepartmentLevelIdentifier=department_level_identifier,
                ActivationDate=activation_date,
                DeactivationDate=deactivation_date,
                DepartmentIndicator=True,
                EmploymentStatusIndicator=True,
                ProfessionIndicator=True,
                UUIDIndicator=True,
            )
        )
        return sd_employments
