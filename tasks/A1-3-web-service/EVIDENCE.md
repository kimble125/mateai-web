# 증빙 목록 (A1-3)

사실 / 미확인을 구분해 적는다. 캡처 파일은 `evidence/`에 추가한다 (키·계정 정보가 보이지 않게).

## 확인된 것 (2026-09-11 19:56 KST, 로컬)

| 항목 | 방법 | 결과 |
|---|---|---|
| 회귀 테스트 11개 | `python3 -m unittest tests/test_web_regression.py` | 11/11 OK (외부 API 호출 없음). 09-11 20:41 기준. 새로 추가한 테스트는 수정 전 코드에서 실패하는 것을 확인 |
| 로컬 페이지 | `python3 devserver.py` → `GET /` | 200 |
| 잘못된 지역 수 | `POST /api/travel {"date":"2026-10-01","cities":"abc"}` | `400 BAD_CITIES` (수정 전 500) |
| 빈 채팅 입력 | `POST /api/chat {"utterance":""}` | `EMPTY_INPUT` 안내 |

## 배포 확인 (2026-09-11 20:13 KST, https://mateai-web-jk4v-two.vercel.app, 커밋 c69091c)

| 요청 | 결과 |
|---|---|
| `GET /`, `css/style.css`, `js/app.js` | 200 (비로그인) |
| `GET /tasks/...`, `GET /.env` | 404 — 배포 제외 확인 |
| `POST /api/travel {"cities":"abc"}` | 400 `BAD_CITIES` |
| `POST /api/travel {"date":"2026-02-30"}` | 400 `BAD_DATE` |
| `POST /api/chat {"utterance":""}` | 400 `EMPTY_INPUT` |
| `POST /api/chat` 지연 상황(안내 모드) | 200, `llm_calls: 0`, 결정론 템플릿 |
| `POST /api/chat` 일반 인사(동행 모드) | **500 ValueError, 0.34초** → 원인 수정 후 `7bc6c52` 재배포 |
| (7bc6c52) `POST /api/chat` 동행 모드 | **200, 2.9초, 실제 AI 응답** (`provider: openai`, `ai_generated: true`) |
| (7bc6c52) `POST /api/travel {"date":"2026-10-03","cities":1}` | **200, 7.6초**, 부산 추천, 6개 섹션, Kakao 5건, 근거 검사 pass 5/5. Gemini HTTP 404 → OpenAI 전환 기록 |
| (c6e72ac) 같은 여행 요청 | 200, `status: complete`, 제주, 근거 검사 pass 5건, 오류 0건 |

## 미확인 / 평가 중 추가할 것

| 항목 | 상태 |
|---|---|
| 기존 Vercel 프로젝트 2개 | 계속 `failure`, 빌드 로그 미열람 → 원인 미확인 (새 프로젝트 jk4v로 대체) |
| 실제 AI 생성 성공 **화면 캡처** | API 응답으로는 배포 성공 확인(위 표). 화면 캡처는 평가 중 추가 |
| 데스크톱·모바일 캡처 | 브라우저 개발자도구 반응형 모드(390px / 1440px)로 평가 중 캡처 |
| AI 코딩 도구 사용 과정 | Codex가 기획, Claude Code가 이 커밋의 수정·테스트 수행. 대화 스크린샷 추가 예정 |

과거(A1-1/A1-2) 캡처는 오늘 배포 결과의 증거로 쓰지 않는다.
