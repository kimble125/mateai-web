# 증빙 목록 (A1-3)

사실 / 미확인을 구분해 적는다. 캡처 파일은 `evidence/`에 추가한다 (키·계정 정보가 보이지 않게).

## 확인된 것 (2026-09-11 19:56 KST, 로컬)

| 항목 | 방법 | 결과 |
|---|---|---|
| 회귀 테스트 7개 | `python3 -m unittest tests/test_web_regression.py` | 7/7 OK (외부 API 호출 없음) |
| 로컬 페이지 | `python3 devserver.py` → `GET /` | 200 |
| 잘못된 지역 수 | `POST /api/travel {"date":"2026-10-01","cities":"abc"}` | `400 BAD_CITIES` (수정 전 500) |
| 빈 채팅 입력 | `POST /api/chat {"utterance":""}` | `EMPTY_INPUT` 안내 |

## 미확인 / 평가 중 추가할 것

| 항목 | 상태 |
|---|---|
| Vercel 배포 | GitHub Deployments 최근 10건 모두 `failure`, 빌드 로그 미열람 → 원인 미확인 |
| 실제 AI 생성 성공 캡처 | 이번 세션에서 실호출 안 함. 평가 시연에서 로컬로 1회 수행 후 캡처 |
| 데스크톱·모바일 캡처 | 브라우저 개발자도구 반응형 모드(390px / 1440px)로 평가 중 캡처 |
| AI 코딩 도구 사용 과정 | Codex가 기획, Claude Code가 이 커밋의 수정·테스트 수행. 대화 스크린샷 추가 예정 |

과거(A1-1/A1-2) 캡처는 오늘 배포 결과의 증거로 쓰지 않는다.
