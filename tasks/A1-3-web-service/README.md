# A1-3 AI 웹 서비스 빌딩 — MateAI

**MateAI: 한국 여행을 함께 계획하는 AI 동행 웹.** 대화(라이브 챗)와 여행 리포트를 한 페이지에서 제공하고,
AI가 쓴 가게 이름을 실제 지도 검색 결과와 대조해 **확인된 정보 / AI 추정 / 검사 불가**를 구분해 보여 줍니다.

> **배포 URL: https://mateai-web-jk4v-two.vercel.app** (로그인 없이 접속 가능)
>
> 서비스 코드는 이 폴더가 아니라 **저장소 루트**에 있습니다 (Vercel이 루트를 배포하기 때문).
> 이 폴더는 평가용 안내·기획서·증빙만 담습니다. `tasks/`는 `.vercelignore`로 배포에서 제외됩니다.

## 평가자용 5분 경로

| 순서 | 볼 것 | 위치 |
|---|---|---|
| 1 | 서비스 기획서 (목적·타겟·페이지·AI 입출력·실패 기준) | [`SERVICE_PLAN.md`](SERVICE_PLAN.md) |
| 2 | 프론트 (바닐라, 4페이지) | [`/index.html`](../../index.html) Home · [`/chat.html`](../../chat.html) Chat · [`/trip.html`](../../trip.html) Trip Planner · [`/about.html`](../../about.html) About · [`/css/style.css`](../../css/style.css) · [`/js/`](../../js/) (`common.js` 공통 · `chat.js` · `trip.js`) |
| 3 | 백엔드 (Vercel Python Functions) | [`/api/chat.py`](../../api/chat.py) · [`/api/travel.py`](../../api/travel.py) · [`/requirements.txt`](../../requirements.txt) |
| 4 | 회귀 테스트 (외부 API 호출 없음) | [`/tests/test_web_regression.py`](../../tests/test_web_regression.py) |
| 5 | 이번에 고친 버그와 검증 상태 | 아래 표 · [`EVIDENCE.md`](EVIDENCE.md) |

## 필수 제출 5종 체크

| 요구 | 상태 | 근거 |
|---|---|---|
| 배포된 웹 서비스 (Vercel URL) | ✅ 공개 접속·입력 오류 처리·**실제 AI 대화/여행 리포트 성공** 확인 | https://mateai-web-jk4v-two.vercel.app |
| GitHub 저장소 (프론트/api 구분) | ✅ | 이 저장소 루트 구조 |
| README (소개·스택·실행/배포·URL·환경 변수) | ✅ | 이 문서 + [루트 README](../../README.md) |
| 서비스 기획서 | ✅ | [`SERVICE_PLAN.md`](SERVICE_PLAN.md) |
| 증빙 (데스크톱·모바일·AI 동작·AI 코딩 과정) | 🟡 평가 시 캡처 추가 | [`EVIDENCE.md`](EVIDENCE.md) |

## 보너스 과제 (선택)

| 보너스 | 상태 | 근거 |
|---|---|---|
| ② UX: 다크 모드 | ✅ 적용 | 우상단 🌙/☀️ 토글. OS 설정 자동 반영, 선택은 `localStorage`에 기억 (`js/common.js` theme, `css/style.css` `[data-theme]`) |
| ② UX: 마이크로 인터랙션 | ✅ 적용 | 채팅 타이핑 표시(점 3개), 말풍선 등장 애니메이션, 버튼 누름 효과, 리포트 로딩 스켈레톤. `prefers-reduced-motion`이면 끔 |
| ② 개선 효과 확인 방법 | 🟡 **설계만** (측정 코드 미적용) | 지표: 세션당 대화 턴 수, Trip Planner → "Ask Mate about this plan" 클릭률, 다크 모드 사용 비율. 방법: Vercel Web Analytics 활성화 후 개편 전후 비교. 현재 수치 없음 |
| ① 저장/자동화 연동 | ❌ 미적용 | 대화는 브라우저 탭(`sessionStorage`)에만 저장하며 외부 저장소·노코드 자동화 연동 없음 |

## 기술 스택과 구조

- 프론트: 순수 HTML / CSS / JavaScript (프레임워크 없음). **4개 페이지** Home / Chat / Trip Planner / About, 모든 페이지 상단 메뉴로 이동. 영어권 여행자용 영어 UI
- 채팅: 최근 대화 12턴을 함께 보내 이어 말하기. Trip Planner 결과를 "Ask Mate about this plan"으로 채팅에 넘기거나, 채팅 안의 "🗺️ Plan a trip in chat"으로 바로 리포트를 받아 이후 질문의 맥락으로 사용 (이동만으로는 AI 추가 호출 없음)
- 백엔드: Vercel Serverless Functions (Python 3.12), 표준 라이브러리 `urllib`만 사용
- AI: OpenAI 호환 LLM (키가 있는 제공자 1개 사용) + 장소 검색(Kakao/Naver 지역 검색)

```
사용자 입력(form) → js/app.js fetch('/api/travel') → api/travel.py 입력 검증
  → LLM 지역 추천(JSON, 파싱 실패 시 1회 재시도) → 지도 API 맛집 검색(실패 시 부분 결과)
  → LLM 리포트 작성(실패 시 6개 섹션 폴백) → 가게 이름 근거 검사 → JSON → 화면 렌더
```

## 실행 방법 (로컬)

```bash
git clone https://github.com/kimble125/mateai-web.git && cd mateai-web
cp .env.example .env          # 키를 채운다. .env는 .gitignore로 커밋되지 않는다
python3 devserver.py          # http://127.0.0.1:8787
python3 -m unittest tests/test_web_regression.py   # 외부 API 없이 11개 회귀
```

## 환경 변수 (키 값은 절대 커밋하지 않음)

| 변수 | 용도 |
|---|---|
| `OPENAI_API_KEY` 또는 `GEMINI_API_KEY` / `LLM_BASE_URL`+`LLM_MODEL` | 대화·여행 리포트 생성 LLM |
| `KAKAO_REST_API_KEY` 또는 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET` | 맛집 장소 검색 |

- 로컬: 루트 `.env` (`api/_lib/providers.py`가 읽음, 이미 설정된 환경 변수를 덮어쓰지 않음)
- 배포: Vercel 대시보드 → Project → Settings → Environment Variables에 같은 이름으로 등록
- 키가 없으면 AI 성공처럼 보이지 않게 `NO_LLM_KEY` 오류를 반환합니다.

## 배포 방법과 현재 상태

1. GitHub 저장소를 Vercel에 import (Framework: Other, Root: 저장소 루트)
2. 위 환경 변수를 Vercel에 등록 → `main`에 push하면 자동 재배포

**현재 상태 (2026-09-11 20:13 확인, 사실):**
- Vercel 프로젝트 `mateai-web-jk4v` 배포 **success**. 공개 주소 https://mateai-web-jk4v-two.vercel.app 비로그인 `GET /` 200.
- 배포에서 확인: `/api/travel` 잘못된 지역 수 → 400 `BAD_CITIES`, 불가능한 날짜 → 400 `BAD_DATE`,
  `/api/chat` 빈 입력 → 400 `EMPTY_INPUT`, 안내 모드(LLM 0회) → 200. `tasks/`와 `.env`는 404 (배포 제외 확인).
- 배포에서 발견: `/api/chat` 동행 모드가 **500 ValueError** (0.3초, 아래 버그 표). 수정 커밋 `7bc6c52` 재배포.
- `7bc6c52` 배포에서 실제 AI 확인 (20:16): 대화 동행 모드 200·2.9초·`provider: openai`·`ai_generated: true`,
  여행 리포트(2026-10-03, 1곳) 200·7.6초·6개 섹션·Kakao 맛집 5건·근거 검사 5/5 일치.
  단 1순위 Gemini가 HTTP 404로 실패해 OpenAI로 넘어감 → 빈 모델명 기본값 처리 추가.
- `c6e72ac` 배포 (20:18): 같은 요청이 `status: complete`, 오류 0건 (Gemini 1순위 성공) — 빈 모델명 가설과 일치.
- 기존 프로젝트 `mateai-web`, `mateai-web-hfni`는 계속 `failure` (빌드 로그 미열람, 원인 미확인). 새 프로젝트로 재연결함.

## 이번 작업에서 고친 버그 (AI 코딩 결과를 직접 검증한 부분)

| 문제 (재현) | 원인 | 수정 | 검증 |
|---|---|---|---|
| `cities: "abc"` → **500 서버 오류** | `int()` 변환 예외를 잡지 않음 | 정수 1~2만 허용, 아니면 `400 BAD_CITIES` | `test_travel_rejects_bad_types_without_server_error` |
| `cities: 5` → 조용히 2로 바뀜 | `min/max`로 몰래 보정 | 범위 밖도 명시적 오류 | 같은 테스트 |
| JSON 배열 본문 → 500 | `body.get` 가정 | 객체가 아니면 `BAD_JSON` (chat·travel) | 같은 테스트 + 수동 curl |
| AI 실패 시 폴백 리포트에 `## 1일 일정 제안` 누락 | 폴백이 5개 섹션만 작성 | 6번째 섹션을 도시·검색 결과로 채움 | `test_fallback_report_keeps_all_six_sections` |
| 검사한 가게 0건인데 "근거 검사 통과" 표시 | 불일치 0건만 보고 통과 판정 | "검사 대상 없음" 배지 분리 | `test_frontend_does_not_call_zero_checks_a_pass` |
| **배포에서만** 대화 동행 모드 → 500 `ValueError` | `urllib.request.Request()` 생성이 `try` 밖 → 스킴 없는/빈 `LLM_BASE_URL`이면 제공자 오류가 아닌 예외로 턴 전체가 죽음 (배포 환경변수 값은 미확인, 가설) | `Request` 생성을 `try` 안으로, 빈 값은 기본 URL 사용 | `test_bad_llm_base_url_is_a_provider_error_not_a_crash` (수정 전 실패 확인) |
| AI 호출이 실패해도 고정 문구가 "AI API" 응답으로 표시 | 생성 결과와 무관하게 라벨 고정 | `generator`를 성공/키 없음/호출 실패로 구분, `ai_generated`·`provider` 추가 | `test_chat_failure_is_not_labelled_as_ai_success` |
| **배포에서** Gemini 호출이 매번 HTTP 404 → OpenAI로 전환 | 빈 `GEMINI_MODEL`이면 URL이 `models/:generateContent`가 됨 (배포 값 미확인, 가설. 기본 모델은 목록 조회로 존재 확인) | 빈 모델명·URL 환경변수는 기본값 사용 | `test_empty_model_env_uses_defaults` |
| 대화가 매 턴 같은 말("엄마 사진 속 동대구역", KTX/ITX)을 반복 | 대화 기록 없이 매 턴 고정 기억·열차 정보를 프롬프트에 주입 | 사용자 정의 페르소나(한국 여행 온 외국인 ↔ 한국인 현지 친구 가이드) 프롬프트 + 최근 대화 기록 + 여행 리포트 맥락 | `test_chat_prompt_uses_history_and_trip_context`, 로컬 3턴 실호출 확인 |
| 일부 단계 실패를 성공처럼 표시 | 상태 필드 없음 | 응답에 `status: complete/partial`, 화면에 "부분 결과" 안내. 다음 제공자로 넘어가 성공한 경우는 partial 아님 | 배포 응답 확인 |

## 실패 처리 (과제 기준 3종 모두)

| 상황 | 사용자에게 보이는 것 |
|---|---|
| 빈 입력 / 날짜 누락 / 불가능한 날짜 | 입력칸 아래 안내 (`EMPTY_INPUT`, `BAD_DATE`) |
| API 오류 4xx/5xx | "잠시 후 다시 시도" 안내, 버튼 재활성화, 입력 보존 |
| 지연/타임아웃 | 60초 제한(AbortController) 후 안내. 서버 호출 비용까지 중단된다는 뜻은 아님 |

## 한계 (과장하지 않기)

- 근거 검사는 **가게 이름이 검색 결과에 있는지**만 봅니다. 주소·영업시간·실제 영업 여부는 보장하지 않습니다.
- 날씨·행사는 AI 추정입니다. 교통 정보는 샘플 데이터이며 실시간 조회가 아닙니다.
- 화면은 한국어, 대화는 영어 입력 기준입니다. 영어권 여행자용 완전한 영어화는 미완입니다.
- 모델을 직접 학습한 것이 아니라 기존 LLM API를 연결한 서비스입니다.
