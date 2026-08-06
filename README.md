# Victory Tailora

Victory Tailora is a highly personalized SaaS workspace where people can choose the features they need and arrange them into their own working environment.

Instead of forcing every user into the same dashboard, the product is designed around configurable modules. A user can select the tools that matter to them, place those tools where they want them, and evolve their workspace as their priorities change.

## Project direction

- Let users choose the modules they need.
- Let users arrange and reorder modules on a personal workspace.
- Keep the product extensible so new modules can be added without redesigning the whole application.
- Support a future SaaS model with accounts, teams, permissions, subscriptions, and reusable workspace templates.

## Technology

- **Backend:** Django, Django Ninja, SQLite for local development
- **Frontend:** React, TypeScript, Vite
- **Local orchestration:** Docker Compose

## Repository layout

```text
backend/   Django project and Django Ninja API
frontend/  React + TypeScript client
```

## Local development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API is available at `http://localhost:8000/api/` and the health check is at `http://localhost:8000/api/health`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend is available at `http://localhost:5173`.

### Docker Compose

```bash
docker compose up --build
```

## API overview

- `GET /api/health` - service health check
- `GET /api/modules` - available workspace modules
- `GET /api/layouts` - saved workspace layouts
- `POST /api/layouts` - save a workspace layout

This repository is an early foundation for the product. Authentication, billing, multi-tenancy, persistent user ownership, and production infrastructure are intentionally left for the next iterations.

