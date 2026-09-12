/* 공통: API 호출, 이스케이프, 마크다운, 다크 모드, 페이지 간 공유 상태(sessionStorage). */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** fetch + 타임아웃 + 사용자용 오류 메시지. 서버 오류 본문을 그대로 노출하지 않는다. */
async function post(path, body, timeoutMs) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    let data = null;
    try { data = await res.json(); } catch { /* 본문이 JSON이 아닐 수 있다 */ }
    if (!res.ok) {
      const code = data && data.error;
      return { ok: false, code, message: ERRORS[code]
        || `Something went wrong on our side (HTTP ${res.status}). Please try again.` };
    }
    return { ok: true, data };
  } catch (e) {
    if (e.name === 'AbortError') {
      return { ok: false, code: 'TIMEOUT',
        message: `No response within ${Math.round(timeoutMs / 1000)} seconds. Please try again.` };
    }
    return { ok: false, code: 'NETWORK', message: "Can't reach the server. Check your connection." };
  } finally {
    clearTimeout(timer);
  }
}

/** 서버 오류 코드 → 여행자용 영어 안내. */
const ERRORS = {
  EMPTY_INPUT: 'Type a message first.',
  BAD_JSON: 'That request looked broken. Please try again.',
  BAD_DATE: 'Please pick a valid travel date.',
  BAD_CITIES: 'Choose 1 or 2 destinations.',
  NO_LLM_KEY: 'The AI service is not configured on the server yet.',
  RECOMMEND_FAILED: "We couldn't create a plan right now. Please try again in a moment.",
  RATE_LIMITED: "You're going a bit fast. Give it a minute and try again.",
  BUDGET_EXHAUSTED: "This demo has used up its AI budget for now. Please try again later.",
};

/** 리포트용 작은 마크다운 렌더러 (제목·목록·굵게). */
function renderMarkdown(md) {
  const out = [];
  let inList = false;
  for (const raw of String(md || '').split('\n')) {
    const line = raw.trimEnd();
    const flag = line.includes('<!-- ⚠️');
    const clean = line.replace(/<!--.*?-->/g, '').trimEnd();
    const bold = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    const m = clean.match(/^(#{1,6})\s+(.*)$/);
    if (m) {
      if (inList) { out.push('</ul>'); inList = false; }
      const lvl = Math.min(m[1].length + 1, 4);
      out.push(`<h${lvl}>${bold(m[2])}</h${lvl}>`);
      continue;
    }
    const li = clean.match(/^\s*(?:[-*+]|\d+\.)\s+(.*)$/);
    if (li) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${bold(li[1])}${flag ? ' <span class="flag">⚠️ not in search results</span>' : ''}</li>`);
      continue;
    }
    if (inList) { out.push('</ul>'); inList = false; }
    if (clean.trim() && !clean.startsWith('>')) out.push(`<p>${bold(clean)}</p>`);
    else if (clean.startsWith('>')) out.push(`<p class="hint">${bold(clean.slice(1).trim())}</p>`);
  }
  if (inList) out.push('</ul>');
  return out.join('');
}

/** 말풍선용 최소 서식: 이스케이프 후 **굵게** 만 살린다. 모델이 마크다운을 섞어 쓴다. */
function renderInline(text) {
  return esc(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|\s)\*(?!\s)([^*\n]+?)\*(?=\s|$|[.,!?])/g, '$1<em>$2</em>');
}

/** 저장소 접근은 실패할 수 있다(사생활 모드 등) — 항상 감싼다. */
const store = {
  get(k, fallback) { try { const v = sessionStorage.getItem(k); return v ? JSON.parse(v) : fallback; } catch { return fallback; } },
  set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch { /* 무시 */ } },
};

/* 다크 모드 (보너스: UX). 선택은 localStorage에 기억, 없으면 OS 설정을 따른다. */
(function theme() {
  let saved = null;
  try { saved = localStorage.getItem('theme'); } catch { /* 무시 */ }
  if (saved) document.documentElement.dataset.theme = saved;
  const btn = $('theme');
  if (!btn) return;
  const isDark = () => (document.documentElement.dataset.theme
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
  const paint = () => { btn.textContent = isDark() ? '☀️' : '🌙'; btn.setAttribute('aria-label', isDark() ? 'Switch to light mode' : 'Switch to dark mode'); };
  paint();
  btn.addEventListener('click', () => {
    const next = isDark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('theme', next); } catch { /* 무시 */ }
    paint();
  });
})();

/* 여행 리포트 공통: 채팅과 Trip Planner가 같은 API·표시 규칙을 쓴다. */
function todayPlus(days) {
  const d = new Date(Date.now() + days * 864e5);
  return d.toISOString().slice(0, 10);
}

function planTrip(date, cities) {
  return post('/api/travel', { date, cities: Number(cities) || 1 }, 60000);
}

/** 근거 검사 배지. 검사 0건(no_claim)은 '통과'가 아니다. */
function groundingBadge(g = {}) {
  const bad = (g.unsupported || []).length;
  if (bad) return `<span class="badge bad">${bad} not verified</span>${esc(g.unsupported.join(', '))}`;
  if (!g.checked) return '<span class="badge warn">Nothing to check</span>No restaurant names to match against search results';
  return `<span class="badge ok">✓ ${g.checked}/${g.checked} verified</span>All restaurant names found on ${esc((g.sources || []).join(', ') || 'map search')}`;
}

/** 채팅 맥락으로 넘길 리포트 텍스트 (주석 제거, 길이 제한은 서버에서도 한다). */
function reportContext(d) {
  return `Trip date: ${d.date}\n` + String(d.markdown || '').replace(/<!--.*?-->/g, '').slice(0, 2800);
}
