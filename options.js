'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const listEl = $('list');

  // Removals in progress: host -> { readyAt, expiresAt, timer, shown, waitEl }.
  // Before readyAt the row shows a countdown; from readyAt until expiresAt it
  // shows the confirm button. Times are wall-clock, so a slowed timer cannot
  // stretch or shorten the wait.
  const pending = new Map();
  let sites = [];

  $('rule-note').textContent =
    'ဆိုက်တစ်ခုကို စာရင်းက ဖယ်ချင်ရင် ' + REMOVE_WAIT_SECONDS + ' စက္ကန့် စောင့်ရပါမယ် ' +
    '(စိတ်လိုက်မာန်ပါ ပြန်ဖွင့်မိတာကို တားဖို့ပါ)။ ထည့်ပြီး ' + GRACE_MINUTES +
    ' မိနစ်အတွင်းဆိုရင်တော့ ချက်ချင်း ဖယ်လို့ရပါတယ်။';

  function button(text, className, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = className;
    b.textContent = text;
    b.addEventListener('click', onClick);
    return b;
  }

  function cancelPending(host) {
    const p = pending.get(host);
    if (!p) return;
    clearInterval(p.timer);
    pending.delete(host);
  }

  function startRemoval(site) {
    if (inGrace(site)) {
      removeSite(site.host);
      return;
    }
    const readyAt = Date.now() + REMOVE_WAIT_SECONDS * 1000;
    const p = {
      readyAt,
      expiresAt: readyAt + REMOVE_CONFIRM_SECONDS * 1000,
      timer: setInterval(() => tick(site), 250),
      shown: null,
      waitEl: null,
    };
    pending.set(site.host, p);
    renderActions(site);
  }

  function phaseOf(p) {
    return Date.now() >= p.readyAt ? 'ready' : 'waiting';
  }

  function waitText(p) {
    return Math.max(1, Math.ceil((p.readyAt - Date.now()) / 1000)) + ' စက္ကန့် စောင့်ပါ';
  }

  function tick(site) {
    const p = pending.get(site.host);
    if (!p) return;
    if (Date.now() >= p.expiresAt) {
      cancelPending(site.host);
      renderActions(site);
    } else if (phaseOf(p) !== p.shown) {
      renderActions(site);
    } else if (p.waitEl) {
      // Only the text changes between phases: the buttons stay the same
      // elements, so a click is never lost to a redraw.
      p.waitEl.textContent = waitText(p);
    }
  }

  function renderActions(site) {
    const row = listEl.querySelector('li[data-host="' + site.host + '"]');
    if (!row) return;
    const box = row.querySelector('.site-actions');
    box.textContent = '';
    const p = pending.get(site.host);
    if (!p) {
      box.append(button('ဖယ်မယ်', 'btn btn-small', () => startRemoval(site)));
      return;
    }
    const cancel = button('မဖယ်တော့ဘူး', 'btn btn-small', () => {
      cancelPending(site.host);
      renderActions(site);
    });
    p.shown = phaseOf(p);
    p.waitEl = null;
    if (p.shown === 'waiting') {
      p.waitEl = document.createElement('span');
      p.waitEl.className = 'wait';
      p.waitEl.textContent = waitText(p);
      box.append(p.waitEl, cancel);
    } else {
      const confirm = button('အခု ဖယ်မယ်', 'btn btn-small btn-danger', () => {
        if (Date.now() < p.readyAt) return;
        cancelPending(site.host);
        removeSite(site.host);
      });
      box.append(confirm, cancel);
    }
  }

  function renderList() {
    const hosts = new Set(sites.map((s) => s.host));
    for (const host of Array.from(pending.keys())) {
      if (!hosts.has(host)) cancelPending(host);
    }
    listEl.textContent = '';
    for (const site of sites) {
      const li = document.createElement('li');
      li.dataset.host = site.host;
      const name = document.createElement('span');
      name.className = 'site-name';
      name.textContent = site.host;
      const actions = document.createElement('span');
      actions.className = 'site-actions';
      li.append(name, actions);
      listEl.append(li);
      renderActions(site);
    }
    $('list-title').textContent = 'ပိတ်ထားတဲ့ဆိုက်များ (' + sites.length + ')';
    $('empty').hidden = sites.length > 0;
  }

  async function renderStats() {
    const hits = await getHits();
    const days = [];
    for (let i = 6; i >= 0; i -= 1) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      days.push({ date, count: hits[dayKey(date)] || 0 });
    }
    const max = Math.max(1, ...days.map((d) => d.count));
    const box = $('stats');
    box.textContent = '';
    for (const d of days) {
      const col = document.createElement('div');
      col.className = 'stat';
      const count = document.createElement('span');
      count.className = 'stat-count';
      count.textContent = d.count;
      const track = document.createElement('span');
      track.className = 'stat-track';
      const bar = document.createElement('span');
      bar.className = 'stat-bar';
      bar.style.height = Math.round((d.count / max) * 100) + '%';
      track.append(bar);
      const label = document.createElement('span');
      label.className = 'stat-day';
      label.textContent = d.date.getDate() + '/' + (d.date.getMonth() + 1);
      col.append(count, track, label);
      box.append(col);
    }
  }

  async function load() {
    sites = await getSites();
    renderList();
  }

  function showAddMessage(text, isError) {
    const el = $('add-msg');
    el.textContent = text;
    el.classList.toggle('error', Boolean(isError));
    el.hidden = false;
  }

  $('add-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('add-input');
    const host = normalizeSite(input.value);
    if (!host) {
      showAddMessage('ဆိုက်နာမည် မမှန်ပါ။ example.com လိုမျိုး ရိုက်ထည့်ပါ။', true);
      return;
    }
    const result = await addSite(host);
    if (!result.ok) {
      showAddMessage(host + ' က ပိတ်ထားပြီးသားပါ (' + result.by + ')။', true);
      return;
    }
    input.value = '';
    showAddMessage(host + ' ကို ပိတ်လိုက်ပါပြီ။', false);
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (changes.sites) load();
    if (changes.hits) renderStats();
  });

  // The wait only counts while this page is being looked at.
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) return;
    for (const host of Array.from(pending.keys())) cancelPending(host);
    renderList();
  });

  load();
  renderStats();
})();
