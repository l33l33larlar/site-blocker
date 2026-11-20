'use strict';

// Shared by the background service worker and every extension page.

// The block list starts empty: sites are added from the toolbar popup or the
// list page. Each entry ({ host, addedAt }) also covers the host's subdomains.

// Removing a site needs this long a wait, so an impulse cannot undo the block.
const REMOVE_WAIT_SECONDS = 60;
// After the wait, the confirm button stays available this long.
const REMOVE_CONFIRM_SECONDS = 30;
// A site added by mistake can be removed at once for this long.
const GRACE_MINUTES = 10;
const HITS_KEEP_DAYS = 30;

// Domains that host many unrelated things: for these the popup offers the
// exact host first instead of the whole domain.
const SHARED_DOMAINS = [
  'apple.com', 'baidu.com', 'blogspot.com', 'github.io', 'google.com',
  'medium.com', 'microsoft.com', 'msn.com', 'naver.com', 'qq.com',
  'substack.com', 'wordpress.com', 'yahoo.com', 'yandex.com', 'yandex.ru',
];

// "https://www.BBC.com/burmese" -> "bbc.com". Returns null when it is not a site name.
function normalizeSite(input) {
  let s = String(input || '').trim().toLowerCase();
  if (!s) return null;
  if (!/^[a-z][a-z0-9+.-]*:\/\//.test(s)) s = 'http://' + s;
  let host;
  try {
    host = new URL(s).hostname;
  } catch (e) {
    return null;
  }
  host = host.replace(/\.$/, '').replace(/^www\./, '');
  if (host.length > 253) return null;
  if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/.test(host)) return null;
  return host;
}

// Best-effort "whole site" name: edition.cnn.com -> cnn.com, www.bbc.co.uk -> bbc.co.uk.
function baseDomain(host) {
  if (/^\d+(\.\d+){3}$/.test(host)) return host;
  const parts = host.split('.');
  if (parts.length <= 2) return host;
  const tld = parts[parts.length - 1];
  const sld = parts[parts.length - 2];
  const secondLevel = ['ac', 'co', 'com', 'edu', 'go', 'gov', 'ne', 'net', 'or', 'org'];
  const keep = tld.length === 2 && secondLevel.includes(sld) ? 3 : 2;
  return parts.slice(-keep).join('.');
}

function hostMatches(host, site) {
  return host === site || host.endsWith('.' + site);
}

// The list entry that already blocks this host, if any.
function findCovering(sites, host) {
  return sites.find((s) => hostMatches(host, s.host)) || null;
}

async function getSites() {
  const { sites } = await chrome.storage.local.get('sites');
  if (!Array.isArray(sites)) return [];
  return sites.filter((s) => s && typeof s.host === 'string');
}

async function addSite(host) {
  const sites = await getSites();
  const covering = findCovering(sites, host);
  if (covering) return { ok: false, by: covering.host };
  // Entries that the new, wider one makes redundant are dropped.
  const kept = sites.filter((s) => !hostMatches(s.host, host));
  kept.push({ host, addedAt: Date.now() });
  kept.sort((a, b) => a.host.localeCompare(b.host));
  await chrome.storage.local.set({ sites: kept });
  return { ok: true };
}

async function removeSite(host) {
  const sites = await getSites();
  await chrome.storage.local.set({ sites: sites.filter((s) => s.host !== host) });
}

function inGrace(site) {
  return Date.now() - (site.addedAt || 0) < GRACE_MINUTES * 60 * 1000;
}

function dayKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return y + '-' + m + '-' + d;
}

async function getHits() {
  const { hits } = await chrome.storage.local.get('hits');
  return hits && typeof hits === 'object' ? hits : {};
}

// Counts one attempt to open a blocked site and returns today's total.
async function recordHit(site) {
  const { hits: stored, lastHit } = await chrome.storage.local.get(['hits', 'lastHit']);
  const hits = stored && typeof stored === 'object' ? stored : {};
  const now = Date.now();
  const today = dayKey(new Date());
  // The same block can load the page twice within a moment; count it once.
  const repeat = lastHit && lastHit.site === site && now - lastHit.t < 3000;
  if (!repeat) hits[today] = (hits[today] || 0) + 1;
  const oldest = dayKey(new Date(now - HITS_KEEP_DAYS * 24 * 60 * 60 * 1000));
  for (const key of Object.keys(hits)) {
    if (key < oldest) delete hits[key];
  }
  await chrome.storage.local.set({ hits, lastHit: { site, t: now } });
  return hits[today] || 0;
}
