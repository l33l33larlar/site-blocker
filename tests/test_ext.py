"""End-to-end check of the Site Blocker extension (the folder above this one).

Usage: python3 test_ext.py [--full] [--shots DIR]
  --full   also sits through the 60-second removal wait
  --shots  where to save screenshots (default: a new temp folder)

The everyday Chrome profile is not touched: this starts a separate headless
Chrome with its own empty profile and loads the extension through the
DevTools pipe (Chrome no longer accepts --load-extension). Needs network
access for the "unlisted site still opens" checks.
"""
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True  # no __pycache__ inside the extension folder

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cdp import Chrome  # noqa: E402

EXT = os.path.dirname(HERE)
WORK = tempfile.mkdtemp(prefix="site-blocker-test-")
PROFILE = os.path.join(WORK, "profile")
SHOTS = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else os.path.join(WORK, "shots")

results = []
carry = {}  # values handed from the first launch to the second


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("  -> " + str(detail) if detail != "" else ""))


def shots(c, session, name):
    """Screenshot in both colour schemes."""
    for scheme in ("dark", "light"):
        c.send("Emulation.setEmulatedMedia",
               {"features": [{"name": "prefers-color-scheme", "value": scheme}]}, session=session)
        c.pump(0.3)
        c.screenshot(session, os.path.join(SHOTS, "%s_%s.png" % (name, scheme)))


def main():
    os.makedirs(SHOTS, exist_ok=True)
    try:
        c = Chrome(PROFILE)
        try:
            run(c)
        finally:
            c.close()
        c = Chrome(PROFILE)
        try:
            run_after_restart(c)
        finally:
            c.close()
    finally:
        shutil.rmtree(PROFILE, ignore_errors=True)
    print("\nscreenshots: " + SHOTS)
    print("%d/%d passed" % (sum(results), len(results)))
    sys.exit(0 if all(results) else 1)


def run_after_restart(c):
    """Second launch on the same profile: the list and the rules must still be there."""
    ext_id = c.send("Extensions.loadUnpacked", {"path": EXT})["id"]
    base = "chrome-extension://%s/" % ext_id
    c.pump(3)
    sw_s = c.attach(find(c, "service_worker", ext_id)["targetId"])
    hosts = c.evaluate(sw_s, "getSites().then(s => s.map(x => x.host))")
    check("list survives a restart unchanged", hosts == carry["hosts"], "%s sites" % len(hosts))
    n_rules = c.evaluate(sw_s, "chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
    check("rules survive a restart", n_rules == len(hosts), n_rules)
    t = c.open("https://www.reddit.com/")
    check("site added by hand is still blocked", c.url_of(t) == base + "blocked.html?site=reddit.com", c.url_of(t))
    hits = c.evaluate(sw_s, "getHits().then(h => Object.values(h)[0])")
    check("attempt count carries on", hits == carry["hits"] + 1, hits)

    # --- a copy installed as 1.0.0 (which stored a ready-made list) gets reloaded with this code:
    # that batch goes, sites added by hand stay
    c.evaluate(sw_s, """(async () => {
      const seed = Array.from({length: 39}, (_, i) => ({host: 'seed' + i + '.example', addedAt: 1000}));
      const mine = [{host: 'bbc.com', addedAt: 2000}, {host: 'reddit.com', addedAt: 3000}];
      await chrome.storage.local.remove('seedCleared');
      await chrome.storage.local.set({sites: seed.concat(mine)});
    })()""")
    c.pump(1.5)
    before = c.evaluate(sw_s, "chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
    c.send("Extensions.loadUnpacked", {"path": EXT})  # same folder again = the reload button
    c.pump(3)
    sw_s = c.attach(find(c, "service_worker", ext_id)["targetId"])
    hosts = c.evaluate(sw_s, "getSites().then(s => s.map(x => x.host))")
    check("reload clears the old preloaded list only", before == 41 and hosts == ["bbc.com", "reddit.com"],
          "%s rules before, now %s" % (before, hosts))
    n_rules = c.evaluate(sw_s, "chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
    check("rules follow", n_rules == 2, n_rules)
    t = c.open("http://seed0.example/")
    url = c.url_of(t) or ""
    check("a cleared site is no longer blocked", not url.startswith(base), url)
    c.send("Extensions.loadUnpacked", {"path": EXT})  # same folder again = the reload button
    c.pump(3)
    sw_s = c.attach(find(c, "service_worker", ext_id)["targetId"])
    hosts = c.evaluate(sw_s, "getSites().then(s => s.map(x => x.host))")
    check("a second reload changes nothing", hosts == ["bbc.com", "reddit.com"], hosts)


def find(c, kind, url_part):
    for t in c.targets():
        if t["type"] == kind and url_part in t["url"]:
            return t
    return None


def run(c):
    print("browser:", c.send("Browser.getVersion")["product"])
    ext_id = c.send("Extensions.loadUnpacked", {"path": EXT})["id"]
    base = "chrome-extension://%s/" % ext_id
    print("extension id:", ext_id)
    c.pump(3)

    # --- install: the list starts empty, options page opened
    sw = find(c, "service_worker", ext_id)
    check("service worker is running", sw is not None)
    sw_s = c.attach(sw["targetId"])
    n_sites = c.evaluate(sw_s, "getSites().then(s => s.length)")
    n_rules = c.evaluate(sw_s, "chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
    check("list starts empty", n_sites == 0 and n_rules == 0, "%s sites / %s rules" % (n_sites, n_rules))
    opt = find(c, "page", base + "options.html")
    check("options page opened on install", opt is not None)
    opt_s = c.attach(opt["targetId"])
    c.send("Page.enable", session=opt_s)
    text = c.evaluate(opt_s, "document.getElementById('empty').hidden ? '' : document.getElementById('empty').innerText")
    check("empty list explains how to add a site", "icon ကို နှိပ်" in text, text)
    shots(c, opt_s, "options_empty")

    # the sites the rest of the run works with, added the way the popup adds them
    for host in ("bbc.com", "cnn.com", "news.google.com", "example.org", "reuters.com"):
        c.evaluate(sw_s, "addSite(%s)" % json.dumps(host))
    c.pump(1.5)
    n_sites = c.evaluate(sw_s, "getSites().then(s => s.length)")
    n_rules = c.evaluate(sw_s, "chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
    check("one rule per added site", n_sites == 5 and n_rules == 5, "%s sites / %s rules" % (n_sites, n_rules))

    # --- blocking
    t_bbc = c.open("https://www.bbc.com/burmese")
    check("bbc.com/burmese is blocked", c.url_of(t_bbc) == base + "blocked.html?site=bbc.com", c.url_of(t_bbc))
    s_bbc = c.attach(t_bbc)
    text = c.evaluate(s_bbc, "document.body.innerText")
    check("blocked page shows site and count", "bbc.com" in text and "1 ကြိမ်" in text, text.replace("\n", " | "))
    c.send("Page.enable", session=s_bbc)
    shots(c, s_bbc, "blocked")

    t_cnn = c.open("https://edition.cnn.com/world")
    check("subdomain edition.cnn.com is blocked", c.url_of(t_cnn) == base + "blocked.html?site=cnn.com", c.url_of(t_cnn))
    t_gn = c.open("https://news.google.com/home")
    check("news.google.com is blocked", c.url_of(t_gn) == base + "blocked.html?site=news.google.com", c.url_of(t_gn))
    t_http = c.open("http://example.org/")
    check("plain http is blocked too", c.url_of(t_http) == base + "blocked.html?site=example.org", c.url_of(t_http))

    hits = c.evaluate(sw_s, "getHits().then(h => Object.values(h)[0])")
    check("attempts are counted", hits == 4, hits)

    t_ex = c.open("https://example.com/", wait=4)
    check("unlisted site still opens", c.url_of(t_ex) == "https://example.com/", c.url_of(t_ex))
    t_g = c.open("https://www.google.com/", wait=4)
    check("google.com itself is not blocked", (c.url_of(t_g) or "").startswith("https://www.google.com"), c.url_of(t_g))

    # --- options page: add a site, the open tab gets swept
    print("options visibility:", c.evaluate(opt_s, "document.visibilityState"))
    rows = c.evaluate(opt_s, "document.querySelectorAll('#list li').length")
    check("options lists every site", rows == n_sites, rows)

    add = """(async (v) => {
      document.getElementById('add-input').value = v;
      document.getElementById('add-form').requestSubmit();
      await new Promise(r => setTimeout(r, 1500));
      return document.getElementById('add-msg').textContent;
    })(%s)"""
    msg = c.evaluate(opt_s, add % json.dumps("https://www.Example.com/some/page"))
    check("add via form (URL gets cleaned)", "example.com ကို ပိတ်လိုက်ပါပြီ" in msg, msg)
    c.pump(1.5)
    check("already-open tab is swept", c.url_of(t_ex) == base + "blocked.html?site=example.com", c.url_of(t_ex))
    n_rules2 = c.evaluate(sw_s, "chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
    check("rule added", n_rules2 == n_rules + 1, n_rules2)

    msg = c.evaluate(opt_s, add % json.dumps("example.com"))
    check("duplicate is refused", "ပိတ်ထားပြီးသား" in msg, msg)
    msg = c.evaluate(opt_s, add % json.dumps("m.example.com"))
    check("covered subdomain is refused", "ပိတ်ထားပြီးသား" in msg, msg)
    msg = c.evaluate(opt_s, add % json.dumps("not a site"))
    check("garbage is refused", "မမှန်ပါ" in msg, msg)

    shots(c, opt_s, "options")

    # --- second net: tab update listener blocks even without a network rule
    c.evaluate(sw_s, """chrome.declarativeNetRequest.getDynamicRules().then(rs => {
      const r = rs.find(x => x.condition.requestDomains[0] === 'example.com');
      return chrome.declarativeNetRequest.updateDynamicRules({removeRuleIds: [r.id]});
    })""")
    t_ex2 = c.open("https://example.com/", wait=5)
    check("fallback listener blocks without a rule", c.url_of(t_ex2) == base + "blocked.html?site=example.com", c.url_of(t_ex2))

    # --- remove within grace: immediate
    click_remove = """(async (host) => {
      const row = document.querySelector('#list li[data-host="' + host + '"]');
      row.querySelector('button').click();
      await new Promise(r => setTimeout(r, 1200));
      const again = document.querySelector('#list li[data-host="' + host + '"]');
      return again ? again.querySelector('.site-actions').innerText : 'GONE';
    })(%s)"""
    state = c.evaluate(opt_s, click_remove % json.dumps("example.com"))
    check("fresh entry is removed at once", state == "GONE", state)
    t_ex3 = c.open("https://example.com/", wait=4)
    check("removed site opens again", c.url_of(t_ex3) == "https://example.com/", c.url_of(t_ex3))

    # --- remove an old entry: needs the wait
    c.evaluate(sw_s, """getSites().then(s => {
      for (const x of s) x.addedAt = 0;
      return chrome.storage.local.set({sites: s});
    })""")
    c.pump(1.5)
    state = c.evaluate(opt_s, click_remove % json.dumps("bbc.com"))
    check("old entry starts a countdown", "စက္ကန့် စောင့်ပါ" in state, state.replace("\n", " | "))
    still = c.evaluate(sw_s, "getSites().then(s => s.some(x => x.host === 'bbc.com'))")
    check("site stays blocked during the wait", still is True)
    shots(c, opt_s, "options_wait")

    # cancel works
    state = c.evaluate(opt_s, """(async () => {
      const row = document.querySelector('#list li[data-host="bbc.com"]');
      row.querySelector('button').click();
      await new Promise(r => setTimeout(r, 300));
      return document.querySelector('#list li[data-host="bbc.com"] .site-actions').innerText;
    })()""")
    check("countdown can be cancelled", state.strip() == "ဖယ်မယ်", state)

    # leaving the page resets the wait
    c.send("Page.bringToFront", session=opt_s)
    c.pump(0.5)
    print("options visibility after bringToFront:", c.evaluate(opt_s, "document.visibilityState"))
    state = c.evaluate(opt_s, click_remove % json.dumps("cnn.com"))
    check("countdown runs on the visible page", "စက္ကန့် စောင့်ပါ" in state, state.replace("\n", " | "))
    other = c.open("about:blank", wait=1)
    other_s = c.attach(other)
    c.send("Page.bringToFront", session=other_s)
    c.pump(1)
    vis = c.evaluate(opt_s, "document.visibilityState")
    state = c.evaluate(opt_s, "document.querySelector('#list li[data-host=\"cnn.com\"] .site-actions').innerText")
    check("switching tabs resets the wait", vis == "hidden" and state.strip() == "ဖယ်မယ်", "%s / %s" % (vis, state))
    c.send("Page.bringToFront", session=opt_s)
    c.pump(0.5)

    if "--full" in sys.argv:
        state = c.evaluate(opt_s, click_remove % json.dumps("bbc.com"))
        print("waiting 30s, then checking the countdown is on time ...")
        c.pump(29)
        state = c.evaluate(opt_s, "document.querySelector('#list li[data-host=\"bbc.com\"] .site-actions').innerText")
        left = int(state.split()[0]) if state.split() and state.split()[0].isdigit() else -1
        check("countdown keeps real time", 28 <= left <= 31, state.replace("\n", " | "))
        c.pump(32)
        state = c.evaluate(opt_s, "document.querySelector('#list li[data-host=\"bbc.com\"] .site-actions').innerText")
        check("confirm button appears after the wait", "အခု ဖယ်မယ်" in state, state.replace("\n", " | "))
        state = c.evaluate(opt_s, click_remove % json.dumps("bbc.com"))
        check("confirm removes the site", state == "GONE", state)

    # --- helpers
    cases = c.evaluate(opt_s, """JSON.stringify([
      normalizeSite('HTTPS://WWW.BBC.com/burmese?x=1'), normalizeSite('bbc.co.uk'), normalizeSite('news.google.com/'),
      normalizeSite('chrome://extensions'), normalizeSite(''), normalizeSite('localhost'),
      baseDomain('edition.cnn.com'), baseDomain('www.bbc.co.uk'), baseDomain('burmese.dvb.no'),
      baseDomain('news.gnlm.com.mm'), baseDomain('cnn.com')])""")
    expect = ["bbc.com", "bbc.co.uk", "news.google.com", None, None, None,
              "cnn.com", "bbc.co.uk", "dvb.no", "gnlm.com.mm", "cnn.com"]
    check("name helpers", json.loads(cases) == expect, cases)

    # --- popup, with the active tab faked to be a news page
    for name, url in (("popup_sub", "https://live.somenews.co.uk/post/1"), ("popup_plain", "https://www.reddit.com/r/news"),
                      ("popup_blocked", "https://www.reuters.com/world"), ("popup_shared", "https://finance.yahoo.com/x"),
                      ("popup_internal", "chrome://extensions/")):
        tid = c.open("about:blank", wait=0.5)
        s = c.attach(tid)
        c.send("Page.enable", session=s)
        c.send("Emulation.setDeviceMetricsOverride",
               {"width": 320, "height": 260, "deviceScaleFactor": 2, "mobile": False}, session=s)
        c.send("Page.addScriptToEvaluateOnNewDocument", {"source": """
          if (window.chrome && chrome.tabs) {
            chrome.tabs.query = async () => [{id: 1, url: %s}];
          }""" % json.dumps(url)}, session=s)
        c.send("Page.navigate", {"url": base + "popup.html"}, session=s)
        c.pump(1.5)
        text = c.evaluate(s, "document.body.innerText")
        print("  [%s] %s" % (name, text.replace("\n", " | ")))
        drawn = c.evaluate(s, "Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).length")
        want = {"popup_sub": 2, "popup_plain": 1, "popup_blocked": 0, "popup_shared": 2, "popup_internal": 0}[name]
        check("%s shows %d button(s)" % (name, want), drawn == want, drawn)
        shots(c, s, name)
        if name == "popup_sub":
            btns = c.evaluate(s, "Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => b.textContent).join(' / ')")
            check("popup offers whole site first", btns.startswith("somenews.co.uk တစ်ခုလုံး") and "live.somenews.co.uk ကိုပဲ" in btns, btns)
        if name == "popup_shared":
            btns = c.evaluate(s, "Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => b.textContent).join(' / ')")
            check("popup offers exact host first on shared domains", btns.startswith("finance.yahoo.com ကိုပဲ") and "yahoo.com တစ်ခုလုံး" in btns, btns)
        if name == "popup_internal":
            check("popup refuses browser pages", "ပိတ်လို့ မရပါ" in text, "")
        if name == "popup_plain":
            c.evaluate(s, "document.getElementById('block-main').click(); new Promise(r => setTimeout(r, 600))")
            added = c.evaluate(sw_s, "getSites().then(s => s.some(x => x.host === 'reddit.com'))")
            check("popup button blocks the site", added is True)
        if name == "popup_blocked":
            check("popup knows a blocked site", "ပိတ်ထားပြီးသား" in text, "")

    final_rules = c.evaluate(sw_s, "chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
    final_sites = c.evaluate(sw_s, "getSites().then(s => s.length)")
    check("rules match the list at the end", final_rules == final_sites, "%s rules / %s sites" % (final_rules, final_sites))
    carry["hosts"] = c.evaluate(sw_s, "getSites().then(s => s.map(x => x.host))")
    carry["hits"] = c.evaluate(sw_s, "getHits().then(h => Object.values(h)[0])")


if __name__ == "__main__":
    main()
