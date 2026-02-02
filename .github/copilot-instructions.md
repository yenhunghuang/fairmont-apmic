```markdown
# Copilot Instructions for fairmont-apmic

## Tech Stack & Architecture

- **Language:** Python 3.11+
- **Frameworks:** FastAPI (API), Uvicorn (ASGI server)
- **Database:** SQLite (local, checkpointed pipeline)
- **PDF Parsing:** pdfplumber, PyMuPDF
- **LLM Integration:** openai, httpx
- **Excel/YAML:** openpyxl, PyYAML
- **Testing:** pytest, pytest-asyncio, pytest-cov
- **Linting/Formatting:** black, ruff

## Key Directories & Files

- `src/` — Main source code
  - `api/` — FastAPI endpoints (`main.py`, `routes/`)
  - `services/` — Pipeline, adapters, cache, PDF parser, LLM client
  - `models/` — Entities, schemas, database models
  - `utils/` — Item/fabric normalization, logging
- `tests/` — Unit and integration tests
- `docs/` — Specs, API reference, output format
- `specs/` — Feature specs, data models, checklists
- `configs/` — Supplier configs
- `requirements.txt` — Python dependencies
- `pyproject.toml` — Tool configs (black, ruff)
- `.env.example` — Environment variable template
- `CLAUDE.md` — Project architecture and conventions

## Build, Test, and Lint Commands

```sh
# Install dependencies
pip install -r requirements.txt

# Run dev server
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_pipeline.py -v

# Run tests by name
pytest -k "test_normalization" -v

# Coverage report
pytest --cov=src --cov-report=html

# Format code
black src tests
ruff check src tests --fix
```

## Project Conventions

- **Pipeline:** 7-stage PDF processing, checkpointed in SQLite (`src/services/pipeline.py`)
- **Adapters:** Vendor-specific logic in `src/services/adapters/`
- **Testing:** Uses temporary SQLite DB, fixtures in `tests/conftest.py`
- **Environment:** Set variables as per `.env.example`
- **Output:** 17-field JSON, spec in `docs/EXCEL_OUTPUT_SPECIFICATION.md`
- **Refer to `CLAUDE.md` for detailed architecture, conventions, and field mapping.**

## Contribution Tips

- Follow black/ruff for style.
- Add/modify tests for new features.
- Update documentation/specs for API/data changes.
```