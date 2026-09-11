/* Trip Planner 페이지: 입력 검증 → /api/travel → 리포트·근거·오류 표시 → 채팅으로 이어가기. */
(function () {
  const out = $('travel-out');
  const err = $('travel-err');
  $('date').value = todayPlus(14);
  $('date').min = todayPlus(0);
  let busy = false;
  let last = null;

  $('trip-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy) return;                                   // 중복 제출 방지
    const date = $('date').value;
    if (!date) { err.textContent = 'Please pick a travel date.'; err.hidden = false; return; }  // ① 빈 입력
    err.hidden = true;
    busy = true;
    $('make').disabled = true;
    $('make').textContent = 'Planning…';
    out.className = 'card result';
    out.innerHTML = '<p class="hint">Mate is picking destinations, searching Kakao Map for food and writing your plan…</p>' +
      '<div class="skeleton" style="width:60%"></div><div class="skeleton"></div><div class="skeleton" style="width:80%"></div>' +
      '<div class="skeleton" style="width:70%"></div><div class="skeleton"></div>';

    const r = await planTrip(date, $('cities').value);
    busy = false;
    $('make').disabled = false;
    $('make').textContent = 'Create my plan';

    if (!r.ok) {                                        // ②③ API 오류 / 타임아웃 — 입력은 그대로 둔다
      out.className = 'card result empty';
      out.innerHTML = last ? '<div><p>Showing nothing new. Your previous plan is below the error.</p></div>' : '<div><div style="font-size:42px">😕</div><p>No plan this time.</p></div>';
      err.textContent = r.message; err.hidden = false;
      return;
    }
    last = r.data;
    render(r.data);
  });

  function render(d) {
    const g = d.grounding || {};
    const errs = (d.errors || []).filter((x) => !x.fell_back);
    const partial = d.status === 'partial'
      ? '<p class="err" style="margin:0 0 14px">Some steps failed, so this plan may be incomplete. See details below.</p>' : '';
    out.className = 'card result fade-in';
    out.innerHTML = `${partial}<div class="report">${renderMarkdown(d.markdown)}</div>` +
      `<div class="checks"><div>${groundingBadge(g)}</div>` +
      '<div class="hint" style="margin-top:6px">Weather and events are AI estimates, not confirmed.</div>' +
      (errs.length ? `<details><summary>${errs.length} issue(s) while planning</summary><ul>${errs.map((x) =>
        `<li><code>${esc(x.step)}${x.city ? ' / ' + esc(x.city) : ''}</code> ${esc(x.type)}</li>`).join('')}</ul></details>` : '') +
      '</div><div class="result-actions">' +
      '<button class="btn" id="to-chat" type="button">💬 Ask Mate about this plan</button>' +
      '<button class="btn ghost" id="again" type="button">Plan another day</button></div>';
    $('to-chat').addEventListener('click', () => {
      // 이동만 한다 — 추가 AI 호출 없음. 채팅 페이지가 이 리포트를 대화 맥락으로 쓴다.
      store.set('pendingPlan', { date: d.date, markdown: d.markdown, grounding: g, cities: d.cities });
      location.href = '/chat.html';
    });
    $('again').addEventListener('click', () => { $('date').focus(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
  }
})();
