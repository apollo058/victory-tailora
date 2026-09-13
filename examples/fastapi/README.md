# FastAPI 예제

저장소 최상위 경로에서 다음 명령으로 예제를 실행하십시오.

```bash
python -m uvicorn examples.fastapi.app:app --reload
```

Inspector는 예제 코드의 `enabled=True`로 명시적으로 활성화됩니다. 예제는
`0.1.0rc1` 기준의 FastAPI·SQLAlchemy 조합을 사용합니다.
`http://127.0.0.1:8000/docs`에서 API Docs와 Inspector 탭을 사용할 수 있습니다.

- `GET /health`는 `{"status":"ok"}`를 반환합니다.
- `GET /users/{user_id}`는 SQLite 조회를 실행하므로 요청과 SQL 연결을
  Inspector에서 확인할 수 있습니다.
- `GET /users/repeat/1`은 동일 fingerprint의 반복 쿼리를 만듭니다.
- `GET /slow`와 `GET /slow-query`는 각각 느린 요청과 느린 쿼리 signal을 만듭니다.
- `GET /secret-query`는 SQL literal이 redaction되는 모습을 보여줍니다.
- `GET /secret-error?token=demo-secret`와 `GET /db-error`는 안전한 오류 요약을
  확인하는 시나리오입니다.

이 예제는 로컬 실행을 전제로 하며 `access_check`을 설정하지 않습니다. 공유
환경이나 production에서는 보안 가이드의 접근 제어를 먼저 적용하십시오.
