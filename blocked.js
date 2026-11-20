'use strict';

(async function () {
  const LINES = [
    'ဒီဆိုက်ကို နောက်မှ ကြည့်လည်း ရပါတယ်။ အခု လုပ်စရာရှိတာကို ဆက်လုပ်လိုက်ပါ။',
    'အသက်တစ်ချက် ပြင်းပြင်းရှူပြီး ဒီ tab ကို ပိတ်လိုက်ပါ။',
    'တကယ်အရေးကြီးတာဆိုရင် မကြည့်လည်း သိလာမှာပါ။',
    'ဖွင့်ချင်စိတ်က ခဏနေရင် ပျောက်သွားပါလိမ့်မယ်။',
  ];

  const site = normalizeSite(new URLSearchParams(location.search).get('site')) || '';
  document.getElementById('site').textContent = site;
  document.getElementById('line').textContent = LINES[Math.floor(Math.random() * LINES.length)];
  if (site) document.title = site + ' — ပိတ်ထားပါတယ်';

  document.getElementById('close').addEventListener('click', async () => {
    const tab = await chrome.tabs.getCurrent();
    if (tab) chrome.tabs.remove(tab.id);
  });

  const today = await recordHit(site);
  document.getElementById('count').textContent =
    'ဒီနေ့ ပိတ်ထားတဲ့ဆိုက်တွေကို ဖွင့်ဖို့ကြိုးစားတာ ' + today + ' ကြိမ် ရှိပါပြီ။';
})();
