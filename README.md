# Connector Context Backend

> Make any app searchable - Universal search and agent integration engine.

**Connector Context Backend** is a high-performance Python search and data synchronization engine designed to connect external productivity data sources (like Notion, Slack, and GitHub) to modern vector databases (such as Qdrant and Vespa) and LLM applications. 

It provides the necessary pipelines to ingest, clean, chunk, embed, and index content asynchronously using reliable Temporal-based background workers.

---

## Key Features

- 🚀 **FastAPI Engine:** Fully asynchronous HTTP service with request logging, validation, timeout, rate-limiting, and error-handling middlewares.
- 🔄 **Temporal Workflows:** Industrial-grade asynchronous task queues and workflow orchestrations to execute, cancel, and schedule complex sync runs.
- 🔌 **Extensible Sources & Destinations:**
  - **Sources:** Notion, Slack, GitHub, local files, and more.
  - **Destinations:** Vespa, Qdrant, and standard relational stores.
- 🧠 **Dynamic Embedder Framework:** Supports OpenAI, Mistral, Anthropic, Cohere, Cerebras, Together, Groq, and local FastEmbed embeddings.
- ⚡ **Domain-Driven Architecture:** Clean segregation of business domains (`domains/`) from infrastructural details (`adapters/`) using abstract Protocols (`core/protocols/`).
- 📢 **In-Process Event Bus:** Decoupled event publishing and subscribing to handle side effects like webhooks (via Svix) and analytics (via PostHog) cleanly.

---

## Architecture Overview

The backend is structured according to **Clean Architecture** patterns to enforce testability and separation of concerns:

```
backend/connector_context/
├── api/                  # HTTP Layer - thin routing, middleware, and API dependencies
├── core/                 # Cross-cutting concerns (Config, Container DI, Protocols, Events)
├── domains/              # Core Business Logic (source_connections, sync, billing, search, webhooks)
│   └── */operations.py   # Domain operations
│   └── */tests/          # Colocated unit and integration tests
├── adapters/             # Infrastructure Adapters (Temporal, Stripe, Redis, Storage)
├── platform/             # Source/Destination/Embedder implementations
└── db/                   # Database Layer (SQLAlchemy models, Alembic migrations, Repositories)
```

For a comprehensive explanation of the backend redesign, see [connector_context/architecture-refactor.md](file:///d:/Personal/Projects/backend/connector_context/architecture-refactor.md).

---

## Tech Stack & Dependencies

- **Runtime:** Python 3.13+
- **Framework:** FastAPI
- **Database ORM:** SQLAlchemy (Asyncio) with PostgreSQL (`asyncpg`)
- **Task Queue:** Temporal Engine (`temporalio`)
- **Package Manager:** Poetry
- **Linter & Formatter:** Ruff, Black, and isort

---

## Local Development Setup

### 1. Prerequisites

Make sure you have the following installed on your machine:
- Python 3.13+
- Poetry
- Docker & Docker Compose (for running PostgreSQL, Temporal, Qdrant, and Redis locally)

### 2. Installation

Clone the repository and install the dependencies using Poetry:

```bash
# Navigate to the backend directory
cd backend

# Install project dependencies
poetry install
```

### 3. Environment Configuration

Copy the example environment file and configure the values to match your local setup:

```bash
cp .env.example .env
```

### 4. Running Database Migrations

Apply Alembic migrations to set up your database schema:

```bash
poetry run alembic upgrade head
```

### 5. Running the Application

Start the FastAPI application in development mode:

```bash
poetry run uvicorn connector_context.main:app --reload --port 8000
```

The interactive API documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Testing

The project uses `pytest` for testing. Tests are colocated within their respective domains and adapters under `tests/` directories.

To run the full test suite:

```bash
poetry run pytest
```

To run a specific test suite or domain tests:

```bash
poetry run pytest connector_context/domains/source_connections/tests/
```

We also run type-checking (`mypy`) and linting (`ruff`):

```bash
# Lint check
poetry run ruff check .

# Code formatting check
poetry run black --check .

# Type checking
poetry run mypy .
```

---

## License

This project is proprietary and confidential. All rights reserved.
