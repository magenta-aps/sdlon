from unittest.mock import MagicMock
from unittest.mock import patch

from sdlon.ad import LdapADGUIDReader


@patch("sdlon.ad.requests.get")
def test_ldap_adguid_reader(mock_get: MagicMock):
    # Arrange
    reader = LdapADGUIDReader("hostname", 1234)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "dn": "uid=bruce,ou=os2mo,o=magenta,dc=magenta,dc=dk",
        "uuid": "c04d7ec7-1364-4d98-9ad4-4dddabe703b4",
        "username": "bruce",
    }
    mock_get.return_value = mock_response

    # Act
    adguid_dict = reader.read_user("1212121234")

    # Assert
    mock_get.assert_called_once_with(
        "http://hostname:1234/SD",
        params={"cpr_number": "1212121234"},
    )
    assert adguid_dict == {"ObjectGuid": "c04d7ec7-1364-4d98-9ad4-4dddabe703b4"}


@patch("sdlon.ad.requests.get")
def test_ldap_adguid_reader_case_where_user_not_found(mock_get: MagicMock):
    # Arrange
    reader = LdapADGUIDReader("hostname", 1234)

    mock_response = MagicMock()
    mock_response.json.return_value = {"detail": "No DNs found for CPR number"}
    mock_get.return_value = mock_response

    # Act
    adguid_dict = reader.read_user("1212121234")

    # Assert
    mock_get.assert_called_once_with(
        "http://hostname:1234/SD",
        params={"cpr_number": "1212121234"},
    )
    assert adguid_dict == {"ObjectGuid": None}
