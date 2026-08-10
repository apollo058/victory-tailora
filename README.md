# Victory Tailora — OpenAPI Dev Inspector

Victory Tailora is the working codename for an open-source development inspector for Python APIs.

The project aims to make request and database behavior visible while developing with FastAPI and Django Ninja. It is designed for the moment before a team needs Sentry, Grafana, Jaeger, or a full observability stack: install a package, enable one setting, open the existing Swagger UI, and inspect what happened during an API call.

## Current status

This repository is in the idea and architecture planning stage. Runtime logging, the Swagger integration, and the PyPI package have not been implemented yet.

There is intentionally no runnable product application in the repository yet. Implementation will begin after the product boundaries and event model are settled.

## Product idea

When a developer calls an endpoint from Swagger UI, the Inspector should make it easy to answer:

- How long did the request take?
- Which SQL queries were executed?
- How long did each query take?
- How many queries did this endpoint trigger?
- Which query patterns are repeated most often?
- Is this request showing a likely N+1 pattern?
- Which endpoints and queries are the slowest during the current development session?

## Intended experience

The developer should keep using one URL:

```text
/swagger

[ API Docs ] [ Inspector ]
```

The API documentation remains Swagger UI. Inspector is an additional tab supplied through the Swagger UI plugin and custom layout extension points. The project should not fork or modify Swagger UI core.

## Target users

- Python developers building APIs with FastAPI or Django Ninja.
- Small teams that need quick local visibility before adopting an observability platform.
- Open-source projects that want useful development diagnostics without external services.
- Developers investigating slow endpoints, excessive queries, or N+1 behavior.

## Design principles

1. **Development first** — disabled by default outside local development.
2. **Zero infrastructure** — no database, collector, Grafana, or hosted account required for the basic experience.
3. **One-screen diagnosis** — connect a request to its queries without copying logs between tools.
4. **Framework adapters** — share one event model while keeping FastAPI, Django Ninja, and database integrations separate.
5. **Safe defaults** — redact secrets and query parameters, cap memory usage, and avoid response-body capture by default.
6. **Optional depth** — start with request and SQL timing; add stack traces, EXPLAIN, sampling, and OpenTelemetry export later.

## Planned repository shape

```text
packages/
├── core/                    Shared event model, storage, aggregation, and redaction
├── adapters/
│   ├── django_ninja/        Django request and database integration
│   └── fastapi/             ASGI request and SQLAlchemy/DB integration
└── swagger_ui_plugin/       Inspector tab and Swagger UI integration

examples/
├── django_ninja/            Minimal example application
└── fastapi/                 Minimal example application

docs/
├── idea.md                  Product scope and open questions
├── architecture.md         Runtime and package architecture
└── roadmap.md               Staged implementation plan

```

## Planned installation experience

The exact package name is intentionally still open. The intended experience is approximately:

```bash
pip install <package-name>
```

```python
from dev_inspector import enable_inspector

enable_inspector(app)
```

Then the developer opens the host application's configured Swagger page and selects the Inspector tab. The UI is served as part of the Swagger UI integration; it is not a separate frontend application.

## Planned first release

- FastAPI and Django Ninja adapters.
- Request method, route, status, and duration.
- SQL statement, normalized fingerprint, duration, and count.
- Recent-request in-memory ring buffer.
- Request detail view with its related queries.
- Slow-request and slow-query thresholds.
- Query aggregation and duplicate-query hints.
- Swagger UI tab integration without forking Swagger UI.
- Local-only enablement and secret redaction.

## Explicit non-goals for the first release

- Replacing Sentry, Grafana, Jaeger, or OpenTelemetry.
- Long-term production telemetry storage.
- Full distributed tracing.
- Capturing arbitrary request or response bodies by default.
- Supporting every Python web framework on day one.

## Documentation

- [Product idea and open questions](docs/idea.md)
- [Architecture proposal](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
