# This script adds or re-opens the terminated engagements described
# in Redmine case #61415.

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import click
from sdclient.responses import Employment, EmploymentWithLists

from sdlon.sd import SD


def get_emp_status_timeline(
    employment: Employment,
    employment_changed: EmploymentWithLists
) -> EmploymentWithLists:
    # TODO: for now, we only handle EmploymentStatus. In the future we
    #       should also handle Profession and EmploymentDepartment

    # The EmploymentIdentifiers must match
    assert employment.EmploymentIdentifier == employment_changed.EmploymentIdentifier

    emp_timeline = EmploymentWithLists(
        EmploymentIdentifier=employment.EmploymentIdentifier,
        EmploymentDate=employment.EmploymentDate,
        AnniversaryDate=employment.AnniversaryDate,
        EmploymentStatus=[employment.EmploymentStatus] + employment_changed.EmploymentStatus
    )

    if len(emp_timeline.EmploymentStatus) <= 1:
        return emp_timeline

    # Make sure there are no holes in the timeline
    activation_dates = (
        emp_status.ActivationDate
        for emp_status in emp_timeline.EmploymentStatus[1:]
    )
    deactivation_dates = (
        emp_status.DeactivationDate
        for emp_status in emp_timeline.EmploymentStatus[:-1]
    )
    date_pairs = zip(activation_dates, deactivation_dates)
    assert all(
        deactivation_date + timedelta(days=1) == activation_date
        for activation_date, deactivation_date in date_pairs
    )

    return emp_timeline
