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

`allow_in_production`은 인증 기능이 아닙니다. 외부 네트워크에 열려 있는 서버에서는
`access_check`, 사내망·VPN, 방화벽 정책을 함께 적용하십시오. 환경 이름은 실수를
줄이는 보조 설정이며 네트워크 보안 경계가 아닙니다.

## 수집하지 않는 데이터

Tailora는 요청 본문, 응답 본문, SQLAlchemy parameters, 인증 헤더와 쿠키의
원문을 이벤트로 저장하지 않습니다. SQL literal과 오류 요약은 저장 전에 마스킹되고
API 응답 직전에 다시 마스킹됩니다. 설정·인증·수집 실패 로그에는 SQL,
token, 요청 값, 예외 원문을 남기지 않습니다.

## 경로와 origin

Inspector UI와 API는 호스트 앱과 같은 origin의 `path_prefix` 아래에서 제공됩니다.
Tailora는 CORS를 자동으로 넓히지 않습니다. 외부 origin 접근이 필요하면 호스트
앱에서 허용 origin을 구체적으로 제한하고 인증 hook을 함께 적용하십시오.

## 자원 한도

Ring Buffer 용량, 요청당 쿼리 수, SQL·오류·경로·헤더·파라미터 길이,
API 목록·집계 결과 수에 상한이 있습니다. 쿼리가 잘리면 API는 전체 실행 수,
분석한 쿼리 수, `is_queries_truncated`를 함께 반환합니다.
