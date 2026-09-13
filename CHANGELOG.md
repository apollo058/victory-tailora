# 변경 기록

이 파일은 릴리스별 사용자 영향과 호환성 변경을 기록합니다.

## 0.1.0rc1 — 2026-09-09

첫 번째 pre-release 후보입니다.

- FastAPI 요청·SQLAlchemy 쿼리·threshold 신호를 확인할 수 있는 실행 예제를
  제공합니다.
- `tailora[fastapi]`, `tailora[sqlalchemy]`, `tailora[dev]` extra를 제공합니다.
- wheel과 source distribution을 `tailora[release]`의 고정된 build·twine 도구로
  검증할 수 있습니다.
- 요청 본문, 응답 본문, SQL parameters, 인증 헤더와 쿠키 원문은 수집하지
  않습니다.

### 호환성

- Python 3.10 이상
- FastAPI 0.115 이상 1 미만
- SQLAlchemy 2 이상 3 미만
- SQLite 예제와 Swagger UI 5.17.14

### 알려진 제한사항

- Inspector 저장소는 프로세스 내부 메모리 링버퍼이며 장기 telemetry 저장소가
  아닙니다.
- 공식 quickstart는 FastAPI와 SQLAlchemy 조합만 다룹니다.
- 현재 공식 프레임워크 지원은 FastAPI이며 Django Ninja 어댑터는 아직 제공하지
  않습니다.
- Inspector를 production 인증·방화벽의 대체 수단으로 사용하면 안 됩니다.
- PyPI 업로드와 GitHub release 생성은 별도 배포 승인 후 진행합니다.
