# 변경 기록

이 파일은 릴리스별 사용자 영향과 호환성 변경을 기록합니다.

## Unreleased — 2026-10-13 security review

- 환경을 생략한 Inspector 활성화는 인증을 요구합니다. 인증 없는 로컬 사용은
  `environment="development"`를 명시하고 loopback client/Host로 접속해야 합니다.
- SQL 인용·중첩 주석·유니코드 dollar quote·확장 숫자 표현의 값 노출을 수정하고,
  모호한 SQL mode와 미지원 방언의 원문은 보관하지 않습니다.
- SQL 원문 처리에 65,536자 상한을 적용하고 요청 쿼리 한도 이후에는 원문 처리를
  생략합니다. SQLAlchemy 측정 상태에 SQL 원문을 추가 보관하지 않습니다.
- Inspector 문자열 렌더링을 escape하고 CSP와 동일 origin 프레임 제한을 적용합니다.
- Swagger UI는 SRI와 함께 5.33.2로 갱신합니다. 외부 validator, query 설정 덮어쓰기,
  인증값의 영구 저장을 비활성화합니다.
- 최소 의존성은 FastAPI 0.135, Starlette 1.3.1, SQLAlchemy 2.0.31, pytest 9.0.3으로
  올립니다. 보안 검사 extra와 반복 검사 workflow를 추가합니다.
- Swagger 번들의 전체 의존성 검증은 아직 통과하지 않았습니다.
  [보안 검사 보고서](docs/security-audit.md)의 남은 항목을 릴리스 전에 확인해야 합니다.

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
