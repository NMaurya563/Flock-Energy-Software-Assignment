"""Regenerate the public API contract from the application schemas."""

import json
from pathlib import Path

from app.main import app


def main() -> None:
    path = Path(__file__).resolve().parents[2] / "openapi.json"
    path.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
