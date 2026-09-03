# A1-2 평가 순서

## 1. 코드 없이 먼저 확인

1. [`SUBMISSION.md`](SUBMISSION.md)의 요구사항 표를 봅니다.
2. [`results/2026-03-15_raw.json`](results/2026-03-15_raw.json)에서 추천 JSON, 맛집 목록, `errors`를 봅니다.
3. [`results/2026-03-15_travel_plan.md`](results/2026-03-15_travel_plan.md)에서 최종 6개 섹션을 봅니다.

## 2. 실행

```bash
git clone https://github.com/kimble125/mateai-web.git
cd mateai-web/tasks/A1-2-travel-planner
cp .env.example .env
open -e .env
```

`.env`에 실제 키를 넣은 뒤 다음을 실행합니다. 키가 화면이나 캡처에 보이지 않게 합니다.

```bash
python3 travel_planner.py --date 2026-03-15 --cities 2 --no-cache
```

확인할 출력은 추천 지역, 지역별 맛집 수, 리포트 완료, 근거 검사, 두 저장 경로입니다.

## 3. 실패 처리와 캐시

```bash
python3 travel_planner.py --date 2026-13-45
python3 travel_planner.py --date 2026-03-15 --cities 2
```

첫 명령은 사용법을 출력하고 종료해야 합니다. 두 번째 명령은 앞서 저장한 JSON을 찾아
`캐시 사용`을 표시합니다.

## 4. 자동 테스트

```bash
python3 -m unittest discover -s tests -v
```

## 5. 20초 설명

> 날짜를 받은 뒤 LLM의 JSON 추천을 지도 API 검색어로 연결하고, 두 결과를 다시 Markdown
> 리포트로 조합합니다. 인증·쿼터·네트워크·파싱 실패를 구분하고, 키는 `.env`로 코드와 분리했습니다.
