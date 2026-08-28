# MateAI Portfolio — Codyssey A1-1~3

Python·Git 기초 과제에서 시작해 근거 기반 여행 파이프라인을 만들고,
그 기능을 캐릭터챗 웹 서비스로 통합한 과정을 한곳에 모은 저장소입니다.
최종 목표는 **Scatter Lab ML Research Intern 포트폴리오의 기초 개발 증거와
MateAI 연구 본체를 자연스럽게 연결하는 것**입니다.

## 평가자용 빠른 경로

| 단계 | 무엇을 만들었나 | 바로 보기 | 빠른 확인 |
|---|---|---|---|
| **A1-1** | 프롬프트 관리 CLI · Python/Git 기초 | [`tasks/A1-1-prompt-manager/`](tasks/A1-1-prompt-manager/) | 폴더에서 `python3 -m unittest discover -s tests -v` |
| **A1-2** | LLM 추천 → 지도 검색 → 근거 검사 리포트 | [`tasks/A1-2-travel-planner/`](tasks/A1-2-travel-planner/) | 폴더에서 `python3 travel_planner.py --help` |
| **A1-3** | MateAI 대화 + 여행 리포트 웹 서비스 | [현재 저장소 루트](#a1-3--mateai-웹-서비스) | `python3 devserver.py` |

A1-1의 16개 기능 단위 커밋과 브랜치 병합, A1-2의 개발 이력은 Git subtree로
가져와 이 저장소의 그래프에도 보존했습니다. 독립 원본 저장소도 평가 근거로 유지합니다:
[`prompt-manager`](https://github.com/kimble125/prompt-manager) ·
[`travel-planner`](https://github.com/kimble125/travel-planner).

## 하나의 발전 흐름

```text
A1-1  프롬프트 자산·입력 검증·선언/행동 신호 구분
  ↓
A1-2  MateAI의 근거 가드를 여행 도메인에 이식
  ↓
A1-3  캐릭터 대화와 여행 리포트를 웹에서 통합·관찰
  ↓
MateAI 연구  같은 예산에서 장기기억 전략 4가지를 비교하는 실험
```

- **사실**: A1-1의 MateAI 프롬프트 5개, A1-2의 근거 가드·제공자 폴백,
  A1-3의 `api/_lib/`는 실제 프로젝트 자산을 과제에 맞게 재사용한 것입니다.
- **해석**: 세 과제는 “기초 구현 → 검증 가능한 생성 파이프라인 → 제품형 인터페이스”라는
  포트폴리오 서사를 만듭니다.
- **현재 한계**: A1 과제 자체가 ML 연구 성능을 입증하지는 않습니다. 장기기억 전략의 우열은
  MateAI의 고정 예산 4-arm 실험과 사람 평가가 완료된 뒤에만 주장합니다.

Vercel 배포에는 루트의 A1-3 서비스 파일만 포함됩니다. `tasks/`는 GitHub 평가용이며
`.vercelignore`의 allowlist로 빌드·배포 대상에서 분리했습니다.

---

## A1-3 — MateAI 웹 서비스

### 몰입과 무오류성을 레이어로 나눈 여행 동행 AI

첫 방한 영어권 여행자를 위한 AI 동행 서비스입니다.
캐릭터챗의 **몰입**과 안내 챗봇의 **정확성**을 하나로 합치는 대신 **레이어로 나눴습니다.**

**배포 URL**: (Vercel 배포 후 여기에 기입)

---

## 이 서비스가 증명하려는 것

> **사실 안내 경로에는 LLM 호출이 없습니다.**

친근하게 말을 걸며 정을 쌓아 온 친구가 열차 시각을 틀리면, 사용자는 그것을
기능 실패가 아니라 **관계의 배신**으로 받아들입니다.
그래서 사실 안내와 캐릭터 대화를 **다른 경로**로 처리합니다.

서버리스 환경에서 이 불변식은 설계 주장이 아니라 **숫자로 증명됩니다.**

| 레이어 | 처리 | LLM 호출 | 실측 응답 시간 |
|---|---|---:|---:|
| 가이드 모드 (사실 안내) | 순수 Python 규칙 엔진 | **0회** | **2 ms** |
| 컴패니언 모드 (캐릭터) | AI API | 1회 | 1,841 ms |

사이트의 **인스펙터 패널**에서 매 턴마다 직접 확인할 수 있습니다.

---

## 기술 스택

| 영역 | 사용 |
|---|---|
| 프론트엔드 | **바닐라 HTML / CSS / JavaScript** (프레임워크 없음 — 과제 제약) |
| 백엔드 | **Vercel Serverless Functions (Python)** — `api/` |
| AI | Google Gemini (주) → OpenAI (보조) |
| 장소 검색 | Kakao Local (주) → Naver Local (보조) |
| 외부 패키지 | **없음.** 모든 HTTP 호출은 표준 라이브러리 `urllib` |

---

## 페이지 구성 (4개 섹션)

| 섹션 | 내용 |
|---|---|
| **소개** | 문제 정의와 3개 레이어 설계 |
| **라이브 챗** — AI 기능 ① | 직접 말을 걸어 봅니다. 모드 전환·LLM 호출 수·근거 검사를 실시간 표시 |
| **여행 리포트** — AI 기능 ② | 날짜를 주면 AI가 지역 추천 → 지도 API 맛집 검색 → AI 리포트 작성 → **근거 검사** |
| **엔진 내부** | 정제 방식만 바꾼 DPO 실험 결과 (두 규모) |

---

## AI 기능 명세

### ① 캐릭터 대화 — `POST /api/chat`

| | |
|---|---|
| 입력 | 영어 자유 발화 + 여정 상태(정시/지연) |
| 출력 | 캐릭터 응답 + 모드·긴급도·LLM 호출 수·근거 검사 결과 |
| 실패 처리 | 빈 입력 차단 / API 오류 메시지 표시 / **30초 타임아웃** |

**근거 가드가 실제로 작동합니다.** 캐릭터가 시각을 지어내면 그 문장만 잘라냅니다.
인스펙터의 `잘라낸 주장` 항목에서 무엇이 제거됐는지 볼 수 있습니다
(실측 예: `time=8:30, time=9:10`).

### ② 여행 리포트 — `POST /api/travel`

| | |
|---|---|
| 입력 | 여행 날짜(YYYY-MM-DD) + 지역 수(1~2) |
| 출력 | 마크다운 리포트 + 근거 검사 결과 + `errors` 배열 |
| 실패 처리 | 날짜 형식 검증 / 지도 API 실패 시 **`데이터 없음`으로 계속** / **60초 타임아웃** |

리포트에 적힌 가게가 실제 검색 결과에 있는지 검사하고, 없으면 표시합니다.
날씨·행사는 AI 추정이므로 **`(추정)`** 을 붙입니다 — 검증할 수 없는 것을 검증한 척하지 않습니다.

---

## 로컬에서 실행

```bash
git clone https://github.com/kimble125/mateai-web.git
cd mateai-web

cp .env.example .env        # 키 서식 복사 후 값 입력
python3 devserver.py        # http://127.0.0.1:8787
```

`devserver.py` 는 개발용입니다. 배포에는 쓰이지 않습니다 —
Vercel이 `api/*.py` 를 서버리스 함수로, 나머지를 정적 파일로 처리합니다.

---

## 배포 (Vercel)

1. 이 저장소를 GitHub에 올립니다
2. [vercel.com/new](https://vercel.com/new) 에서 저장소를 import 합니다
3. **Settings → Environment Variables** 에 키를 등록합니다 (`.env` 는 배포되지 않습니다)

| 이름 | 필수 |
|---|---|
| `GEMINI_API_KEY` | ✅ (또는 `OPENAI_API_KEY`) |
| `OPENAI_API_KEY` | 보조 |
| `KAKAO_REST_API_KEY` | 맛집 검색용 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 보조 |

4. **Redeploy** 합니다

> 환경 변수를 바꾼 뒤에는 반드시 재배포해야 반영됩니다.

### 키 관리

- 키는 **`.env`(로컬)** 와 **Vercel 대시보드(배포)** 에만 둡니다
- `.gitignore` 가 `.env` 를 막고 있습니다. 커밋 이력에 키가 들어간 적이 없음을 확인했습니다
- 유출이 의심되면 **즉시 폐기 후 재발급**이 1순위입니다

---

## 파일 구성

```
index.html            4개 섹션 · 시맨틱 마크업
css/style.css         반응형 · 라이트/다크 자동 대응
js/app.js             fetch · 실패 처리 3종 · 작은 마크다운 렌더러
api/chat.py           AI 기능 ① 캐릭터 대화
api/travel.py         AI 기능 ② 여행 리포트
api/_lib/             MateAI 엔진 (라우터·규칙 엔진·근거 가드·페르소나)
devserver.py          로컬 개발 서버 (배포에는 미사용)
vercel.json           함수 최대 실행 시간 · 보안 헤더
.python-version       Vercel Python 3.12 고정
.vercelignore         A1-3 서비스 파일만 배포하는 allowlist
tasks/                A1-1·A1-2 코드와 Git 이력 (배포 제외)
tests/                A1-3 핵심 불변식·배포 설정 회귀 테스트
```

`api/_lib/` 는 제가 만든 캐릭터챗 엔진 **MateAI** 에서 가져왔습니다.
표준 라이브러리만 쓰므로 서버리스 환경에 그대로 올라갑니다.
