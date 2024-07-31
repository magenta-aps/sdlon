# This script adds or re-opens the terminated engagements described
# in Redmine case #61415.
from datetime import timedelta

from sdclient.responses import Employment
from sdclient.responses import EmploymentWithLists
from sdclient.responses import GetEmploymentChangedResponse
from sdclient.responses import GetEmploymentResponse


def get_emp_status_timeline(
    employment: Employment, employment_changed: EmploymentWithLists | None
) -> EmploymentWithLists:
    # TODO: for now, we only handle EmploymentStatus. In the future we
    #       should also handle Profession and EmploymentDepartment

    # The EmploymentIdentifiers must match
    if employment_changed is not None:
        assert (
            employment.EmploymentIdentifier == employment_changed.EmploymentIdentifier
        )

    future_emp_statuses = (
        employment_changed.EmploymentStatus if employment_changed is not None else []
    )
    emp_timeline = EmploymentWithLists(
        EmploymentIdentifier=employment.EmploymentIdentifier,
        EmploymentDate=employment.EmploymentDate,
        AnniversaryDate=employment.AnniversaryDate,
        EmploymentStatus=[employment.EmploymentStatus] + future_emp_statuses,
    )

    if len(emp_timeline.EmploymentStatus) <= 1:
        return emp_timeline

    # Make sure there are no holes in the timeline, i.e. we make sure that
    # the DeactivationDate for EmploymentStatus object number n is exactly
    # one day earlier than the ActivationDate for EmploymentStatus object
    # number n + 1
    activation_dates = (
        emp_status.ActivationDate for emp_status in emp_timeline.EmploymentStatus[1:]
    )
    deactivation_dates = (
        emp_status.DeactivationDate for emp_status in emp_timeline.EmploymentStatus[:-1]
    )
    date_pairs = zip(activation_dates, deactivation_dates)
    assert all(
        deactivation_date + timedelta(days=1) == activation_date
        for activation_date, deactivation_date in date_pairs
    )

    return emp_timeline


def get_sd_employment_map(
    sd_employments: GetEmploymentResponse,
    sd_employments_changed: GetEmploymentChangedResponse,
) -> dict[tuple[str, str], EmploymentWithLists]:
    """
    Get a map from (cpr, EmploymentIdentifier) to the corresponding employment
    status timeline.

    Args:
        sd_employments: the response from SD GetEmployment
        sd_employments_changed: the response from SD GetEmploymentChanged

    Returns:
        map from (cpr, EmploymentIdentifier) to the corresponding employment
        status timeline.
    """

    def get_map(
        sd_emp: GetEmploymentResponse | GetEmploymentChangedResponse,
    ) -> dict[tuple[str, str], Employment | EmploymentWithLists]:
        return {
            (person.PersonCivilRegistrationIdentifier, emp.EmploymentIdentifier): emp
            for person in sd_emp.Person
            for emp in person.Employment
        }

    sd_emp_map = get_map(sd_employments)
    sd_emp_changed_map = get_map(sd_employments_changed)

    return {
        key: get_emp_status_timeline(emp, sd_emp_changed_map.get(key))
        for key, emp in sd_emp_map.items()
    }
