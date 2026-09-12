# MateAI — 한국 여행 동행 AI 웹 서비스

첫 방한 영어권 여행자를 위한 AI 동행 서비스입니다. 같은 화면에서 현지 친구와 대화하고,
날짜만 주면 하루 일정을 받습니다. **AI가 쓴 가게 이름은 지도 검색 결과와 대조하고,
확인하지 못한 것은 확인하지 못했다고 표시합니다.**

**배포:** <https://mateai-web-jk4v-two.vercel.app>

이 저장소는 Codyssey A1-1~A1-3 과제의 코드와, 그것을 이어 붙인 MateAI 웹 서비스를 함께 담고 있습니다.
장기 목표는 캐릭터챗 서비스에 쓸 수 있는 대화 엔진을 만들고, 그 판단 근거를 설명할 수 있게 남기는 것입니다.

## 이 서비스가 주장하는 것

> 사실 안내 경로에는 LLM 호출이 없습니다.

친근하게 말을 걸던 친구가 열차 시각을 틀리면, 사용자는 그것을 기능 실패가 아니라 관계의 배신으로 받아들입니다.
그래서 **말투(몰입)와 사실(정확성)을 합치지 않고 경로를 나눴습니다.** 서버리스에서 이 구분은
설계 주장이 아니라 호출 수와 응답 시간으로 드러납니다.

| 레이어 | 처리 | LLM 호출 | 사실 검증 | 실측 |
|---|---|---:|---|---|
| 가이드 (지연·환승 같은 사실 안내) | 순수 Python 규칙 엔진 | **0회** | 열차 데이터에 있는 값만 인용, 없으면 거절 | 0 ms (로컬, 2026-09-12) |
| 컴패니언 (자유 대화) | LLM 1회 | 1회 | **없음.** 프롬프트로 시간·가격 창작을 금지할 뿐 | 0.6~2.9 s (배포, 2026-09-11) |
| 여행 리포트 | LLM 최대 3회 + 지도 최대 2회 | 3회 | 리포트의 가게 이름을 지도 검색 결과와 대조 | 7.6 s (배포, 2026-09-11) |

컴패니언 응답에 근거 검사를 붙이지 않은 것은 **의도한 현재 상태**입니다. 열차 사실 가드를 자유 대화에
그대로 적용하면 정상적인 여행 조언까지 잘려 나갑니다. 대신 가게 이름 단위 검증을 대화에도 넣는 것이
다음 작업 후보입니다.

## 구성

| 페이지 | 파일 | 내용 |
|---|---|---|
| Home | `index.html` | 서비스 소개, 대화 예시 |
| Chat | `chat.html` · `js/chat.js` | 현지 친구와 대화, 채팅 안에서 여행 리포트 생성, 지연 상황 데모 |
| Trip Planner | `trip.html` · `js/trip.js` | 날짜·지역 수 입력 → 리포트 → 대화로 이어가기 |
| About | `about.html` | 무엇을 검증하고 무엇을 보장하지 않는지 |

```
사용자 입력 → js/common.js fetch('/api/chat' | '/api/travel')
  → api/_lib/endpoint.serve : 호출 예산 확인 → 입력 검증
  → LLM 추천 · 지도 검색 · LLM 리포트 작성
  → api/_lib/travel_grounding : 가게 이름 대조
  → JSON → 화면(확인됨 / 추정 / 검사 대상 없음 구분 표시)
```

| 영역 | 사용 |
|---|---|
| 프론트엔드 | 바닐라 HTML / CSS / JavaScript. 다크 모드, 390px~1440px 반응형 |
| 백엔드 | Vercel Serverless Functions (Python 3.12), `api/` |
| AI | Gemini(주) → OpenAI(보조) 폴백 체인 |
| 장소 검색 | Kakao Local(주) → Naver Local(보조) |
| 외부 패키지 | 없음. 모든 HTTP 호출은 표준 라이브러리 `urllib` |

`api/_lib/`는 별도로 개발 중인 캐릭터챗 엔진 MateAI에서 가져온 이식본입니다(라우터, 규칙 엔진,
근거 가드, 페르소나 점수). 연구 코드와 자동 동기화되지 않습니다.

## 대화 설계

프롬프트는 역할만 정의합니다. 입력자는 한국에 여행 온 외국인, 응답자는 한국인 현지 친구 가이드입니다.
이름·서사 같은 캐릭터 설정은 두지 않았습니다.

최근 12턴을 함께 보내고, 여행 리포트가 있으면 그 내용을 참고 자료로 붙입니다. 이전에는 대화 기록 없이
고정된 기억 카드를 매 턴 주입해서, 모델이 매번 같은 소개부터 다시 말하는 문제가 있었습니다
(`api/chat.py`의 `build_prompt`).

대화 안에서 만든 리포트는 이후 질문의 맥락이 됩니다. Trip Planner에서 "Ask Mate about this plan"으로
넘길 때는 추가 AI 호출이 없습니다.

## 비용과 남용 방지

공개 URL이라 유료 API가 그대로 노출됩니다. `api/_lib/budget.py`가 방문자별 호출 빈도와
인스턴스 총량을 제한합니다(기본: 대화 5분에 12회, 리포트 10분에 4회). 서버리스에는 공유 저장소가 없어
**인스턴스 하나 안에서만 정확합니다.** 정확한 전역 상한은 외부 저장소가 필요하며 아직 도입하지 않았습니다.

한 요청의 상한은 대화 LLM 1회, 리포트 LLM 3회 + 지도 2회입니다. 요청 중에는 버튼을 잠가 중복 제출을 막습니다.

## 로컬 실행

```bash
git clone https://github.com/kimble125/mateai-web.git && cd mateai-web
cp .env.example .env          # 키 값 입력. .env는 .gitignore가 막는다
python3 devserver.py          # http://127.0.0.1:8787
python3 -m unittest tests/test_web_regression.py   # 외부 API 없이 19개 회귀
```

`devserver.py`는 배포에 쓰이지 않지만 **요청 경로는 배포와 같습니다**(`serve_request`).
예전에는 `handle()`을 직접 불러서 호출 제한과 오류 숨김을 건너뛰었고, 로컬 통과가 배포 통과를 보장하지 못했습니다.

## 환경 변수와 배포

키는 로컬 `.env`와 Vercel 대시보드에만 둡니다. 브라우저로 내려가는 코드와 요청에는 넣지 않습니다.

| 이름 | 용도 |
|---|---|
| `GEMINI_API_KEY` (또는 `OPENAI_API_KEY`) | 대화·리포트 생성 |
| `LLM_MODEL` · `LLM_BASE_URL` · `GEMINI_MODEL` | 선택. **빈 값으로 두지 말 것** — 비워 두면 잘못된 요청이 되어 404/예외가 납니다 |
| `KAKAO_REST_API_KEY` (또는 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`) | 맛집 검색 |
| `CHAT_RATE_LIMIT` · `TRAVEL_RATE_LIMIT` · `*_INSTANCE_CAP` | 선택. 호출 상한 조정 |

GitHub 저장소를 Vercel에 import하고(Framework: Other, Root: 저장소 루트) 위 변수를 등록하면,
`main` 푸시마다 자동 배포됩니다. `.vercelignore`가 allowlist로 A1-3 서비스 파일만 배포하고 `tasks/`는 제외합니다.

## 한계

- 근거 검사는 가게 **이름**이 검색 결과에 있는지만 봅니다. 주소·영업시간·실제 영업 여부는 보장하지 않습니다.
- 날씨와 행사는 AI 추정입니다. 지연 데모의 열차 시각표는 샘플 데이터이며 실시간 조회가 아닙니다.
- 대화는 브라우저 탭(sessionStorage)에만 남습니다. 세션을 넘는 기억, 계정, 저장소가 없습니다.
- 자유 대화 응답은 사실 검증을 거치지 않습니다(위 표 참고).
- 모델을 직접 학습하지 않았습니다. 기존 LLM API를 연결한 서비스입니다.

## 같은 저장소의 앞선 과제

| 과제 | 내용 | 위치 |
|---|---|---|
| A1-1 | 프롬프트 관리 CLI. Python·Git 기초, 기능 단위 커밋 16개 | [`tasks/A1-1-prompt-manager/`](tasks/A1-1-prompt-manager/) |
| A1-2 | LLM 추천 → 지도 검색 → 근거 검사 리포트 CLI | [`tasks/A1-2-travel-planner/`](tasks/A1-2-travel-planner/) |
| A1-3 | 이 웹 서비스. 작업 기록은 [`tasks/A1-3-web-service/`](tasks/A1-3-web-service/) |

독립 원본 저장소도 유지합니다: [`prompt-manager`](https://github.com/kimble125/prompt-manager) ·
[`travel-planner`](https://github.com/kimble125/travel-planner).
