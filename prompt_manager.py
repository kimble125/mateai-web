"""나만의 프롬프트 관리 — 콘솔 프로그램

터미널에서 메뉴 번호를 골라 프롬프트를 보관하고 찾아 쓴다.
표준 라이브러리만 쓴다(외부 패키지 없음).

    python3 prompt_manager.py
"""

import json
import os
from datetime import datetime

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
            "views": 0,
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
            "views": 0,
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
            "views": 0,
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
            "views": 0,
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
            "views": 0,
        },
        # ── 코디세이 이전 미션에서 쓴 프롬프트 ──────────────────────────
        {
            "title": "[B1-1] 매일 투자 일지 생성 — 항해사 '킴블'",
            "content": (
                "당신은 '킴블', 데이터로 투자를 기록하는 항해사입니다. 사용자가 주는 "
                "'매일 데이터 패킷'을 받아 옵시디언용 정형 일지를 작성합니다(혼자 보는 기록).\n\n"
                "[출력 8섹션] 1. 날짜·한 줄 요약  2. 포트폴리오 스냅샷(당일 수익률은 반드시 "
                "'달러 기준 / 환율 효과 / 원화 기준' 3줄로 분리)  3. 종목별 현황  "
                "4. 환율(USD/KRW·변동·원화 수익 영향)  5. 팩터·원인(사실/해석 구분)  "
                "6. 매매 기록  7. 내일 체크포인트  8. raw 데이터 footer\n\n"
                "[안전장치] 제공 안 된 수치·이슈는 지어내지 말고 '확인 필요'로 표기. "
                "부족하면 최대 3개 확인 질문. 사실/해석, 달러/원화를 분리. "
                "추론 과정은 노출하지 말고 결과물만.\n\n"
                "[돌아보니] 이 프롬프트의 안전장치가 나중에 MateAI의 근거 가드와 같은 발상이었다. "
                "'모르면 지어내지 말고 확인 필요라고 말하라'가 곧 cite-or-refuse다."
            ),
            "category": "페르소나",
            "favorite": True,
            "views": 0,
        },
        {
            "title": "[B1-1] 주간 블로그 초고 — 캐릭터 대사는 자리만 비우기",
            "content": (
                "당신은 '킴블'의 편집 보조입니다. 매일 일지 7건을 받아 '주간 블로그 초고'를 "
                "만듭니다. 단, 킴블의 캐릭터 대사·농담·도입 훅은 직접 쓰지 말고 "
                "[킴블 보이스: (여기에 사람이 채움)] 형태로 **자리만 비워 둡니다.**\n\n"
                "[출력 10섹션] 1.제목 후보 3개(SEO) 2.한 줄 요약 3.이번 주 한눈에(달러/환율/원화 "
                "3분할·누적·벤치마크) 4.무슨 일이 있었나(사실/해석 구분) 5.잘된 것/아쉬운 것 "
                "6.환율 이야기 7.다음 주 관전 포인트(단정 금지) 8.[킴블 보이스 채울 자리] 표시 "
                "9.SEO 메타 10.면책\n\n"
                "[안전장치] 7건에 없는 사실·수치를 만들지 않음. 사실/의견, 달러/원화 분리. "
                "캐릭터 대사는 창작하지 말고 자리만.\n\n"
                "[돌아보니] **사실은 AI가, 캐릭터는 사람이** — 레이어를 나눈 첫 시도였다. "
                "MateAI가 가이드 모드와 컴패니언 모드를 분리한 것과 같은 구조다."
            ),
            "category": "텍스트 생성",
            "favorite": False,
            "views": 0,
        },
        {
            "title": "[B1-2] 영상 생성 — 원화 보존과 금지 목록",
            "content": (
                "One continuous shot. The red risk pulse appears once on the translucent window "
                "and gently fades. Clean mint light threads grow slowly from Dohyeon's hand "
                "toward the three family silhouettes behind him. Very slow two-percent camera "
                "push-in. Preserve the young Korean man's face, natural five-finger hand, deep "
                "navy hoodie, pose, window shape, and all family silhouettes exactly. "
                "Restrained warm Korean pencil-webtoon motion, subtle breathing only.\n\n"
                "No text, no letters, no numbers, no ticker, no chart, no price, no profit, "
                "no buy or sell button, no new symbol, no new person, no extra finger, "
                "no hand deformation, no face morphing, no camera shake, no cyberpunk overload.\n\n"
                "[채택 기준] ①얼굴·손·후드가 원화와 같다 ②적색 파동은 한 번만 ③민트 선이 "
                "가족 쪽으로 연결된다 ④창에 숫자·차트·버튼이 생기지 않는다\n"
                "한 항목이라도 실패하면 재생성 전에 **프롬프트 맨 앞에 실패 원인을 한 문장 추가**한다.\n\n"
                "[돌아보니] 금지 목록이 프롬프트의 절반을 차지한다. 생성 모델에서는 "
                "'무엇을 하라'보다 '무엇을 하지 마라'가 더 강하게 작동하는 경우가 많다."
            ),
            "category": "영상 생성",
            "favorite": False,
            "views": 0,
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
        "views": 0,          # 상세 보기로 꺼내 쓴 횟수
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


# ── 기능: 검색 ──────────────────────────────────────────────────────────
def search_prompt(prompts: list[dict]) -> None:
    line("프롬프트 검색")
    keyword = ask("검색어: ").lower()

    # 제목 또는 내용에 포함되면 결과. 대소문자는 구분하지 않는다.
    found = [p for p in prompts
             if keyword in p["title"].lower() or keyword in p["content"].lower()]

    print("\n검색 결과:")
    if print_rows(found, f"'{keyword}'와(과) 일치하는 프롬프트가 없습니다."):
        print(f"({len(found)}개를 찾았습니다.)")


# ── 기능: 상세 보기 ─────────────────────────────────────────────────────
def show_detail(prompts: list[dict]) -> None:
    line("프롬프트 상세 보기")
    if not print_rows(prompts, "등록된 프롬프트가 없습니다."):
        return

    i = pick_index(prompts)
    if i is None:
        return

    prompt = prompts[i]
    prompt["views"] = prompt.get("views", 0) + 1   # 실제로 꺼내 쓴 횟수를 센다
    bar = "─" * 60
    print(f"\n{bar}")
    print(f"제목: {prompt['title']}")
    print(f"카테고리: {prompt['category']}")
    print(f"즐겨찾기: {'⭐' if prompt['favorite'] else '—'}")
    print(f"사용 횟수: {prompt['views']}회")
    print(bar)
    print(prompt["content"])
    print(bar)


# ── 기능: 즐겨찾기 ──────────────────────────────────────────────────────
def toggle_favorite(prompts: list[dict]) -> None:
    line("즐겨찾기 관리")
    if not print_rows(prompts, "등록된 프롬프트가 없습니다."):
        return

    i = pick_index(prompts, "프롬프트 번호 입력: ")
    if i is None:
        return

    prompt = prompts[i]
    prompt["favorite"] = not prompt["favorite"]
    action = "추가했습니다" if prompt["favorite"] else "해제했습니다"
    print(f"\n'{prompt['title']}' 프롬프트를 즐겨찾기에서 {action}!")


def show_favorites(prompts: list[dict]) -> None:
    line("즐겨찾기 목록")
    found = [p for p in prompts if p["favorite"]]
    print_rows(found, "즐겨찾기한 프롬프트가 없습니다.")


# ── 보너스 1: 파일로 저장하고 불러오기 ──────────────────────────────────
# 기본 동작은 "종료하면 초기화"다. 저장은 사용자가 메뉴에서 명시적으로 고를 때만 한다.
DATA_FILE = "prompts.json"
EXPORT_DIR = "exports"


def save_to_file(prompts: list[dict]) -> None:
    line("파일로 저장")
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"\n저장하지 못했습니다: {e}")
        return
    print(f"\n{len(prompts)}개를 {DATA_FILE} 에 저장했습니다.")


def load_from_file(prompts: list[dict]) -> None:
    line("파일에서 불러오기")
    if not os.path.exists(DATA_FILE):
        print(f"\n{DATA_FILE} 이 없습니다. 먼저 저장해 주세요.")
        return
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"\n불러오지 못했습니다: {e}")
        return

    # 리스트를 새로 만들지 않고 제자리에서 갈아 끼운다.
    # main()이 들고 있는 것과 같은 객체여야 화면에 반영된다.
    prompts.clear()
    for item in loaded:
        item.setdefault("favorite", False)   # 옛 파일에 없을 수 있는 키를 채운다
        item.setdefault("views", 0)
        prompts.append(item)
    print(f"\n{len(prompts)}개를 불러왔습니다.")


def export_markdown(prompts: list[dict]) -> None:
    """카테고리별로 Markdown 파일을 만든다."""
    line("Markdown으로 내보내기")
    if not prompts:
        print("\n내보낼 프롬프트가 없습니다.")
        return

    os.makedirs(EXPORT_DIR, exist_ok=True)
    by_category: dict[str, list[dict]] = {}
    for prompt in prompts:
        by_category.setdefault(prompt["category"], []).append(prompt)

    today = datetime.now().strftime("%Y-%m-%d")
    for category, items in by_category.items():
        # 파일명에 쓸 수 없는 문자를 걷어낸다.
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in category).strip()
        path = os.path.join(EXPORT_DIR, f"{safe}.md")
        lines = [f"# {category}", "", f"내보낸 날짜: {today}", ""]
        for prompt in items:
            star = " ⭐" if prompt["favorite"] else ""
            lines += [f"## {prompt['title']}{star}", "", "```", prompt["content"], "```", ""]
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError as e:
            print(f"  {path} 실패: {e}")
            continue
        print(f"  {path}  ({len(items)}개)")
    print(f"\n{len(by_category)}개 카테고리를 내보냈습니다.")


# ── 보너스 2: 수정·삭제와 사용 기록 ─────────────────────────────────────
def edit_prompt(prompts: list[dict]) -> None:
    line("프롬프트 수정")
    if not print_rows(prompts, "등록된 프롬프트가 없습니다."):
        return
    i = pick_index(prompts)
    if i is None:
        return

    prompt = prompts[i]
    print(f"\n(그대로 두려면 Enter)")
    title = input(f"제목 [{prompt['title']}]: ").strip()
    content = input("내용 (Enter=유지, 입력하면 교체): ").strip()

    if title:
        prompt["title"] = title
    if content:
        prompt["content"] = content
    if input("카테고리도 바꿀까요? (y/N): ").strip().lower() == "y":
        prompt["category"] = ask_category()
    print(f"\n'{prompt['title']}' 프롬프트를 수정했습니다!")


def delete_prompt(prompts: list[dict]) -> None:
    line("프롬프트 삭제")
    if not print_rows(prompts, "등록된 프롬프트가 없습니다."):
        return
    i = pick_index(prompts)
    if i is None:
        return

    title = prompts[i]["title"]
    # 삭제는 되돌릴 수 없으므로 한 번 더 묻는다.
    if input(f"'{title}' 을(를) 정말 삭제할까요? (y/N): ").strip().lower() != "y":
        print("\n취소했습니다.")
        return
    prompts.pop(i)
    print(f"\n'{title}' 프롬프트를 삭제했습니다.")


def show_top(prompts: list[dict]) -> None:
    """사용 횟수가 많은 순으로 보여 준다.

    이 기능이 답하는 질문: '내가 실제로 무엇을 쓰는가.'
    즐겨찾기는 내가 중요하다고 *선언한* 것이고, 사용 횟수는 실제 *행동*이다.
    둘은 자주 어긋난다 — 그 간극이 이 목록의 쓸모다.
    """
    line("많이 쓴 프롬프트 (Top)")
    used = [p for p in prompts if p.get("views", 0) > 0]
    if not used:
        print("\n아직 상세 보기로 꺼내 쓴 프롬프트가 없습니다.")
        return

    ranked = sorted(used, key=lambda p: p["views"], reverse=True)
    for rank, prompt in enumerate(ranked, start=1):
        star = " ⭐" if prompt["favorite"] else ""
        gap = "  ← 즐겨찾기는 아닌데 많이 씀" if not prompt["favorite"] and rank <= 3 else ""
        print(f"{rank}. [{prompt['views']}회] {prompt['title']}{star}{gap}")
    print(f"\n총 {len(ranked)}개")


# ── 메뉴 ────────────────────────────────────────────────────────────────
MENU = [
    "프롬프트 추가",
    "프롬프트 목록",
    "카테고리별 조회",
    "프롬프트 검색",
    "프롬프트 상세 보기",
    "즐겨찾기 관리",
    "즐겨찾기 목록",
    "파일로 저장",
    "파일에서 불러오기",
    "Markdown으로 내보내기",
    "프롬프트 수정",
    "프롬프트 삭제",
    "많이 쓴 프롬프트 (Top)",
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
        elif n == 4:
            search_prompt(prompts)
        elif n == 5:
            show_detail(prompts)
        elif n == 6:
            toggle_favorite(prompts)
        elif n == 7:
            show_favorites(prompts)
        elif n == 8:
            save_to_file(prompts)
        elif n == 9:
            load_from_file(prompts)
        elif n == 10:
            export_markdown(prompts)
        elif n == 11:
            edit_prompt(prompts)
        elif n == 12:
            delete_prompt(prompts)
        elif n == 13:
            show_top(prompts)
        else:
            print(f"\n(아직 구현되지 않은 기능입니다: {MENU[n - 1]})")


if __name__ == "__main__":
    main()
