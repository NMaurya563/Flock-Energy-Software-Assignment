"""Timestamp parsing and Decimal register deltas, independent of transport."""

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.core.exceptions import PortalError
from app.domain.constants import INDIA
from app.schemas.consumption import Consumption, Reading


def normalize_readings(
    rows: object, meter_id: str, start: datetime | None, end: datetime | None, *, historical: bool
) -> Consumption:
    readings: list[Reading] = []
    warnings: list[str] = []
    if not isinstance(rows, list):
        raise PortalError("invalid_upstream_response", "Portal readings were malformed.")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            warnings.append(f"Row {index}: malformed record; omitted.")
            continue
        try:
            timestamp = datetime.strptime(row["timestamp"], "%d/%m/%Y %H:%M").replace(tzinfo=INDIA)
        except (KeyError, TypeError, ValueError):
            warnings.append(f"Row {index}: invalid timestamp; omitted.")
            continue
        if (start and timestamp < start) or (end and timestamp > end):
            continue
        values: dict[str, Decimal | None] = {}
        for source, field in (("kwh", "kwh"), ("kvah", "kvah"), ("voltR", "voltage_r")):
            value = row.get(source)
            try:
                if value in (None, "", "—", "-"):
                    values[field] = None
                    warnings.append(f"Row {index}: missing {source}; returned null.")
                    continue
                values[field] = Decimal(str(value))
                if not values[field].is_finite():
                    raise InvalidOperation()
            except InvalidOperation:
                values[field] = None
                warnings.append(f"Row {index}: invalid {source}; returned null.")
        readings.append(Reading(timestamp=timestamp, **values))
    readings.sort(key=lambda reading: reading.timestamp)
    occurrences = Counter(row.timestamp for row in readings)
    for previous, current in zip(readings, readings[1:]):
        if occurrences[previous.timestamp] > 1 or occurrences[current.timestamp] > 1:
            warnings.append("Duplicate reading timestamp; interval consumption omitted.")
            continue
        if previous.kwh is not None and current.kwh is not None:
            delta = current.kwh - previous.kwh
            if delta < 0:
                warnings.append("Cumulative register decreased; interval consumption omitted.")
            else:
                current.consumption_kwh = delta
    note = "Cumulative readings; timestamps use assumed Asia/Kolkata. " + (
        "Historical window fetched from portal; exact inclusive boundaries applied locally."
        if historical
        else "Portal default window; supply both start and end for historical retrieval."
    )
    return Consumption(meter_id=meter_id, data=readings, total=len(readings), warnings=warnings, note=note)
