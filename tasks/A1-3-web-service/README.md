# A1-3 작업 기록 — MateAI 웹

서비스 설명과 실행·배포 방법은 [루트 README](../../README.md)에 있습니다. 서비스 코드도 저장소 루트에 있습니다
(Vercel이 루트를 배포하고 `tasks/`는 `.vercelignore`로 제외됩니다).
이 폴더는 **무엇을 왜 고쳤는지**와 제품 명세를 남기는 기록입니다.

- 제품 명세: [`SERVICE_PLAN.md`](SERVICE_PLAN.md)
- 배포: <https://mateai-web-jk4v-two.vercel.app>
- 회귀: `python3 -m unittest tests/test_web_regression.py` (외부 API 호출 없이 16개)

## 고친 것과 근거

| 문제 (재현) | 원인 | 수정 | 검증 |
|---|---|---|---|
| `cities: "abc"` → 500 서버 오류 | `int()` 변환 예외를 잡지 않음 | 정수 1~2만 허용, 아니면 400 `BAD_CITIES` | `test_travel_rejects_bad_types_without_server_error` |
| `cities: 5` → 조용히 2로 보정 | `min/max`로 값을 몰래 고침 | 범위 밖도 명시적 오류 | 같은 테스트 |
| JSON 배열 본문 → 500 | `body.get` 가정 | 객체가 아니면 `BAD_JSON` (chat·travel) | 같은 테스트 |
| AI 실패 시 폴백 리포트에 `One-Day Plan` 섹션 누락 | 폴백이 5개 섹션만 작성 | 6번째 섹션을 도시·검색 결과로 채움 | `test_fallback_report_keeps_all_six_sections` |
| 검사한 가게 0건인데 "근거 검사 통과" 표시 | 불일치 0건만 보고 통과로 판정 | "검사 대상 없음" 배지로 분리 | `test_frontend_does_not_call_zero_checks_a_pass` |
| **배포에서만** 대화가 500 `ValueError` | `providers._req`의 `urllib.request.Request()` 생성이 `try` 밖 → 스킴 없는 `LLM_BASE_URL`에서 예외가 턴 전체를 죽임 | `Request` 생성을 `try` 안으로, 빈 값은 기본값 사용 | `test_bad_llm_base_url_is_a_provider_error_not_a_crash` (수정 전 실패 확인) |
| AI 호출이 실패해도 고정 문구가 "AI API" 응답으로 표시 | 생성 결과와 무관하게 라벨 고정 | `generator` 상태(ok/no_key/failed)와 `ai_generated`·`provider` 추가 | `test_chat_failure_is_not_labelled_as_ai_success` |
| 배포에서 Gemini가 매번 HTTP 404 → OpenAI로 전환 | 빈 `GEMINI_MODEL`이면 URL이 `models/:generateContent`가 됨 (배포 값 미확인, 가설. 기본 모델 존재는 목록 조회로 확인) | 빈 모델명·URL은 기본값 사용 | `test_empty_model_env_uses_defaults`, 재배포 후 오류 0건 |
| 2순위 제공자로 넘어가 성공한 요청이 `partial`로 표시 | 폴백 기록도 실패로 계산 | `fell_back` 기록은 제외 | 배포 응답 `status: complete` 확인 |
| 대화가 매 턴 같은 말을 반복 | 대화 기록 없이 고정 기억 카드와 열차 사실을 매 턴 주입 | 역할 페르소나 + 최근 12턴 + 리포트 맥락으로 프롬프트 교체 | `test_chat_prompt_uses_history_and_trip_context`, 로컬 3턴 실호출 |
| 공개 URL에서 유료 API를 무제한 호출 가능 | 호출 제한 없음 | `api/_lib/budget.py`로 방문자별 빈도와 인스턴스 총량 제한, 429 응답 | `test_budget_blocks_bursts_and_caps_an_instance` 외 2개 |
| 로컬 서버가 호출 제한·오류 숨김을 건너뜀 | `devserver`가 `handle()`을 직접 호출 | `serve_request()` 한 경로로 통일 | `test_local_and_deployed_share_one_request_path`, `test_unexpected_errors_do_not_leak_internals` |
| 상한 0 설정에서 `IndexError` | 빈 큐의 첫 원소를 읽음 | 빈 큐면 창 전체를 대기 시간으로 사용 | `test_budget_handles_a_zero_limit_configuration` |

## 배포에서 실제로 확인한 것

2026-09-11 측정. 비로그인 `GET /` 200, 정적 경로 8개 200, `tasks/`와 `.env` 404.
입력 오류 3종 400(`BAD_CITIES`·`BAD_DATE`·`EMPTY_INPUT`), 안내 모드 200·LLM 0회,
대화 200·2.9초·`provider: openai`, 여행 리포트 200·7.6초·6개 섹션·Kakao 5건·근거 검사 5/5 일치,
개편 후 대화 200·0.6초·`provider: gemini`.

기존 Vercel 프로젝트 `mateai-web`·`mateai-web-hfni`는 배포가 계속 실패했고 **원인은 미확인**입니다
(빌드 로그 미열람). 현재 서비스는 새 프로젝트 `mateai-web-jk4v`에서 돌아갑니다.

## 남은 일

세션 인계와 다음 작업 제안은 운영 저장소 `00_운영/기록/2026-09-11_A1-3_웹구현_인계.md`에 있습니다.
