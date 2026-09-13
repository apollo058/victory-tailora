# 예제

FastAPI 예제는 SQLite와 SQLAlchemy를 사용해 요청, SQL, 오류, threshold signal을
확인하는 작은 실행 앱입니다.

```bash
python -m uvicorn examples.fastapi.app:app --reload
```

`http://127.0.0.1:8000/docs`를 열고 API Docs와 Inspector 탭을 확인하십시오.
`GET /health`는 정상 요청을, `GET /users/{user_id}`는 SQLite 쿼리를 보여줍니다.
`/users/repeat/1`, `/slow`, `/slow-query`, `/secret-query`,
`/secret-error?token=demo-secret`, `/db-error`로 반복 쿼리, 느린 요청·쿼리,
오류와 redaction을 재현할 수 있습니다.

예제는 로컬 개발용 가짜 데이터만 사용하며 PyPI `tailora` 패키지에는 포함되지
않습니다. 자세한 설치와 보안 경계는 [quickstart](../docs/quickstart.md)와
[보안 가이드](../docs/security.md)를 참고하십시오.

Django Ninja 어댑터와 완성된 배포 예제는 현재 범위에 포함되지 않습니다.
