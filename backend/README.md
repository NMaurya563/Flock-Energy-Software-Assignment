# Backend

Run commands from this directory. See the [root README](../README.md) for setup, API usage, and verification.

- [Folder guide and dependency boundaries](../docs/architecture.md)
- [Engineering decisions and trade-offs](../docs/decisions.md)
- [Verified upstream protocol](../PROTOCOL.md)

The entry point remains `uvicorn app.main:app`. HTTP routes are grouped in `app/api/v1/`, pure transformations in `app/domain/`, upstream access in `app/clients/`, orchestration in `app/services/`, and response contracts in `app/schemas/`.

Offline API integration tests use mocked upstream traffic; only the explicit smoke script contacts the live portal.
