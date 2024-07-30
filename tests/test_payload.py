from sdlon.payload import get_sd_persons


def test_get_sd_persons():
    # Arrange
    payload = """<?xml version="1.0" encoding="UTF-8" ?>
      <GetEmploymentChangedAtDate20111201 creationDateTime="2023-11-23T17:01:42">
        <RequestStructure>
          <InstitutionIdentifier>XY</InstitutionIdentifier>
          <ActivationDate>2023-11-23</ActivationDate>
          <ActivationTime>12:00:00</ActivationTime>
          <DeactivationDate>2023-11-23</DeactivationDate>
          <DeactivationTime>16:01:59</DeactivationTime>
          <DepartmentIndicator>true</DepartmentIndicator>
          <EmploymentStatusIndicator>true</EmploymentStatusIndicator>
          <ProfessionIndicator>true</ProfessionIndicator>
          <SalaryAgreementIndicator>false</SalaryAgreementIndicator>
          <SalaryCodeGroupIndicator>false</SalaryCodeGroupIndicator>
          <WorkingTimeIndicator>true</WorkingTimeIndicator>
          <UUIDIndicator>true</UUIDIndicator>
          <FutureInformationIndicator>true</FutureInformationIndicator>
        </RequestStructure>
        <Person>
          <PersonCivilRegistrationIdentifier>1212121000</PersonCivilRegistrationIdentifier>
          <Employment>
            <EmploymentIdentifier>12345</EmploymentIdentifier>
            <EmploymentStatus changedAtDate="2023-11-23">
              <ActivationDate>2024-04-01</ActivationDate>
              <DeactivationDate>9999-12-31</DeactivationDate>
              <EmploymentStatusCode>8</EmploymentStatusCode>
            </EmploymentStatus>
          </Employment>
        </Person>
        <Person>
          <PersonCivilRegistrationIdentifier>2212221000</PersonCivilRegistrationIdentifier>
          <Employment>
            <EmploymentIdentifier>54321</EmploymentIdentifier>
            <EmploymentStatus changedAtDate="2023-11-23">
              <ActivationDate>2024-04-01</ActivationDate>
              <DeactivationDate>9999-12-31</DeactivationDate>
              <EmploymentStatusCode>8</EmploymentStatusCode>
            </EmploymentStatus>
          </Employment>
        </Person>
      </GetEmploymentChangedAtDate20111201>
    """

    # Act
    persons = get_sd_persons(payload, "1212121000")

    # Assert
    assert len(persons) == 1
    assert persons[0].find("Employment").find("EmploymentIdentifier").text == "12345"
