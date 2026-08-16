# Examples

The FastAPI example is currently a small runnable app used to verify the project setup.

```bash
python -m uvicorn examples.fastapi.app:app --reload
```

Open `http://127.0.0.1:8000/health` and check that it returns `{"status":"ok"}`.

The Inspector is not connected yet. Django Ninja and Inspector-specific examples will be added after the core event model is designed.

