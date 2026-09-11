# A1-3 AI 웹 서비스 빌딩 — MateAI

**MateAI: 한국 여행을 함께 계획하는 AI 동행 웹.** 대화(라이브 챗)와 여행 리포트를 한 페이지에서 제공하고,
AI가 쓴 가게 이름을 실제 지도 검색 결과와 대조해 **확인된 정보 / AI 추정 / 검사 불가**를 구분해 보여 줍니다.

> 서비스 코드는 이 폴더가 아니라 **저장소 루트**에 있습니다 (Vercel이 루트를 배포하기 때문).
> 이 폴더는 평가용 안내·기획서·증빙만 담습니다. `tasks/`는 `.vercelignore`로 배포에서 제외됩니다.

## 평가자용 5분 경로

| 순서 | 볼 것 | 위치 |
|---|---|---|
| 1 | 서비스 기획서 (목적·타겟·페이지·AI 입출력·실패 기준) | [`SERVICE_PLAN.md`](SERVICE_PLAN.md) |
| 2 | 프론트 (바닐라) | [`/index.html`](../../index.html) · [`/css/style.css`](../../css/style.css) · [`/js/app.js`](../../js/app.js) |
| 3 | 백엔드 (Vercel Python Functions) | [`/api/chat.py`](../../api/chat.py) · [`/api/travel.py`](../../api/travel.py) · [`/requirements.txt`](../../requirements.txt) |
| 4 | 회귀 테스트 (외부 API 호출 없음) | [`/tests/test_web_regression.py`](../../tests/test_web_regression.py) |
| 5 | 이번에 고친 버그와 검증 상태 | 아래 표 · [`EVIDENCE.md`](EVIDENCE.md) |

## 필수 제출 5종 체크

| 요구 | 상태 | 근거 |
|---|---|---|
| 배포된 웹 서비스 (Vercel URL) | 🟡 **배포 성공, 공개 접근 설정 확인 중** | 아래 "배포 상태" |
| GitHub 저장소 (프론트/api 구분) | ✅ | 이 저장소 루트 구조 |
| README (소개·스택·실행/배포·URL·환경 변수) | ✅ | 이 문서 + [루트 README](../../README.md) |
| 서비스 기획서 | ✅ | [`SERVICE_PLAN.md`](SERVICE_PLAN.md) |
| 증빙 (데스크톱·모바일·AI 동작·AI 코딩 과정) | 🟡 평가 시 캡처 추가 | [`EVIDENCE.md`](EVIDENCE.md) |

## 기술 스택과 구조

- 프론트: 순수 HTML / CSS / JavaScript (프레임워크 없음). 4개 섹션 `#intro` `#chat` `#travel` `#engine`, 상단 메뉴 앵커 이동
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
python3 -m unittest tests/test_web_regression.py   # 외부 API 없이 7개 회귀
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

**현재 상태 (2026-09-11 20:10 확인, 사실):**
- 새 Vercel 프로젝트 `mateai-web-jk4v`에서 커밋 `c69091c` 배포가 **success** (GitHub Deployments 기록).
- 배포 URL: https://mateai-web-jk4v-o9knaeh85-kimble125.vercel.app — 비로그인 요청은 Vercel SSO로 302 리다이렉트됨
  (Deployment Protection 켜짐). 타인 접속을 위해 보호 해제 또는 공개 Production 도메인 확인이 필요.
- 기존 프로젝트 `mateai-web`, `mateai-web-hfni`는 계속 `failure` (빌드 로그 미열람, 원인 미확인).

## 이번 작업에서 고친 버그 (AI 코딩 결과를 직접 검증한 부분)

| 문제 (재현) | 원인 | 수정 | 검증 |
|---|---|---|---|
| `cities: "abc"` → **500 서버 오류** | `int()` 변환 예외를 잡지 않음 | 정수 1~2만 허용, 아니면 `400 BAD_CITIES` | `test_travel_rejects_bad_types_without_server_error` |
| `cities: 5` → 조용히 2로 바뀜 | `min/max`로 몰래 보정 | 범위 밖도 명시적 오류 | 같은 테스트 |
| JSON 배열 본문 → 500 | `body.get` 가정 | 객체가 아니면 `BAD_JSON` (chat·travel) | 같은 테스트 + 수동 curl |
| AI 실패 시 폴백 리포트에 `## 1일 일정 제안` 누락 | 폴백이 5개 섹션만 작성 | 6번째 섹션을 도시·검색 결과로 채움 | `test_fallback_report_keeps_all_six_sections` |
| 검사한 가게 0건인데 "근거 검사 통과" 표시 | 불일치 0건만 보고 통과 판정 | "검사 대상 없음" 배지 분리 | `test_frontend_does_not_call_zero_checks_a_pass` |
| 일부 단계 실패를 성공처럼 표시 | 상태 필드 없음 | 응답에 `status: complete/partial`, 화면에 "부분 결과" 안내 | 코드 확인 |

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
