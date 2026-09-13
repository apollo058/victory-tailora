# Tailora Inspector 보안 가이드

Tailora Inspector는 개발 중인 앱의 요청 경로, 오류 요약, SQL 형태를 보여주는 진단
도구입니다. 기본적으로 비활성이며 사용자가 `enabled=True`를 명시한 경우에만
수집기, Inspector API, 독립형 화면, Swagger plugin이 함께 활성화됩니다.

## 접근 제어

로컬이 아닌 공유 환경에서는 `access_check`를 반드시 설정하십시오. hook은 FastAPI
`Request`를 받고 bool을 반환하는 동기 또는 비동기 함수입니다. `False`, hook 예외,
bool이 아닌 반환값은 모두 접근 거부로 처리됩니다. hook이 발생시킨 401과 403의
상태 코드는 유지되지만 응답 문구는 안전한 공통 문구로 바뀌니다.

Inspector API, health, UI, 정적 자산은 모두 같은 접근 정책을 사용합니다. Swagger
문서 요청이 거부되면 기본 API Docs는 유지하고 Inspector plugin만 노출하지
않습니다.

## production 보호

production에서는 다음 두 설정을 모두 지정해야 활성화됩니다.

```python
enable_inspector(
    app,
    enabled=True,
    environment="production",
    allow_in_production=True,
    access_check=check_inspector_access,
)
```

`allow_in_production`은 인증 기능이 아닙니다. production에서 Inspector를 켜려면
`access_check`도 반드시 제공해야 하며, 외부 네트워크에 열려 있는 서버에서는
사내망·VPN·방화벽 정책도 함께 적용하십시오. 환경 이름은 실수를 줄이는 보조
설정이며 네트워크 보안 경계가 아닙니다.

## 수집하지 않는 데이터

Tailora는 요청 본문, 응답 본문, SQLAlchemy parameters, 인증 헤더와 쿠키의
원문을 이벤트로 저장하지 않습니다. SQL literal과 오류 요약은 저장 전에 마스킹되고
API 응답 직전에 다시 마스킹됩니다. 라우트가 없는 요청은 실제 경로를 저장하지 않으며,
Inspector 데이터 응답에는 `Cache-Control: no-store`가 적용됩니다. 설정·인증·수집
실패 로그에는 SQL, token, 요청 값, 예외 원문을 남기지 않습니다.

## 경로와 origin

Inspector UI와 API는 호스트 앱과 같은 origin의 `path_prefix` 아래에서 제공됩니다.
Tailora는 CORS를 자동으로 넓히지 않습니다. 외부 origin 접근이 필요하면 호스트
앱에서 허용 origin을 구체적으로 제한하고 인증 hook을 함께 적용하십시오.

Swagger UI core 자산은 고정 버전 CDN URL과 SRI 무결성 검사를 사용합니다. CDN이
차단되거나 자산 검증에 실패하면 API Docs 대신 안전한 안내를 표시합니다. 완전한
오프라인 Swagger 자산 번들링은 현재 지원 범위에 포함되지 않습니다.

## 자원 한도

Ring Buffer 용량, 요청당 쿼리 수, SQL·오류·경로·헤더·파라미터 길이,
API 목록·집계 결과 수에 상한이 있습니다. 쿼리가 잘리면 API는 전체 실행 수,
분석한 쿼리 수, `is_queries_truncated`를 함께 반환합니다.

## 예제와 릴리스 경계

`examples/fastapi`는 로컬에서만 실행하는 가짜 데이터 예제이며 인증이나 네트워크
보호를 제공하지 않습니다. PyPI에는 `tailora` 라이브러리와 Inspector UI asset만
배포하고 예제·테스트·로컬 데이터베이스 파일은 배포하지 않습니다. 지원 범위는
Python 3.10 이상, FastAPI 0.115 이상 1 미만, SQLAlchemy 2 이상 3 미만이며,
현재 공식 프레임워크 지원은 FastAPI입니다.

pre-release 후보를 실제 환경에 설치하기 전에는 clean environment에서 wheel과
source distribution을 검사하십시오. 취약점이나 민감정보 노출을 발견하면 공개
issue에 비밀값을 올리지 말고 저장소의 보안 연락 경로를 이용하십시오.
