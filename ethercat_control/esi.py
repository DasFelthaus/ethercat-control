"""Helpers around EtherCAT ESI files."""

from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET


class ESIInfo:
    def __init__(self, path: Path, product_code: Optional[int] = None, revision: Optional[int] = None):
        self.path = path
        self.product_code = product_code
        self.revision = revision


def parse_esi(path: Path) -> ESIInfo:
    """Lightweight ESI parser to grab product code/revision for logging."""

    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"ESI file not found: {path}")

    product_code = None
    revision = None
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        device = root.find(".//Devices/Device")
        if device is not None:
            type_tag = device.find("Type")
            if type_tag is not None:
                product = type_tag.get("ProductCode")
                revision_str = type_tag.get("RevisionNo")
                if product and product.startswith("#x"):
                    product_code = int(product.replace("#x", ""), 16)
                if revision_str and revision_str.startswith("#x"):
                    revision = int(revision_str.replace("#x", ""), 16)
    except ET.ParseError:
        # Keep best effort: just return with path
        pass
    return ESIInfo(path=path, product_code=product_code, revision=revision)


def ensure_esies_exist(paths: list[Path]) -> None:
    missing = [p for p in paths if not p.expanduser().resolve().exists()]
    if missing:
        joined = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(f"ESI file(s) not found: {joined}")
