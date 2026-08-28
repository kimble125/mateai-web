# 검증 근거 요약

최종 점검일: 2026-08-28

## 개발·실행 환경

- Python 3.14.5에서 검증(Python 3.10 이상 지원)
- Git 2.50.1
- 외부 패키지 없음

## 자동 테스트 결과

```text
test_add_search_detail_and_favorite_flow ... ok
test_default_data_has_required_fields_and_previous_missions ... ok
test_invalid_menu_choice_returns_to_menu_before_exit ... ok
test_save_load_and_markdown_export_are_explicit ... ok

Ran 4 tests
OK
```

재현 명령:

```bash
python3 -m unittest discover -s tests -v
```

## 수동 실행 점검

- 메뉴 표시와 정상 종료
- 기본 프롬프트 8개 목록
- 제목·내용 검색
- 상세 보기와 조회수 증가
- 즐겨찾기 추가·목록
- 조회수 기준 Top 목록

위 흐름은 [평가 순서](../EVALUATION_GUIDE.md)로 재현할 수 있습니다.

## Git 이력 핵심

원본 저장소: <https://github.com/kimble125/prompt-manager>

- 16개 커밋
- 기능 단위 커밋: 데이터 구조 → 메뉴·검증 → 추가 → 목록 → 조회·검색 → 즐겨찾기 → 보너스 → 문서·테스트
- 병합 커밋 `4261acf`: `feature/prompt-list` → `main`
- 최종 A1-1 문서 커밋 `1487495`

이 문서는 재현 가능한 텍스트 근거입니다. 평가 시스템이 이미지 첨부를 요구한다면 제출자가
개발 환경, 프로그램 실행, Git 그래프 화면을 직접 캡처해 추가해야 합니다.
