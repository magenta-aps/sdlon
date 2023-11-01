import json


def print_json(d: list | dict) -> None:
    print(json.dumps(d, indent=2))
