# Repository Guidelines

## Project Structure & Module Organization
- `mlit_mcp/` Core code: `mcp_server.py` (FastMCP stdio server), `server.py` (FastAPI HTTP adapter for tests), `http_client.py`, `cache.py`, `settings.py`, and `tools/` (each tool implements Input/Response/Tool classes).
- `tests/` Pytest suite: unit tests under `tests/tools/`, E2E under `tests/e2e/`, load tests under `tests/load/`.
- `prompt/` Prompt specs and docs; `examples/` sample notebooks/scripts; `README.md` usage; `requirements.txt` deps.

## Build, Test, and Development Commands
- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Run MCP (stdio): `python -m mlit_mcp` (requires `MLIT_API_KEY` in `.env`).
- Run HTTP server (for local testing): `uvicorn mlit_mcp.server:app --reload`
- Test: `pytest`  | Coverage: `pytest --cov=mlit_mcp`
- Lint/format/type: `black .` | `flake8 mlit_mcp tests` | `mypy mlit_mcp`

## Coding Style & Naming Conventions
- Python 3.11+, 4‑space indent, type hints required. Format with Black (defaults).
- Modules/functions: `snake_case`. Classes and Pydantic models: `CamelCase`.
- Tool modules follow pattern: `FooTool`, `FooInput`, `FooResponse`; expose `descriptor()/invoke()/run()`.
- Pydantic fields use snake_case with JSON aliases (e.g., `fromYear`). Keep API names stable for MCP clients.

## Testing Guidelines
- Frameworks: `pytest`, `pytest-asyncio`, `pytest-httpx`.
- Naming: files `test_*.py`; structure mirrors `mlit_mcp/` (e.g., `tests/tools/test_*.py`).
- Avoid real API calls: set `MLIT_API_KEY` to a dummy and monkeypatch `MLITHttpClient.fetch`. Prefer async tests and deterministic fixtures.

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise subject, meaningful scope (e.g., `tools:` `server:`). Include rationale in body when non-trivial.
- PRs: clear description, linked issues, test plan (commands and expected output), and notes on API/CLI changes. Add/adjust tests and docs (`README.md`, this file) when adding tools or endpoints.

## Security & Configuration Tips
- Secrets: store `MLIT_API_KEY` in `.env` (dotenv is loaded). Never commit secrets.
- Large geodata: prefer MCP `resource://` URIs; do not embed large GeoJSON in code.
- Cache: temporary file cache under system temp (e.g., `mlit_mcp_cache/`). Use the `clear_cache` tool or delete files if needed.

