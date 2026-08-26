"""여정 컨텍스트 카드 — 동의 기반 구조화 상태.

원칙 (기획서 §4-2):
  - 사용자가 명시적으로 허용한 필드만 저장한다.
  - 건강·국적·경제상태 등 민감정보를 대화에서 *추론해* 저장하지 않는다.
  - 기본 수명은 여행 세션. 만료되면 응답 생성에서 제외된다.
  - 사용자는 언제든 확인·수정·삭제할 수 있고, 삭제는 즉시 반영된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

# AI가 대화에서 추론해 저장하는 것이 금지된 필드. 사용자가 직접 입력한 경우에만 허용한다.
INFERENCE_FORBIDDEN = frozenset(
    {"health", "nationality", "religion", "income", "political_view", "sexual_orientation"}
)

# 컨텍스트 카드가 담을 수 있는 필드의 전체 집합. 그 외는 거부한다(과수집 방지).
ALLOWED_FIELDS = frozenset(
    {
        "destination",
        "purpose",
        "flight_no",
        "flight_date",
        "language",
        "luggage",
        "companions",
        "accessibility",
        "time_budget",
        "budget_preference",
    }
) | INFERENCE_FORBIDDEN


class ConsentError(ValueError):
    """동의 범위를 벗어난 쓰기 시도."""


@dataclass(frozen=True)
class Consent:
    """필드 단위 동의와 만료 시각(분 단위 타임라인)."""

    fields: frozenset = field(default_factory=frozenset)
    expires_at_min: int | None = None  # None = 세션 종료 시 만료

    def allows(self, name: str) -> bool:
        return name in self.fields

    def expired(self, now_min: int) -> bool:
        return self.expires_at_min is not None and now_min >= self.expires_at_min


@dataclass
class JourneyCard:
    """한 여행 세션의 구조화된 맥락. 응답 생성기는 이 객체만 읽는다."""

    journey_id: str
    consent: Consent = field(default_factory=Consent)
    _data: dict[str, Any] = field(default_factory=dict, repr=False)
    _audit: list[tuple[str, str]] = field(default_factory=list, repr=False)

    # ── 쓰기 ────────────────────────────────────────────────────────────
    def set(self, name: str, value: Any, *, source: str = "user") -> None:
        """맥락 항목을 기록한다.

        source="user"     : 사용자가 직접 입력·선택 — 동의된 필드면 허용
        source="inferred" : 모델이 대화에서 추론 — 민감 필드는 항상 거부
        """
        if name not in ALLOWED_FIELDS:
            raise ConsentError(f"필드 '{name}'은 컨텍스트 카드 스키마에 없다(과수집 방지)")
        if source == "inferred" and name in INFERENCE_FORBIDDEN:
            raise ConsentError(f"민감 필드 '{name}'을 추론으로 저장할 수 없다")
        if not self.consent.allows(name):
            raise ConsentError(f"필드 '{name}'에 대한 사용자 동의가 없다")
        self._data[name] = value
        self._audit.append(("set", name))

    # ── 읽기 ────────────────────────────────────────────────────────────
    def get(self, name: str, now_min: int = 0, default: Any = None) -> Any:
        """만료·삭제된 항목은 존재하지 않는 것으로 취급한다."""
        if self.consent.expired(now_min):
            return default
        return self._data.get(name, default)

    def visible(self, now_min: int = 0) -> dict[str, Any]:
        """지금 이 시점에 응답 생성에 쓸 수 있는 맥락 전체."""
        if self.consent.expired(now_min):
            return {}
        return dict(self._data)

    # ── 삭제·수정 ───────────────────────────────────────────────────────
    def delete(self, name: str) -> None:
        """즉시 삭제. 이후 어떤 응답도 이 값을 재사용하지 않는다."""
        self._data.pop(name, None)
        self._audit.append(("delete", name))

    def revoke(self, name: str) -> None:
        """동의 자체를 철회한다(삭제 + 재기록 차단)."""
        self.delete(name)
        self.consent = replace(self.consent, fields=self.consent.fields - {name})
        self._audit.append(("revoke", name))

    def purge(self) -> None:
        self._data.clear()
        self._audit.append(("purge", "*"))

    @property
    def audit_log(self) -> list[tuple[str, str]]:
        """무엇을 언제 저장·삭제했는지 사용자에게 보여줄 기록."""
        return list(self._audit)
