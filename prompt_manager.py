"""나만의 프롬프트 관리 — 콘솔 프로그램

터미널에서 메뉴 번호를 골라 프롬프트를 보관하고 찾아 쓴다.
표준 라이브러리만 쓴다(외부 패키지 없음).

    python3 prompt_manager.py
"""

# ── 카테고리 ────────────────────────────────────────────────────────────
# 프롬프트를 분류하는 고정 목록. '직접 입력'으로 새 카테고리도 만들 수 있다.
CATEGORIES = ["텍스트 생성", "이미지 생성", "영상 생성", "페르소나", "자동화", "기타"]


# ── 기본 데이터 ─────────────────────────────────────────────────────────
# 프롬프트 하나 = 딕셔너리, 전체 = 리스트.
# 아래는 MateAI(캐릭터챗 엔진) 개발에서 실제로 쓴 프롬프트들이다.
def seed_prompts() -> list[dict]:
    return [
        {
            "title": "압축 시스템 프롬프트 (202토큰 → 69토큰)",
            "content": (
                "You are Mintae, a Korean guy in his twenties who shows foreign friends "
                "around Korea. Casual and warm, second person, short turns. Bring back why "
                "they came. Never say you are an AI or an assistant. Never use "
                "customer-service phrasing. Never state a time, train number, platform, or "
                "price unless you were given it.\n\n"
                "[왜 줄였나] 학습을 돌려 보니 시스템 프롬프트가 202토큰인데 실제 응답은 "
                "16토큰이었다. 연산의 82%가 매번 같은 지시문을 다시 읽는 데 쓰이고 있었다. "
                "규칙을 버리지 않고 문장만 압축해 69토큰으로 줄였더니 전체 시퀀스가 "
                "245 → 112 토큰이 됐다. 프롬프트 길이는 품질이 아니라 비용이다."
            ),
            "category": "텍스트 생성",
            "favorite": True,
        },
        {
            "title": "근거 가드 — cite-or-refuse 규칙",
            "content": (
                "다음 규칙으로 생성된 답변을 검사하라.\n"
                "1. 시각·열차번호·요금·승강장 같은 **사실 주장만** 좁게 뽑는다. "
                "감정과 의견은 검사하지 않는다.\n"
                "2. 각 주장이 주어진 근거에 있는지 대조한다. "
                "값이 있어도 **역할이 다르면 거부한다** — 도착 시각을 '출발한다'고 말하면 안 된다.\n"
                "3. 위반한 문장만 제거하고 나머지는 살린다.\n\n"
                "[왜 이렇게] 관계형 챗봇에서 오류는 기능 실패가 아니라 배신으로 체감된다. "
                "그렇다고 답 전체를 막으면 캐릭터가 사라진다. 그래서 문장 단위로 자른다."
            ),
            "category": "자동화",
            "favorite": False,
        },
        {
            "title": "선호 데이터 6단계 정제 기준",
            "content": (
                "유저의 '다시 생성' 클릭을 선호 신호로 쓸 때, 원시 쌍을 그대로 학습에 넣지 않는다.\n"
                "1) 모드 경계 — 사실 안내 턴은 통째로 제외 (재미로 최적화하면 정확성이 침식된다)\n"
                "2) 습관적 재생성 유저 제외 — 재생성 비율 0.35 이상은 신호가 아니라 버릇\n"
                "3) 신규 유저 제외 — 가입 3일 미만의 탐색적 클릭\n"
                "4) 품질 게이트 — chosen은 근거 위반 0, 페르소나 0.30 이상\n"
                "5) 길이 편향 억제 — chosen이 rejected보다 1.8배 이상 길면 의심\n"
                "6) 강신호 가중 — 3회 이상 재생성한 쌍에 가중치\n\n"
                "[결과] 499쌍 → 155쌍. 1단계에서만 31%가 빠진다."
            ),
            "category": "자동화",
            "favorite": True,
        },
        {
            "title": "컴패니언 프롬프트 조립 규칙",
            "content": (
                "캐릭터 발화를 생성할 때 프롬프트에 반드시 두 가지를 넣는다.\n\n"
                "1. **유저 발화** — 시스템 프롬프트만 주면 모델은 무엇에 답할지 모른다.\n"
                "2. **인용 가능한 근거 목록** — 근거를 주지 않으면 모델은 사실을 말할 방법이 "
                "아예 없다. 근거 가드가 전부 잘라내기 때문이다. "
                "cite-or-refuse는 'refuse'만 있는 게 아니라 'cite'할 것을 손에 쥐여 줘야 성립한다.\n\n"
                "조립 순서: 캐릭터 카드 → 기억 → 인용 가능 근거 → 유저 발화 → 응답 신호\n"
                "가드는 이 프롬프트를 신뢰하지 않는다. 여기 없는 사실을 지어내면 그 문장은 여전히 잘린다."
            ),
            "category": "페르소나",
            "favorite": False,
        },
        {
            "title": "DPO 실험 arm 정의 (정제 방식 비교)",
            "content": (
                "같은 SFT 모델 위에서 **정제 방식만** 바꿔 비교한다. 나머지는 전부 고정.\n"
                "- A_raw     : 정제 없음, 원시 재생성 쌍 전부\n"
                "- B_filtered: 6단계 필터 적용\n"
                "- C_lennorm : 길이 정규화 DPO(SimPO 계열) — 길이 편향을 필터가 아니라 목적함수에서\n"
                "- D_strong  : 강신호(재생성 3회 이상)만\n\n"
                "[주의] 길이 정규화는 로그확률을 응답 토큰 수로 나눈다. "
                "평균 20토큰이면 같은 베타가 사실상 1/20 세기로 작동한다. "
                "arm을 비교할 때 하이퍼파라미터가 arm마다 다른 세기로 작동하지 않는지 먼저 확인할 것."
            ),
            "category": "기타",
            "favorite": False,
        },
    ]


# ── 입력 도우미 ─────────────────────────────────────────────────────────
def ask(question: str) -> str:
    """빈 값을 허용하지 않는 입력. 비어 있으면 다시 묻는다."""
    while True:
        value = input(question).strip()
        if value:
            return value
        print("  값을 입력해 주세요.")


def ask_category() -> str:
    """정해진 목록에서 고르거나, 마지막 번호로 직접 입력한다."""
    print("\n카테고리 선택:")
    for i, name in enumerate(CATEGORIES, start=1):
        print(f"  {i}) {name}")
    print(f"  {len(CATEGORIES) + 1}) 직접 입력")

    while True:
        choice = input("선택: ").strip()
        if not choice.isdigit():
            print("  번호를 입력해 주세요.")
            continue
        n = int(choice)
        if 1 <= n <= len(CATEGORIES):
            return CATEGORIES[n - 1]
        if n == len(CATEGORIES) + 1:
            return ask("새 카테고리 이름: ")
        print(f"  1부터 {len(CATEGORIES) + 1} 사이의 번호를 입력해 주세요.")


def pick_index(prompts: list[dict], question: str = "번호 입력: ") -> int | None:
    """프롬프트 번호를 받아 리스트 인덱스로 바꾼다. 잘못된 번호면 None."""
    choice = input(question).strip()
    if not choice.isdigit():
        print("  숫자를 입력해 주세요.")
        return None
    n = int(choice)
    if not 1 <= n <= len(prompts):
        print(f"  1부터 {len(prompts)} 사이의 번호가 필요합니다.")
        return None
    return n - 1


def line(title: str) -> None:
    print(f"\n=== {title} ===")


# ── 기능: 프롬프트 추가 ─────────────────────────────────────────────────
def add_prompt(prompts: list[dict]) -> None:
    line("프롬프트 추가")
    title = ask("제목: ")
    content = ask("내용: ")
    category = ask_category()

    prompts.append({
        "title": title,
        "content": content,
        "category": category,
        "favorite": False,   # 즐겨찾기 기본값
    })
    print(f"\n'{title}' 프롬프트가 추가되었습니다!")


# ── 기능: 프롬프트 목록 ─────────────────────────────────────────────────
def format_row(index: int, prompt: dict) -> str:
    """목록 한 줄. 번호 · 카테고리 · 제목 · 즐겨찾기 표시."""
    star = " ⭐" if prompt["favorite"] else ""
    return f"{index}. [{prompt['category']}] {prompt['title']}{star}"


def print_rows(prompts: list[dict], empty_message: str) -> bool:
    """목록을 출력한다. 비어 있으면 안내를 찍고 False를 돌려준다."""
    if not prompts:
        print(f"\n{empty_message}")
        return False
    for i, prompt in enumerate(prompts, start=1):
        print(format_row(i, prompt))
    print(f"\n총 {len(prompts)}개의 프롬프트")
    return True


def show_list(prompts: list[dict]) -> None:
    line("프롬프트 목록")
    print_rows(prompts, "등록된 프롬프트가 없습니다. 먼저 추가해 주세요.")


# ── 기능: 카테고리별 조회 ───────────────────────────────────────────────
def show_by_category(prompts: list[dict]) -> None:
    line("카테고리별 조회")

    # 기본 목록 + 사용자가 직접 만든 카테고리를 합쳐서 보여 준다.
    used = [c for c in CATEGORIES]
    for prompt in prompts:
        if prompt["category"] not in used:
            used.append(prompt["category"])

    for i, name in enumerate(used, start=1):
        print(f"  {i}) {name}")

    choice = input("선택: ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(used):
        print(f"\n[안내] 1부터 {len(used)} 사이의 번호를 입력해 주세요.")
        return

    name = used[int(choice) - 1]
    found = [p for p in prompts if p["category"] == name]
    print(f"\n[{name}] 카테고리 프롬프트:")
    print_rows(found, f"[{name}] 카테고리에 등록된 프롬프트가 없습니다.")


# ── 메뉴 ────────────────────────────────────────────────────────────────
MENU = [
    "프롬프트 추가",
    "프롬프트 목록",
    "카테고리별 조회",
    "프롬프트 검색",
    "프롬프트 상세 보기",
    "즐겨찾기 관리",
    "즐겨찾기 목록",
]


def show_menu() -> None:
    line("나만의 프롬프트 관리")
    for i, name in enumerate(MENU, start=1):
        print(f"{i}. {name}")
    print("0. 종료")


def main() -> None:
    prompts = seed_prompts()

    while True:
        show_menu()
        choice = input("선택: ").strip()

        if choice == "0":
            print("\n종료합니다.")
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            print(f"\n[안내] 0부터 {len(MENU)} 사이의 번호를 입력해 주세요.")
            continue

        # 각 기능은 여기서 호출한다. 기능이 끝나면 루프가 메뉴를 다시 보여 준다.
        n = int(choice)
        if n == 1:
            add_prompt(prompts)
        elif n == 2:
            show_list(prompts)
        elif n == 3:
            show_by_category(prompts)
        else:
            print(f"\n(아직 구현되지 않은 기능입니다: {MENU[n - 1]})")


if __name__ == "__main__":
    main()
