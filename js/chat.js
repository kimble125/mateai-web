/* Chat 페이지: 대화 기록을 보내 자연스러운 이어 말하기, 채팅 안에서 여행 리포트 받기.
   대화는 이 탭의 sessionStorage에만 저장된다 (페이지를 옮겨도 유지, 탭을 닫으면 삭제). */
(function () {
  const feed = $('feed');
  const input = $('utterance');
  const err = $('chat-err');
  const KEY = 'mateChat';
  const WELCOME = "Hey, welcome to Korea! 👋 I'm Mate, your local friend. Ask me about food, places, getting around, or say \"plan a trip\" and I'll make you a day plan.";

  // state.messages: {role:'user'|'mate'|'report'|'system', text?, meta?, plan?, fallback?, options?}
  let state = store.get(KEY, null) || { messages: [{ role: 'mate', text: WELCOME }], context: '', mode: 'companion' };
  let busy = false;
  let fireEvent = false;

  const save = () => store.set(KEY, state);
  // 리포트처럼 큰 말풍선은 배치·폰트 로드 뒤에야 높이가 확정된다. 두 프레임 뒤에 내린다.
  const jump = () => { feed.scrollTop = feed.scrollHeight; };
  const scroll = () => requestAnimationFrame(() => requestAnimationFrame(jump));

  function bubble(m) {
    const el = document.createElement('div');
    if (m.role === 'report') {
      el.className = 'bubble mate report';
      el.innerHTML = `<div class="report">${renderMarkdown(m.plan.markdown)}</div>` +
        `<div class="checks" style="margin-top:10px">${groundingBadge(m.plan.grounding)}` +
        '<div class="hint" style="margin-top:4px">Weather and events are estimates. Ask me anything about this plan!</div></div>';
    } else {
      el.className = `bubble ${m.role}${m.fallback ? ' fallback' : ''}`;
      el.innerHTML = renderInline(m.text);
      if (m.options && m.options.length) {
        const box = document.createElement('div');
        box.className = 'options';
        box.innerHTML = m.options.map((o) =>
          `<div class="option"><strong>${esc(o.label)}. ${esc(o.name)}</strong> ${esc(o.dep)} → ${esc(o.arr)}<br><span class="hint">${esc(o.reason)}</span></div>`).join('');
        el.appendChild(box);
      }
      if (m.meta) {
        const meta = document.createElement('span');
        meta.className = 'meta';
        meta.textContent = m.meta;
        el.appendChild(meta);
      }
    }
    feed.appendChild(el);
    return el;
  }

  function add(m) { state.messages.push(m); save(); bubble(m); scroll(); }

  function typing() {
    const el = document.createElement('div');
    el.className = 'bubble mate typing';
    el.setAttribute('aria-label', 'Mate is typing');
    el.innerHTML = '<i></i><i></i><i></i>';
    feed.appendChild(el); scroll();
    return el;
  }

  /** 서버에 보낼 최근 대화 (리포트·시스템 문구 제외). */
  function history() {
    return state.messages.filter((m) => m.role === 'user' || m.role === 'mate')
      .slice(-12).map((m) => ({ role: m.role, text: m.text }));
  }

  function showErr(msg) { err.textContent = msg; err.hidden = false; }

  async function send(text) {
    const utterance = text.trim();
    if (busy) return;
    if (!utterance) { showErr('Type a message first.'); input.focus(); return; }   // ① 빈 입력
    if (/^\/?plan( a)? trip\b|^plan my trip/i.test(utterance)) { openPlanner(); input.value = ''; return; }
    err.hidden = true;
    const past = history();                  // 이번 발화는 utterance로 따로 보낸다
    add({ role: 'user', text: utterance });
    input.value = ''; autosize();
    busy = true; $('send').disabled = true;
    const dots = typing();

    const r = await post('/api/chat', {
      utterance, history: past, context: state.context || '',
      delayed: $('delayed').checked, event_fired: fireEvent, previous_mode: state.mode,
    }, 30000);
    dots.remove();
    busy = false; $('send').disabled = false;
    fireEvent = false;

    if (!r.ok) {                               // ②③ API 오류 / 타임아웃: 입력을 되돌려 재시도 쉽게
      state.messages.pop(); save(); feed.lastChild && feed.lastChild.remove();
      input.value = utterance; autosize();
      showErr(r.message);
      return;
    }
    const d = r.data;
    state.mode = d.mode || state.mode;
    const guide = d.mode === 'guide';
    add({
      role: 'mate', text: d.text,
      fallback: !guide && d.ai_generated === false,
      options: guide ? d.options : null,
      meta: guide ? 'Timetable answer · no AI guessing (sample data)'
        : d.ai_generated === false ? `Couldn't reach the AI · ${d.generator}` : null,
    });
    input.focus();
  }

  /* ── 채팅 안에서 여행 리포트 받기 ── */
  function openPlanner() {
    $('trip-inline').hidden = false;
    $('chat-date').value = $('chat-date').value || todayPlus(14);
    $('chat-date').min = todayPlus(0);
    $('chat-date').focus();
  }
  $('plan-chip').addEventListener('click', openPlanner);
  $('chat-plan-cancel').addEventListener('click', () => { $('trip-inline').hidden = true; });
  $('trip-inline').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy) return;
    const date = $('chat-date').value;
    if (!date) { showErr('Please pick a travel date.'); return; }
    err.hidden = true;
    const n = $('chat-cities').value;
    add({ role: 'user', text: `Can you plan a trip for ${date}? (${n} destination${n === '2' ? 's' : ''})` });
    $('trip-inline').hidden = true;
    busy = true; $('send').disabled = true; $('chat-plan').disabled = true;
    const dots = typing();
    const r = await planTrip(date, n);
    dots.remove();
    busy = false; $('send').disabled = false; $('chat-plan').disabled = false;
    if (!r.ok) { add({ role: 'mate', text: `Hmm, I couldn't make the plan: ${r.message}`, fallback: true }); return; }
    attachPlan(r.data, `Here's your plan for ${r.data.date}! 🗺️`);
  });

  /** 리포트를 대화에 붙이고 이후 답변의 맥락으로 쓴다. AI 추가 호출 없음. */
  function attachPlan(d, intro) {
    add({ role: 'mate', text: intro });
    add({ role: 'report', plan: { date: d.date, markdown: d.markdown, grounding: d.grounding || {} } });
    state.context = reportContext(d); save();
    $('plan-note').hidden = false;
    $('plan-note').textContent = `📌 Mate is using your ${d.date} trip plan as context.`;
  }

  /* ── 기타 UI ── */
  function autosize() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; }
  input.addEventListener('input', autosize);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(input.value); }
  });
  $('composer').addEventListener('submit', (e) => { e.preventDefault(); send(input.value); });
  document.querySelectorAll('#chips .chip:not(#plan-chip)').forEach((c) =>
    c.addEventListener('click', () => send(c.textContent)));
  $('delayed').addEventListener('change', (e) => {
    fireEvent = e.target.checked;
    add({ role: 'system', text: e.target.checked
      ? '✈️ Demo: your flight is now delayed. Ask Mate which train to take.'
      : '✈️ Demo: flight back on time.' });
  });
  $('reset').addEventListener('click', () => {
    state = { messages: [{ role: 'mate', text: WELCOME }], context: '', mode: 'companion' };
    save(); feed.innerHTML = ''; state.messages.forEach(bubble);
    $('plan-note').hidden = true; $('delayed').checked = false;
  });

  // 첫 렌더 + Trip Planner에서 넘어온 리포트
  state.messages.forEach(bubble);
  if (state.context) { $('plan-note').hidden = false; $('plan-note').textContent = '📌 Mate is using your trip plan as context.'; }
  const pending = store.get('pendingPlan', null);
  if (pending) {
    store.set('pendingPlan', null);
    attachPlan(pending, `I got your plan for ${pending.date}. Ask me anything about it! 😊`);
  }
  scroll();
  window.addEventListener('load', jump);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(jump).catch(() => {});
})();
