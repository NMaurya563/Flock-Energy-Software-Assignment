"""Normalize observed export fields without inferring missing source values."""

from pydantic import ValidationError

from app.domain.constants import LEVELS
from app.schemas.meter import HierarchyEntry, Location, Meter


def normalize_meter(raw: object) -> Meter:
    if not isinstance(raw, dict):
        raise ValueError("Invalid meter record")
    warnings: list[str] = []
    location = None
    geo = raw.get("geo")
    if geo is None:
        geo = {}
    if not isinstance(geo, dict):
        geo = {}
        warnings.append("Malformed coordinates omitted.")
    try:
        if geo.get("lat") is not None and geo.get("lng") is not None:
            location = Location(latitude=geo["lat"], longitude=geo["lng"])
    except ValidationError:
        warnings.append("Invalid coordinates omitted.")
    hierarchy = raw.get("hierarchy")
    if hierarchy is None:
        hierarchy = {}
    if not isinstance(hierarchy, dict):
        raise ValueError("Malformed hierarchy")
    for level in LEVELS:
        if level in hierarchy and not isinstance(hierarchy[level], dict):
            warnings.append(f"Malformed {level} hierarchy entry omitted.")
    return Meter(
        meter_id=raw["meterId"],
        serial_number=raw.get("serialNo"),
        make=raw.get("make"),
        phase=raw.get("phaseType"),
        status=raw.get("installStatus"),
        installation_type=raw.get("installType"),
        transformer_code=raw.get("dtCode"),
        location=location,
        warnings=warnings,
        hierarchy=[
            HierarchyEntry(level=level, code=hierarchy[level].get("code"), name=hierarchy[level].get("name"))
            for level in LEVELS
            if isinstance(hierarchy.get(level), dict)
        ],
    )
