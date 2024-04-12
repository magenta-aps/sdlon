from pathlib import Path

from lxml import etree


def get_xml_payload(file: Path) -> str:
    with open(file) as f:
        root = etree.parse(f)
    return etree.tostring(root).decode("utf-8")
