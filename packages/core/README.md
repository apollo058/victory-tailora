# Core

The core package contains framework-neutral request and query event models.

## Current implementation

- `tailora.core.events.RequestEvent` represents one HTTP request.
- `tailora.core.events.QueryEvent` represents one SQL execution.
- `tailora.core.events.ErrorSummary` stores a safe error summary.
- Query count and total query time are calculated from the query list.
- Event fields validate IDs, timestamps, durations, HTTP status codes, and query order.
- `tailora.core.serialization` converts events to and from JSON-compatible data.
- `tailora.core.privacy.redact_event` removes sensitive query, fingerprint, and error values.
- Header and query-parameter helpers apply case-insensitive redaction and item limits.
- SQL literals, comments, and common quoted values are replaced before storage.
- Policy values validate count limits and cap text lengths.
- `tailora.core.store.RingBuffer` keeps recent events in bounded process-local memory.
- The store supports latest-first listing, request ID lookup, eviction, clearing, and snapshots.

The models, privacy helpers, and store do not import FastAPI or SQLAlchemy. Aggregation
and framework adapters will be added in later steps.
