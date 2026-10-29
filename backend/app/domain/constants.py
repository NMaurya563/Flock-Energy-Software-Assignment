from datetime import timedelta, timezone

LEVELS = ("zone", "circle", "division", "subdivision", "substation", "feeder", "dt")
# Upstream timestamps omit an offset; this assumption is documented in PROTOCOL.md.
INDIA = timezone(timedelta(hours=5, minutes=30))
