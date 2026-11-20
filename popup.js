'use strict';

(async function () {
  const $ = (id) => document.getElementById(id);
  const hostEl = $('host');
  const statusEl = $('status');
  const mainBtn = $('block-main');
  const altBtn = $('block-alt');

  function showStatus(text) {
    statusEl.textContent = text;
    statusEl.hidden = false;
  }

  async function refreshSummary() {
    const sites = await getSites();
    const hits = await getHits();
    const today = hits[dayKey(new Date())] || 0;
    $('summary').textContent =
      'ပိတ်ထားတာ ' + sites.length + ' ဆိုက် · ဒီနေ့ ဖွင့်ဖို့ကြိုးစားတာ ' + today + ' ကြိမ်';
  }

  async function block(site) {
    mainBtn.hidden = true;
    altBtn.hidden = true;
    const result = await addSite(site);
    showStatus(result.ok ? site + ' ကို ပိတ်လိုက်ပါပြီ။' : 'ပိတ်ထားပြီးသားပါ (' + result.by + ')။');
    await refreshSummary();
    if (result.ok) setTimeout(() => window.close(), 1200);
  }

  $('open-list').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });

  await refreshSummary();

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = (tab && tab.url) || '';

  if (url.startsWith(chrome.runtime.getURL('blocked.html'))) {
    hostEl.textContent = new URL(url).searchParams.get('site') || '';
    showStatus('ဒီဆိုက်ကို ပိတ်ထားပြီးသားပါ။');
    return;
  }

  const host = /^https?:/i.test(url) ? normalizeSite(url) : null;
  if (!host) {
    hostEl.textContent = '—';
    showStatus('ဒီစာမျက်နှာကို ပိတ်လို့ မရပါ။');
    return;
  }

  hostEl.textContent = host;
  const covering = findCovering(await getSites(), host);
  if (covering) {
    showStatus('ဒီဆိုက်ကို ပိတ်ထားပြီးသားပါ။');
    return;
  }

  const base = baseDomain(host);
  if (base === host) {
    mainBtn.textContent = host + ' ကို ပိတ်မယ်';
    mainBtn.addEventListener('click', () => block(host));
    mainBtn.hidden = false;
    return;
  }

  // The page is on a subdomain: offer the whole site and the exact host.
  // For domains shared by unrelated services the exact host comes first.
  const hostFirst = SHARED_DOMAINS.includes(base);
  const whole = { site: base, text: base + ' တစ်ခုလုံးကို ပိတ်မယ်' };
  const exact = { site: host, text: host + ' ကိုပဲ ပိတ်မယ်' };
  const first = hostFirst ? exact : whole;
  const second = hostFirst ? whole : exact;
  mainBtn.textContent = first.text;
  mainBtn.addEventListener('click', () => block(first.site));
  mainBtn.hidden = false;
  altBtn.textContent = second.text;
  altBtn.addEventListener('click', () => block(second.site));
  altBtn.hidden = false;
})();
