# STEP 12 개발 계획 — FastAPI 예제와 릴리스 준비

## 기준과 목적

- 기준 브랜치: `origin/main`
- 기준 커밋: `e262e74` (`feat: Inspector 설정 및 접근 제어 보안 강화 (#12)`)
- 작업 브랜치: `feature/step12-plan`
- 관련 문서: [빠른 시작](quickstart.md), [보안 가이드](security.md)

STEP 11까지 구현된 FastAPI Inspector를 새 환경에서도 재현할 수 있도록 예제 앱,
quickstart 문서, 패키지 산출물, clean environment 검증, pre-release 준비를 하나의
세로 흐름으로 완성합니다. 이번 단계에서는 기존 Inspector 기능을 크게 확장하기보다
설치부터 Swagger Inspector에서 진단 결과를 확인하는 경로를 안정화합니다.

## 1. 현재 `main` 기준 상태

| 영역 | 현재 상태 | STEP 12에서 확인·보완할 내용 |
| --- | --- | --- |
| FastAPI 예제 | `examples/fastapi/app.py`에 health와 SQLite 사용자 조회가 있습니다. | 정상·반복·느린 요청·HTTP/SQL 실패 시나리오를 추가합니다. |
| SQLAlchemy | SQLite `StaticPool`과 `check_same_thread=False`를 사용합니다. | 새 환경에서 설치 후 실제 쿼리 이벤트가 연결되는지 검증합니다. |
| Inspector | `enabled=True`일 때 middleware, API, Swagger 탭이 함께 켜집니다. | 예제에서 설정 의도와 접근 경계를 명확히 보여줍니다. |
| 테스트 | unit·integration·browser 테스트와 예제 smoke 테스트가 있습니다. | 릴리스 시나리오와 패키지 내용 검사를 추가합니다. |
| 패키지 | `tailora` 패키지와 `fastapi`, `sqlalchemy` extra가 정의되어 있습니다. | wheel·sdist 내용, metadata, 선택 의존성을 검증합니다. |
| 문서 | README와 보안 가이드가 있습니다. | 설치 직후 실행할 quickstart와 지원 범위를 정리합니다. |
| 배포 | 버전은 `0.1.0.dev0`이고 build·twine 도구가 고정되어 있지 않습니다. | 첫 pre-release 후보, tag, changelog, 배포 검증 절차를 준비합니다. |

현재 저장소에는 `CHANGELOG.md`, `LICENSE`, `docs/quickstart.md`가 없으므로 릴리스
작업에서 새로 만들 대상입니다. 예제는 현재 인메모리 SQLite를 사용하므로 별도 DB
서버 없이 재현할 수 있으며, 파일 기반 DB를 추가하는 경우에도 생성 파일은 반드시
Git에서 제외해야 합니다.

## 2. 이번 단계의 고정 결정

### 포함합니다

- PyPI에는 `tailora` 라이브러리만 배포하고 `examples/`는 저장소 샘플로 유지합니다.
- 공식 예제 조합은 Python `>=3.10`, FastAPI `>=0.115,<1`, SQLAlchemy `>=2,<3`,
  SQLite, Swagger UI `5.17.14`로 고정합니다.
- 예제 앱은 기존 `enable_inspector(app, ..., enabled=True)` 흐름을 유지합니다.
- 모든 샘플 값은 가짜 데이터로 만들고, request body·SQL parameters·credential은
  수집하지 않습니다.
- `python -m build`, `twine check`, 전체 테스트, Ruff, 브라우저 검증을 완료 조건으로
  사용합니다.
- 첫 공개 버전은 pre-release 후보로 준비하되, 실제 PyPI 업로드는 별도 배포 승인과
  인증 정보가 준비된 뒤 실행합니다.

### 이번에는 하지 않습니다

- Django Ninja와 추가 데이터베이스 조합의 공식 지원
- 장기 telemetry, 운영 서버 공개, 공유 저장소
- 완전한 N+1 탐지와 `EXPLAIN` 자동 실행
- 예제 코드를 `tailora` public API로 포함하는 패키징
- 검증하지 않은 Python·FastAPI·SQLAlchemy·Swagger UI 버전 조합의 지원 선언

## 3. 구현 작업

### 12.1 FastAPI 예제 앱 완성

대상 파일:

- `examples/fastapi/app.py`
- `examples/fastapi/README.md`
- `tests/integration/test_fastapi_example.py`

작업 내용:

- 기존 health 요청과 단일 사용자 조회를 유지합니다.
- 같은 fingerprint가 반복되는 endpoint를 추가해 duplicate signal을 재현합니다.
- threshold를 넘는 지연 요청과 느린 쿼리 시나리오를 결정적인 시간으로 구성합니다.
- HTTP 오류와 실패 SQL endpoint를 추가해 ErrorSummary와 원래 예외 흐름을 확인합니다.
- 가짜 token·SQL literal·오류 경로를 사용해 화면과 저장 이벤트의 redaction을 확인합니다.
- 초기화 코드는 import와 테스트 반복 실행에 안전하게 만들고, SQLite 산출물은
  생성하지 않거나 `.gitignore`로 보호합니다.

완료 조건:

- `python -m uvicorn examples.fastapi.app:app`으로 별도 수동 설정 없이 시작됩니다.
- 각 시나리오에서 route, status, query count/time, signal, error가 예상한 값으로
  저장됩니다.
- 예제 자체가 실제 패키지 API와 문서에 없는 내부 구현에 의존하지 않습니다.

### 12.2 진단 시나리오와 테스트 데이터 고정

대상 파일:

- `tests/integration/test_fastapi_example.py`
- `tests/integration/test_fastapi_capture.py`
- `tests/integration/test_inspector_signals.py`
- `tests/browser/test_swagger_inspector_integration.py`

작업 내용:

- 정상 요청, 여러 SQL, 반복 fingerprint, 느린 요청, 느린 쿼리, HTTP 오류, DB 오류를
  각각 독립 테스트로 만듭니다.
- 성공·실패·취소에 가까운 예외 흐름에서 원래 HTTP 응답 또는 예외 전달이 유지되는지
  확인합니다.
- 민감 값이 API 응답, 저장소 snapshot, 브라우저 화면, 로그에 남지 않는지 검사합니다.
- 테스트 간 저장소와 예제 모듈 상태가 격리되도록 fixture를 정리합니다.

완료 조건:

- 시나리오 테스트가 실행 순서에 의존하지 않습니다.
- 브라우저에서 API Docs의 Try it out 결과와 Inspector 탭의 요청 상세가 같은 요청을
  가리킵니다.

### 12.3 Quickstart와 사용 문서 정리

대상 파일:

- `README.md`
- `docs/quickstart.md` (신규)
- `examples/README.md`
- `examples/fastapi/README.md`
- `docs/security.md`

작업 내용:

- Python 지원 버전, 운영체제 전제조건, 가상 환경 생성 명령을 기록합니다.
- editable install과 PyPI pre-release 설치를 서로 구분해 제공합니다.
- 다음 경로를 복사해 실행할 수 있게 문서화합니다.

  ```bash
  python -m venv .venv
  source .venv/bin/activate
  python -m pip install -e ".[dev,fastapi]"
  python -m uvicorn examples.fastapi.app:app --reload
  ```

- `/docs`, Inspector 탭, 각 예제 endpoint와 진단 확인 순서를 설명합니다.
- 기본 비활성화, `enabled=True`, production 이중 확인, 접근 hook, redaction 한계를
  보안 가이드와 연결합니다.
- 알려진 제한사항과 문제 보고·보안 취약점 제보 경로를 명시합니다.

완료 조건:

- 저장소 구조를 모두 읽지 않아도 README에서 첫 Inspector 화면까지 도달합니다.
- 문서의 명령, URL, extra 이름, 버전 범위가 실제 코드와 일치합니다.

### 12.4 패키지 metadata와 릴리스 도구 정리

대상 파일:

- `pyproject.toml`
- `LICENSE` (신규)
- `CHANGELOG.md` (신규)
- `tests/unit/test_package.py`
- `tests/integration/test_packaging.py` (신규)

작업 내용:

- 패키지 이름, 설명, Python 조건, license, README 링크와 버전 정책을 확인합니다.
- `fastapi`, `sqlalchemy`, 개발·릴리스 도구 extra의 역할을 분리합니다.
- `build`와 `twine`을 재현 가능한 release extra 또는 CI 도구로 고정합니다.
- wheel과 source distribution을 깨끗한 디렉터리에서 생성합니다.
- wheel 안에는 `tailora` 코드와 Inspector UI asset만 포함하고 `examples/`, 테스트,
  `.sqlite`, `.env`, build cache가 포함되지 않는지 `zipfile`/tar 검사로 확인합니다.
- `import tailora`와 package version이 metadata와 일치하는지 확인합니다.

완료 조건:

- `python -m build`가 wheel과 sdist를 모두 생성합니다.
- `python -m twine check dist/*`가 통과합니다.
- 설치된 wheel에서 FastAPI extra를 추가한 뒤 예제 import와 실행이 가능합니다.

### 12.5 Clean environment 설치 검증

대상 파일:

- `tests/integration/test_clean_install.py` (신규)
- `docs/quickstart.md`

작업 내용:

- 프로젝트 루트 밖의 임시 디렉터리에 새 virtual environment를 만듭니다.
- 생성한 wheel 또는 pre-release 파일을 설치하고 `import tailora`를 확인합니다.
- `fastapi`와 `sqlalchemy` extra 설치 후 예제 서버를 시작합니다.
- `/health`, 사용자 조회, `/docs`, Inspector health/API를 차례로 확인합니다.
- 설치에 필요한 문서 밖의 수동 파일 복사나 환경 변수 요구가 없는지 확인합니다.

완료 조건:

- 개발 checkout의 import 우선순위에 기대지 않고 설치된 package가 로드됩니다.
- 새 환경에서 README 명령만으로 예제의 첫 진단 흐름이 재현됩니다.

### 12.6 전체 품질·브라우저 검증

검증 명령:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
python -m build
python -m twine check dist/*
git diff --check
```

브라우저에서는 다음을 확인합니다.

- API Docs가 기본 선택 상태로 열립니다.
- Try it out 실행 결과가 Inspector 목록에 나타납니다.
- 요청 상세에서 SQL, duration, signal, 오류 요약을 확인할 수 있습니다.
- plugin asset 실패 시에도 API Docs가 유지됩니다.
- 좁은 viewport와 키보드 탭 이동에서도 두 화면을 사용할 수 있습니다.
- Inspector를 선택하기 전에는 불필요한 Inspector API 요청을 보내지 않습니다.

### 12.7 보안·릴리스 문서와 변경 기록

- `CHANGELOG.md`에 pre-release 범위, 호환성, 알려진 제한사항을 기록합니다.
- `docs/security.md`에 예제는 로컬 전용이며 production 보호를 대신하지 않는다는
  점을 명시합니다.
- SQL literal, query parameter, header, 오류 경로 redaction의 한계를 문서화합니다.
- 릴리스 전후에 secret, token, 실제 개인정보, 로컬 DB 파일이 commit·wheel·sdist에
  들어가지 않는지 확인합니다.

### 12.8 버전·tag·pre-release 배포 준비

- 현재 `0.1.0.dev0`를 첫 후보 버전(예: `0.1.0rc1`)으로 올릴지 구현 시작 전에
  결정하고, `pyproject.toml`, package version, changelog, Git tag를 일치시킵니다.
- 배포 전에는 반드시 clean environment 설치를 먼저 성공시킵니다.
- PyPI 업로드는 사용자의 명시적인 배포 승인과 저장소 인증 설정이 있을 때만 실행합니다.
- 업로드 후에는 PyPI 파일을 다시 설치해 wheel 검사와 quickstart를 반복합니다.
- 문제가 있으면 다음 patch pre-release로 되돌릴 수 있도록 tag와 changelog 절차를
  기록합니다.

### 12.9 최종 TDD·릴리스 체크리스트

- [ ] 예제 정상·실패·느린 요청·반복 쿼리가 재현됩니다.
- [ ] 요청·SQL·signal·오류 요약이 Inspector에서 연결됩니다.
- [ ] 비활성화·접근 거부·redaction 경계가 유지됩니다.
- [ ] unit·integration·browser 테스트가 통과합니다.
- [ ] Ruff와 `git diff --check`가 통과합니다.
- [ ] wheel·sdist와 metadata 검사가 통과합니다.
- [ ] clean environment에서 설치·import·예제 실행이 성공합니다.
- [ ] README와 quickstart의 명령·URL·버전 범위가 실제 동작과 일치합니다.
- [ ] build 결과, secret, token, 개인정보가 Git 상태와 배포 파일에 없습니다.
- [ ] changelog와 알려진 제한사항이 pre-release 기준으로 갱신됩니다.

## 4. 권장 구현 순서와 커밋 단위

1. `feat: complete FastAPI release example` — 예제 endpoint, 시나리오 fixture, smoke
   테스트를 함께 변경합니다.
2. `test: add packaging and clean-install checks` — wheel·sdist·metadata·clean
   environment 검증을 추가합니다.
3. `docs: add STEP12 quickstart and release guide` — README, quickstart, examples,
   security, changelog를 갱신합니다.
4. `chore: prepare first pre-release metadata` — 버전, release extra, tag 준비를
   별도 변경으로 분리합니다.

각 커밋은 관련 테스트가 통과하는 상태로 유지하며, PyPI 업로드나 GitHub release
생성은 코드·문서 검증이 끝난 뒤 별도 작업으로 진행합니다.

## 5. 최종 완료 조건

STEP 12는 다음 조건을 모두 만족할 때 완료로 판정합니다.

1. 새 환경에서 패키지 설치 후 FastAPI 예제를 실행할 수 있습니다.
2. README만 보고 `/docs`와 Swagger Inspector에서 요청·SQL·signal을 확인할 수
   있습니다.
3. 정상·실패·느린 요청·반복 쿼리와 민감 정보 보호 시나리오가 자동·브라우저 테스트로
   재현됩니다.

## 6. 구현 진행 상태

- [x] 12.1 FastAPI 예제 endpoint와 SQLite 진단 시나리오를 추가했습니다.
- [x] 12.2 정상·반복·느린 요청/쿼리·HTTP/DB 오류·redaction 통합 테스트를
  추가했습니다.
- [x] 12.3 README, quickstart, 예제 안내와 보안 경계를 갱신했습니다.
- [x] 12.4 `LICENSE`, `CHANGELOG.md`, release extra, wheel/sdist 경계 검사를
  추가했습니다.
- [x] 12.5 checkout 밖의 격리된 설치 대상에 wheel과 FastAPI·SQLAlchemy extra를
  설치하고 예제 서버, `/docs`, Inspector API를 확인했습니다.
- [x] 12.6 전체 pytest, Ruff, `git diff --check`, browser 통합 테스트를
  실행했습니다.
- [x] 12.7 pre-release 범위·호환성·제한사항과 보안 문서를 기록했습니다.
- [x] 12.8 버전을 `0.1.0rc1`로 맞추고 패키지 metadata 및 `twine check`를
  확인했습니다. 실제 PyPI 업로드와 Git tag 생성은 배포 승인 후 진행합니다.
- [x] 12.9 TDD 기준으로 실패 테스트를 먼저 확인한 뒤 구현하고 최종 회귀 검증을
  완료했습니다.
4. PyPI package와 GitHub `examples/`의 경계가 wheel·sdist 검사로 확인됩니다.
5. 지원 버전, 설치 방법, 보안 경계, 알려진 제한사항이 문서에 고정됩니다.
6. 테스트·lint·build·metadata·clean-install 검증이 모두 통과합니다.
7. pre-release 후보의 버전과 changelog가 서로 일치하며 Git tag는 배포 승인 후
   생성합니다.
