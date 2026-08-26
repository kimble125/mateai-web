'use strict';

/* MateAI 웹 데모
 *
 * 실패 처리 세 가지를 모두 다룬다(과제 요구 5번).
 *   · 빈 입력      — 요청을 보내기 전에 막고 안내한다
 *   · API 오류     — 4xx/5xx의 서버 메시지를 그대로 보여 준다
 *   · 지연/타임아웃 — AbortController로 끊고 안내한다
 */

const $ = (id) => document.getElementById(id);

/** 타임아웃이 있는 POST. 실패는 예외가 아니라 {ok,data} 로 돌려준다. */
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
      return { ok: false, message: (data && data.message)
        || `서버 오류 (HTTP ${res.status}). 잠시 후 다시 시도해 주세요.` };
    }
    return { ok: true, data };
  } catch (e) {
    if (e.name === 'AbortError') {
      return { ok: false, message: `응답이 ${Math.round(timeoutMs / 1000)}초 안에 오지 않았습니다. 다시 시도해 주세요.` };
    }
    return { ok: false, message: '네트워크에 연결할 수 없습니다. 연결을 확인해 주세요.' };
  } finally {
    clearTimeout(timer);
  }
}

function showError(el, message) {
  el.textContent = message;
  el.hidden = false;
}
function clearError(el) { el.hidden = true; el.textContent = ''; }

const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ── 섹션 2: 라이브 챗 ─────────────────────────────────────── */
const chat = {
  delayed: false,
  previousMode: 'companion',
  busy: false,

  init() {
    $('send').addEventListener('click', () => this.send());
    $('utterance').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.isComposing) this.send();
    });
    $('toggle').addEventListener('click', () => this.toggle());
  },

  toggle() {
    this.delayed = !this.delayed;
    $('toggle').textContent = this.delayed ? '정시로 되돌리기' : '지연 발생';
    $('state-hint').textContent = this.delayed
      ? '현재 상태: 항공편 지연 — 긴급도가 올라가 가이드 모드로 넘어갑니다'
      : '현재 상태: 정시 · 컴패니언 모드로 시작합니다';
  },

  bubble(cls, text) {
    const div = document.createElement('div');
    div.className = `msg ${cls}`;
    div.textContent = text;
    $('feed').appendChild(div);
    div.scrollIntoView({ block: 'nearest' });
    return div;
  },

  async send() {
    if (this.busy) return;
    const input = $('utterance');
    const text = input.value.trim();
    const err = $('chat-err');

    if (!text) {                                   // ① 빈 입력
      showError(err, '메시지를 입력해 주세요.');
      input.focus();
      return;
    }
    clearError(err);
    this.bubble('me', text);
    input.value = '';

    this.busy = true;
    $('send').disabled = true;
    const pending = this.bubble('ai', '…');
    pending.innerHTML = '<span class="spinner"></span>생각하는 중';

    const r = await post('/api/chat', {
      utterance: text,
      delayed: this.delayed,
      previous_mode: this.previousMode,
      event_fired: this.delayed,
    }, 30000);

    $('send').disabled = false;
    this.busy = false;

    if (!r.ok) {                                   // ②③ API 오류 / 타임아웃
      pending.remove();
      showError(err, r.message);
      return;
    }

    const t = r.data;
    pending.className = `msg ai ${t.mode}`;
    pending.textContent = t.text;
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = `${t.mode.toUpperCase()} · 긴급도 ${t.urgency} · LLM 호출 ${t.llm_calls}회 · ${t.latency_ms}ms`;
    pending.appendChild(meta);

    this.previousMode = t.mode;
    this.inspect(t);
  },

  inspect(t) {
    const zero = t.llm_calls === 0;
    const rows = [
      ['모드', t.mode === 'guide' ? '가이드 (사실 안내)' : '컴패니언 (캐릭터)'],
      ['긴급도', t.urgency],
      ['토큰 상한', t.max_tokens],
      ['응답 생성기', t.generator],
      ['LLM 호출', `${t.llm_calls}회`, zero ? 'zero' : 'paid'],
      ['응답 시간', `${t.latency_ms} ms`, zero ? 'zero' : 'paid'],
      ['페르소나 일치', t.persona],
      ['라우팅 근거', t.rationale],
    ];
    if (t.grounding) {
      rows.push(['근거 검사', `${t.grounding.verdict} (${t.grounding.score})`]);
      if (t.grounding.removed && t.grounding.removed.length) {
        rows.push(['잘라낸 주장', t.grounding.removed.join(', '), 'paid']);
      }
      if (t.grounding.citations && t.grounding.citations.length) {
        rows.push(['출처', t.grounding.citations.join(' · ')]);
      }
    }
    if (t.options && t.options.length) {
      rows.push(['탑승 가능 열차',
        t.options.map((o) => `${o.label}. ${o.name} ${o.dep}→${o.arr}`).join(' / ')]);
    }
    $('kv').innerHTML = rows.map(([k, v, cls]) =>
      `<div class="kv"><span class="k">${esc(k)}</span>` +
      `<span class="v ${cls || ''}">${esc(v)}</span></div>`).join('');
    $('inspector').hidden = false;
  },
};

/* ── 섹션 3: 여행 리포트 ───────────────────────────────────── */
const travel = {
  busy: false,

  init() {
    const d = new Date();
    d.setDate(d.getDate() + 14);
    $('date').value = d.toISOString().slice(0, 10);
    $('make').addEventListener('click', () => this.run());
  },

  async run() {
    if (this.busy) return;
    const err = $('travel-err');
    const date = $('date').value;

    if (!date) {                                   // ① 빈 입력
      showError(err, '여행 날짜를 선택해 주세요.');
      return;
    }
    clearError(err);

    this.busy = true;
    $('make').disabled = true;
    $('travel-out').innerHTML =
      '<div class="report"><span class="spinner"></span>' +
      'AI가 지역을 고르고, 지도에서 맛집을 찾고, 리포트를 쓰는 중입니다 … (15~30초)</div>';

    const r = await post('/api/travel',
      { date, cities: Number($('cities').value) || 1 }, 60000);

    $('make').disabled = false;
    this.busy = false;

    if (!r.ok) {                                   // ②③ API 오류 / 타임아웃
      $('travel-out').innerHTML = '';
      showError(err, r.message);
      return;
    }
    this.render(r.data);
  },

  render(d) {
    const g = d.grounding || {};
    const ok = !g.unsupported || g.unsupported.length === 0;
    const badge = ok
      ? `<span class="badge ok">근거 검사 통과</span>가게 이름 ${g.checked || 0}건 전부 검색 결과와 일치`
      : `<span class="badge bad">근거 없음 ${g.unsupported.length}건</span>${esc(g.unsupported.join(', '))}`;

    const errs = (d.errors || []).length
      ? `<h3>오류 요약 (errors)</h3><ul>${d.errors.map((e) =>
          `<li><code>${esc(e.step)}${e.city ? '/' + esc(e.city) : ''}</code> ` +
          `<strong>${esc(e.type)}</strong> — ${esc(String(e.message).slice(0, 160))}</li>`).join('')}</ul>`
      : '<h3>오류 요약 (errors)</h3><ul><li>없음</li></ul>';

    $('travel-out').innerHTML =
      `<div class="report">${this.markdown(d.markdown)}` +
      `<hr><p style="margin:0 0 8px">${badge}</p>` +
      `<p class="hint">맛집 출처: ${esc((g.sources || []).join(', ') || '없음')} · ` +
      `날씨·행사는 AI 추정이며 확정 정보가 아닙니다.</p>${errs}</div>`;
    $('travel-out').scrollIntoView({ behavior: 'smooth', block: 'start' });
  },

  /** 아주 작은 마크다운 렌더러. 리포트가 쓰는 문법만 처리한다. */
  markdown(md) {
    const out = [];
    let inList = false;
    for (const raw of String(md || '').split('\n')) {
      const line = raw.trimEnd();
      const flag = line.includes('<!-- ⚠️');
      const clean = line.replace(/<!--.*?-->/g, '').trimEnd();
      const m = clean.match(/^(#{1,6})\s+(.*)$/);
      if (m) {
        if (inList) { out.push('</ul>'); inList = false; }
        const lvl = Math.min(m[1].length + 1, 4);
        out.push(`<h${lvl}>${esc(m[2])}</h${lvl}>`);
        continue;
      }
      const li = clean.match(/^\s*(?:[-*+]|\d+\.)\s+(.*)$/);
      if (li) {
        if (!inList) { out.push('<ul>'); inList = true; }
        const body = esc(li[1]).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        out.push(`<li>${body}${flag ? ' <span class="flag">⚠️ 검색 결과에 없음</span>' : ''}</li>`);
        continue;
      }
      if (inList) { out.push('</ul>'); inList = false; }
      if (clean.trim()) {
        out.push(`<p>${esc(clean).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</p>`);
      }
    }
    if (inList) out.push('</ul>');
    return out.join('');
  },
};

chat.init();
travel.init();
