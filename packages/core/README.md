# Core

The core package contains framework-neutral request and query event models.

## Current implementation

- `tailora.core.events.RequestEvent` represents one HTTP request.
- `tailora.core.events.QueryEvent` represents one SQL execution.
- `tailora.core.events.ErrorSummary` stores a safe error summary.
- Query count and total query time are calculated from the query list.
- Event fields validate IDs, timestamps, durations, HTTP status codes, and query order.
- `tailora.core.serialization` converts events to and from JSON-compatible data.

The models do not import FastAPI or SQLAlchemy. Redaction, storage, aggregation, and
framework adapters will be added in later steps.
