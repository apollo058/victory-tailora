# Product Idea

## Working title

**OpenAPI Dev Inspector** is the current product description. `Victory Tailora` remains the repository codename until the package name and public branding are decided.

## Problem

During API development, a developer often needs more than the response body and status code. They need to understand the path from an endpoint to the database:

```text
API request → route handler → database queries → response
```

Printing SQL to a terminal is useful, but it loses request context. A full observability stack is powerful, but it can be too much for a small local project or an early debugging session.

## Proposed solution

Add a lightweight development inspector to the Swagger UI that is already open while testing an API.

The Inspector should show recent requests, request timing, query count, total database time, individual SQL statements, repeated query patterns, and basic slow-query signals. It should use local memory by default and require no external service.

## Why Swagger UI is the right surface

- It is already the developer's API testing surface.
- The selected operation and request context are naturally related to diagnostics.
- A separate dashboard URL creates unnecessary context switching.
- Swagger UI supports plugins and custom layouts, so the project can extend the page without maintaining a fork.

## Core questions the product should answer

1. Which API operation was executed?
2. How long did the request take?
3. How many database queries were executed?
4. What percentage of request time was spent in the database?
5. Which query was slowest?
6. Which normalized query occurred most often?
7. Are there repeated queries that suggest N+1 behavior?

## Open questions

- Should the first release use `/swagger` as the canonical route, or integrate with the framework's configured docs URL?
- Should the Inspector tab appear only when explicitly enabled, or whenever `DEBUG` is true?
- Which SQL backends should be supported first: SQLite and PostgreSQL, or database-agnostic hooks only?
- Should query parameters be displayed at all, or always redacted by default?
- Should the event buffer be process-local only, or optionally shared across workers?
- Should the initial package name be `openapi-dev-inspector`, `api-dev-inspector`, or another name?
- Should the project provide one package with optional extras or separate adapter packages?

