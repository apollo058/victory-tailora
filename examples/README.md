# 예제

FastAPI 예제는 SQLite와 SQLAlchemy를 사용해 요청과 SQL 수집을 확인하는 작은
실행 앱입니다.

```bash
python -m uvicorn examples.fastapi.app:app --reload
```

`http://127.0.0.1:8000/docs`를 열고 API Docs와 Inspector 탭을 확인하십시오.
`GET /health`는 `{"status":"ok"}`를 반환하고, `GET /users/{user_id}`는
요청과 연결된 SQLite 쿼리를 실행합니다.

Django Ninja 어댑터와 완성된 배포 예제는 현재 범위에 포함되지 않습니다.
