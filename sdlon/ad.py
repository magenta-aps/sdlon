import requests


class LdapADGUIDReader:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def read_user(self, cpr: str) -> dict[str, str]:
        """
        Get the ADGUID via the LDAP integration. For now, we will return a dictionary
        to be compatible with the old integration to the AD.

        Args:
             cpr: The CPR of the person to get the AD info from

        Returns:
            Dictionary containing the ADGUID of the AD person.
        """

        # No error handling - if this fails, we will fail hard.
        r = requests.get(
            f"http://{self.host}:{self.port}/SD", params={"cpr_number": cpr}
        )

        return {"ObjectGuid": r.json().get("uuid")}
