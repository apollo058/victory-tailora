# 보안 검사 기록 — 2026-10-13

**현재 판정: 프로젝트 코드에서 재현한 문제는 수정했지만, 전체 릴리스 보안 검사는
통과하지 않았습니다.** Swagger UI 번들의 전체 의존성 버전을 확정할 자료가
불완전하고, upstream lockfile에서 `qs` advisory 두 개가 확인됩니다. 실제 배포
번들의 해당 버전과 공격 가능성은 미확정입니다. 이를 취약점 없음으로 표시하거나
검사 경고를 무시해서는 안 됩니다.

## 검사 범위와 방법

- `src/tailora`의 설정, FastAPI 등록·인증·라우팅·미들웨어, SQLAlchemy 수집기,
  이벤트·저장소·분석·직렬화, UI loader와 JavaScript를 읽었습니다.
- 인증 hook의 동기/비동기 실행, `False`·예외·잘못된 반환값, API와 정적 자산의
  인증 적용, 경로 인코딩과 잘못된 query 입력으로 인증을 우회하는지 검사했습니다.
- 실제 SQLite 실행 결과와 SQL·fingerprint의 마스킹 결과를 비교했습니다.
  250개의 생성된 SQLite 문자열 조합과 DB별 공격 입력으로 값 노출을 검사했습니다.
- 실제 Chromium에서 Inspector HTML 삽입, inline script 차단, Swagger의 외부
  schema 및 validator 지정, API Docs와 Inspector의 정상 사용을 검사했습니다.
- Bandit, Ruff, pip-audit, OSV, upstream npm lockfile audit를 사용했습니다.
  Python 의존성은 최신 설치와 새 최소 지원 버전 조합을 별도로 검사했습니다.
- Swagger CDN 파일의 SHA-384를 직접 계산해 SRI와 비교하고, JavaScript에 실제로
  포함된 DOMPurify 버전, 공개 source map과 upstream lockfile을 대조했습니다.
- Git 이력의 관련 소스 객체 245개에서 private key, AWS access key, GitHub token,
  JWT, OpenAI key 형식을 검색했습니다. 비밀값 자체를 출력하지 않았습니다.

검사는 Python 3.13의 격리된 가상 환경에서 수행했습니다. 실제 운영 서버의 프록시,
방화벽, CORS, 인증 공급자, 사용자 권한 설정은 이 저장소에 없어 검증하지 않았습니다.
공개 advisory 데이터베이스와 형식 기반 비밀키 검사는 알려지지 않은 취약점이나
임의 형식의 비밀값까지 보장하지 않습니다.

## 발견한 문제와 수정

| 항목 | 근거와 영향 | 적용한 수정 |
| --- | --- | --- |
| SQL 문자열 값 노출 | SQLite의 `'prefix\\' || 'tailora-secret'`는 유효한 쿼리입니다. 기존 scanner가 백슬래시를 quote escape로 오해해 `tailora-secret`를 저장했습니다. Oracle의 내부 apostrophe가 있는 q/nq 인용문도 값 일부를 노출했습니다. | 방언별 quote 해석과 Oracle 구분자 처리를 추가했습니다. PostgreSQL/MySQL의 접속별 SQL mode 때문에 해석이 모호한 백슬래시 문자열은 SQL과 fingerprint를 버립니다. |
| SQL 주석·숫자 값 노출 | PostgreSQL/SQL Server 중첩 주석의 첫 `*/` 이후, 유니코드 dollar quote, `987654321e5`와 `0xABCDEF`가 기존 마스킹을 통과했습니다. | 중첩 주석, 유니코드 태그, 지수·진법·숫자 구분자 표현을 처리합니다. 미지원 방언은 원문을 저장하지 않습니다. |
| 환경 누락 시 인증 없는 활성화 | `enable_inspector(app, enabled=True)`의 환경 기본값이 `development`여서 운영 앱에서도 별도 인증·production 확인 없이 등록할 수 있었습니다. | 기본값을 `unspecified`로 바꾸고 환경 누락 시 인증 설정을 요구합니다. `prod_...`, `production_...`도 production 확인 대상으로 처리합니다. |
| 인증 없는 로컬 Inspector의 외부 노출 | 로컬 설정의 Inspector는 네트워크 client와 Host를 제한하지 않았습니다. 외부 바인딩, DNS rebinding, 호스트 앱의 넓은 CORS를 이용하는 웹사이트에서 진단 정보를 읽을 위험이 있었습니다. | 인증 없는 사용은 loopback client와 localhost/loopback Host를 함께 요구합니다. 다른 Origin·cross-site 요청도 거부합니다. 중복 Host와 직접 전달한 forwarding 헤더로는 통과하지 않습니다. 인증한 공유 사용은 허용합니다. |
| 오래된 Swagger 구성요소 | 기존 Swagger UI 5.17.14의 실제 번들에는 DOMPurify 3.1.4가 있었습니다. OSV에서 이 버전에 대한 advisory 21개가 반환됐습니다. 이것이 앱에서 21개의 독립된 공격이 성공한다는 의미는 아닙니다. | Swagger UI 5.33.2로 갱신하고 JS·CSS SRI를 다시 계산했습니다. 실제 DOMPurify 3.4.16에 대한 당시 OSV 결과는 advisory 0개였습니다. 외부 validator와 URL query의 설정 덮어쓰기도 끕니다. |
| 취약한 최소 의존성 | FastAPI 0.115.0의 허용 범위는 Starlette 0.38.6을 설치했습니다. 해당 버전에 여러 DoS·URL 처리 advisory가 있었습니다. 개발 extra의 pytest 8.x 범위도 취약한 임시 디렉터리 처리를 수정한 버전을 설치하지 못했습니다. | FastAPI ≥0.135, Starlette ≥1.3.1, pytest ≥9.0.3, pytest-asyncio ≥1.3으로 변경했습니다. pip도 검사 환경과 설치 안내에서 ≥26.2.1로 갱신했습니다. |
| SQL 처리 자원 제한 부족 | SQL 길이는 전체 문자열을 처리한 뒤에만 잘렸고, 요청 쿼리 보관 한도 후에도 SQL 마스킹을 계속했습니다. 실행 context에는 원문 SQL을 추가 보관했습니다. | SQL scanner 진입 전 65,536자 상한을 적용하고 한도 초과는 버립니다. 쿼리 보관 한도 이후에는 원문 처리를 생략합니다. 측정 상태에는 시간만 보관하고 실행 후 제거합니다. |
| UI의 일부 문자열 escape 누락 | 요청 method를 HTML과 class 속성에 직접 넣었고, loader를 직접 호출하면 base_path가 HTML 속성을 탈출할 수 있었습니다. 정상 HTTP parser를 통한 외부 공격은 재현하지 않았습니다. | 두 문자열을 escape했습니다. Inspector에는 외부 스크립트만 허용하는 CSP, nosniff, 동일 origin 프레임 제한, referrer 제한을 추가했습니다. |

관련 구현: [privacy.py](../src/tailora/core/privacy.py),
[security.py](../src/tailora/adapters/fastapi/security.py),
[config.py](../src/tailora/config.py),
[sqlalchemy.py](../src/tailora/adapters/fastapi/sqlalchemy.py),
[docs.py](../src/tailora/adapters/fastapi/docs.py),
[api.py](../src/tailora/adapters/fastapi/api.py).

최소 조합 검증에서는 SQLAlchemy 2.0.0이 Python 3.13에서 import되지 않는 호환성
문제도 발견했습니다. 보안 취약점으로 분류하지 않았으며, Python 3.13 지원이
추가된 2.0.31을 최소 버전으로 정하고 해당 조합을 실행했습니다.

## 검증 결과

| 검사 | 결과 |
| --- | --- |
| 수정 전 단위·통합 테스트 | 327 passed. 기존 테스트만으로는 위 SQL 값 노출이 발견되지 않았습니다. |
| 수정 후 최신 의존성의 단위·통합 테스트 | 384 passed. wheel·sdist 및 checkout 외부 설치 검사 포함. |
| 새 최소 조합의 단위·통합 테스트 | 382 passed, 2 skipped. release 도구가 없는 최소 환경에서 패키징 관련 검사 두 개는 생략됐습니다. 최신 환경에서는 실행됐습니다. |
| Chromium | 9 passed. HTML 공격값, CSP, 외부 schema/validator 덮어쓰기 방어 포함. |
| 최신 환경의 전체 최종 실행 | **393 passed**, 3개의 upstream deprecation warning. |
| 최신 설치 Python advisory 검사 | 78 package entries, 알려진 advisory 0개. PyPI에 없는 로컬 `tailora`는 자동 검사 대상에서 제외됐으며 소스 검토와 회귀 테스트로 검사했습니다. |
| 새 최소 조합 Python advisory 검사 | 알려진 advisory 0개. |
| Bandit | 중간·높음 등급 0개. 낮음 B110 경고 6개는 SQL 수집기가 호스트 DB 실행을 방해하지 않도록 예외를 삼키는 경로입니다. 원문 예외를 출력하지 않으며 `nosec`으로 숨기지 않았습니다. |
| Ruff | 통과. |
| Git 이력 비밀키 형식 검색 | 245 source objects, 해당 형식의 후보 0개. |
| Swagger SRI | 고정한 JS·CSS 파일 모두 SHA-384 일치. |
| Swagger 전체 의존성 검사 | **실패: 버전 목록 불완전 및 upstream advisory 후보.** |

새 최소 조합: FastAPI 0.135.0, Starlette 1.3.1, SQLAlchemy 2.0.31,
pytest 9.0.3, pytest-asyncio 1.3.0. 최신 조합에서는 FastAPI 0.143.0,
Starlette 1.7.0, SQLAlchemy 2.1.4, pytest 9.1.1을 사용했습니다.

## 남은 릴리스 차단 항목

Swagger 5.33.2의 upstream lockfile로 추론한 `qs` 6.15.2에는 다음 advisory가
있습니다. 두 advisory의 수정 버전은 6.16.0입니다.

- [GHSA-4mjr-xmp4-gh2g: attacker controlled isBuffer를 통한 DoS](https://github.com/ljharb/qs/security/advisories/GHSA-4mjr-xmp4-gh2g)
- [GHSA-x5fp-wj9c-mxmx: bracket-key comma parsing의 array limit 우회](https://github.com/ljharb/qs/security/advisories/GHSA-x5fp-wj9c-mxmx)

동시에 공개 source map에는 `@braintree/sanitize-url`, `redux-immutable`,
`stampit`, `traverse` 파일이 있지만 같은 릴리스의 upstream lockfile에서 정확한
버전을 연결하지 못했습니다. 따라서 lockfile의 `qs` 버전이 배포 번들에 그대로
포함됐다고 단정할 수 없고, 배포 번들의 모든 의존성이 안전하다고 확인할 수도
없습니다. 이 부분은 **확정된 앱 취약점이 아닌 검증 미완료 상태**입니다.

Upstream npm lockfile audit는 `sprintf-js`의 DoS advisory를 `argparse`와
`remarkable`에도 전파해 세 개의 moderate dependency 경고를 냈습니다.
`argparse`와 `sprintf-js`는 공개 browser source map에 나타나지 않았습니다.
이 경고를 곧바로 브라우저 공격 성공으로 계산하지 않았으며, 그 부재만으로
전체 번들의 안전성이 확인된 것으로 처리하지도 않았습니다.

릴리스 전에는 배포 자산과 연결되는 정확한 SBOM 또는 재현 가능한 빌드로
위 버전을 확인해야 합니다. 취약한 버전이 실제 포함되면 패치된 의존성으로
만든 자산으로 교체하고 SRI와 브라우저 호환성을 다시 검증해야 합니다.
경고를 ignore 목록에 넣어서 검사만 통과시키는 방식은 적용하지 않았습니다.

[브라우저 의존성 검사](../scripts/check_swagger_security.py)는 advisory 후보나
버전 미확인 모듈이 있으면 종료 코드 1을 반환합니다. 같은 검사를 push,
pull request와 주간 workflow에 추가했으므로 현재 security job은 통과하지
않는 상태가 예상됩니다. [상세 자산 검사 결과](security-audit-assets.json)에는
버전 추론의 한계와 미확인 모듈을 함께 저장했습니다.

## 호환성 변경과 재검사

로컬 개발 예제는 다음처럼 환경을 명시해야 합니다.

```python
enable_inspector(app, enabled=True, environment="development")
```

외부 공유 환경은 권한을 확인하는 `access_check` 또는 거부 시 예외를 발생시키는
인증 dependency가 필요합니다. production에는 `environment="production"`과
`allow_in_production=True`도 필요합니다. 인증 없는 로컬 모드에 외부 프록시
도메인으로 접속하는 기존 사용은 거부되므로 공유 환경에서는 인증을 설정해야 합니다.
Inspector 권한은 해당 프로세스의 전체 진단 정보를 볼 수 있는 관리자 권한으로
취급해야 합니다. 앱의 일반 사용자 인증만 확인하는 hook은 충분하지 않을 수 있습니다.

```bash
python -m pip install --upgrade "pip>=26.2.1"
python -m pip install -e ".[dev,fastapi,example,release,security]"
python -m pytest -q
ruff check .
bandit -r src -ll
python -m pip_audit
python scripts/check_swagger_security.py
```

검토와 수정은 로컬 작업 파일에 반영했습니다. 배포·PyPI 업로드·GitHub release는
수행하지 않았습니다.

## 공개 근거

- [PostgreSQL SQL lexical structure](https://www.postgresql.org/docs/current/sql-syntax-lexical.html): 인용과 SQL mode의 차이, dollar quote, 중첩 주석.
- [Oracle alternative quoting](https://download.oracle.com/oll/tutorials/SQLInjection/html/lesson1/les01_tm_ovw0.htm): 문자열에 apostrophe를 포함하는 대체 구분자.
- [DOMPurify security advisories](https://github.com/cure53/DOMPurify/security/advisories): sanitizer 취약점과 패치 이력.
- [pytest 9.0.3 release](https://github.com/pytest-dev/pytest/releases/tag/9.0.3): CVE-2025-71176 수정.
- [SQLAlchemy 2.0.31 release](https://www.sqlalchemy.org/blog/2024/06/18/sqlalchemy-2.0.31-released/): Python 3.13 지원.
- [Starlette advisories](https://github.com/encode/starlette/security/advisories): 의존성 최소 버전 재검토의 근거.
- [OSV API](https://api.osv.dev/v1/querybatch): 실제 검사 시 사용한 공개 advisory 서비스.
