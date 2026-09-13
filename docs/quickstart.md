# 빠른 시작

Tailora는 개발 중인 FastAPI 요청과 SQLAlchemy 쿼리를 같은 Swagger 화면에서
확인하는 개발용 Inspector입니다. 기본값은 비활성화되어 있으므로 앱에서
`enabled=True`를 명시해야 합니다.

## 전제조건

- Python 3.10 이상
- 로컬에서 명령을 실행할 수 있는 운영체제
- FastAPI 앱을 실행할 수 있는 가상 환경

## 저장소 예제를 실행하기

저장소를 받은 뒤 최상위 경로에서 다음 명령을 실행하십시오.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,fastapi]"
python -m uvicorn examples.fastapi.app:app --reload
```

Windows PowerShell에서는 가상 환경 활성화 명령만 다음과 같이 바꿉니다.

```powershell
.venv\Scripts\Activate.ps1
```

브라우저에서 <http://127.0.0.1:8000/docs>를 열면 API Docs와 Inspector 탭이
함께 표시됩니다. API Docs에서 `Try it out`을 실행한 뒤 Inspector 탭을 열면
같은 요청의 상태 코드, 처리 시간, SQL, signal을 확인할 수 있습니다.

## 예제 시나리오

| 요청 | 확인할 내용 |
| --- | --- |
| `GET /health` | 정상 요청과 요청 event |
| `GET /users/1` | SQLite SQL 한 건과 응답 연결 |
| `GET /users/repeat/1` | 같은 fingerprint의 `duplicate_query` |
| `GET /slow` | `slow_request` signal |
| `GET /slow-query` | `slow_query` signal |
| `GET /secret-query` | SQL literal redaction |
| `GET /secret-error?token=demo-secret` | 안전한 HTTP 오류 요약과 redaction |
| `GET /db-error` | 500 응답과 실패 QueryEvent |

`/docs`와 `/openapi.json`, `/__tailora/*` 내부 요청은 애플리케이션 진단
event에 포함되지 않습니다.

## PyPI 패키지를 앱에 설치하기

예제 모듈은 GitHub 저장소에만 포함되며 PyPI wheel에는 포함되지 않습니다. 자신의
FastAPI 앱에서는 다음처럼 패키지와 선택 의존성을 설치하십시오.

```bash
python -m pip install "tailora[fastapi,sqlalchemy]"
```

그리고 앱의 SQLAlchemy `Engine`을 연결합니다.

```python
from fastapi import FastAPI

from tailora.adapters.fastapi import enable_inspector

app = FastAPI()
enable_inspector(app, engine=engine, enabled=True)
```

이후 호스트 앱의 docs URL을 열고 Inspector 탭을 선택하십시오. 공유 개발 환경에서는
`access_check`를 설정하십시오. production에서는 `access_check`와 네트워크 제한을
적용하고 `allow_in_production=True`를 함께 지정해야 합니다. `enabled=True`만으로
인증이 추가되지는 않습니다.

## 개발 설치와 pre-release 설치 구분

저장소 예제를 수정하며 작업할 때는 editable install을 사용합니다.

```bash
python -m pip install -e ".[dev,fastapi]"
```

검증된 pre-release 후보를 설치할 때는 PyPI에서 별도로 설치합니다.

```bash
python -m pip install --pre "tailora[fastapi,sqlalchemy]==0.1.0rc1"
```

## 보안과 제한사항

Tailora는 요청·응답 본문, SQL parameters, 인증 헤더와 쿠키 원문을 저장하지
않습니다. SQL literal과 오류 요약도 저장·응답 직전에 마스킹합니다. Inspector는
프로세스 내부 메모리 링버퍼이므로 장기 보관이나 운영 모니터링을 대신하지
않습니다. 자세한 경계는 [보안 가이드](security.md)를 확인하십시오.

## 문제 보고와 릴리스 검증

재현 가능한 예제 요청, Python/FastAPI/SQLAlchemy 버전, 실패한 명령을 포함해
GitHub issue로 문제를 보고하십시오. 취약점은 공개 issue에 비밀값을 포함하지
말고 저장소의 보안 연락 경로를 이용하십시오.

릴리스 후보는 다음 검사를 통과한 뒤에만 배포 승인 대상으로 올립니다.

```bash
python -m pip install -e ".[dev,fastapi,release]"
python -m pytest -q
ruff check .
python -m build
python -m twine check dist/*
```
