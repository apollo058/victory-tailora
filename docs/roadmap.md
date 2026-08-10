# Roadmap

The roadmap is intentionally staged so that implementation begins only after the product boundaries are clear.

## Phase 0 — Idea and architecture

- Confirm product name and package name.
- Confirm `/swagger` integration behavior.
- Decide the first supported database and ORM combinations.
- Define event schema, redaction rules, and storage limits.
- Decide whether the project is one package with extras or several packages.

## Phase 1 — Core capture prototype

- Define request and query event models.
- Add a bounded in-memory store.
- Add request correlation and timing.
- Add query normalization and aggregation.
- Add unit tests for redaction, eviction, and aggregation.

## Phase 2 — Framework adapters

- Add Django Ninja adapter.
- Add FastAPI adapter.
- Add database integration tests.
- Add a minimal example for each framework.

## Phase 3 — Swagger Inspector UI

- Add the Inspector tab through a Swagger UI plugin.
- Show recent requests and request details.
- Show SQL queries, timings, and counts.
- Add slow-query and duplicate-query indicators.
- Verify that the original API Docs experience remains intact.

## Phase 4 — Packaging and public release

- Finalize package metadata and license.
- Publish an initial pre-release to PyPI.
- Add installation and framework quickstarts.
- Add compatibility testing for supported framework and Swagger UI versions.
- Publish a security and privacy guide.

## Later possibilities

- N+1 detection heuristics.
- Optional `EXPLAIN` execution.
- SSE live updates.
- Sampling controls and route filters.
- OpenTelemetry export.
- Shared storage for multi-worker development environments.
- Additional Python frameworks.

