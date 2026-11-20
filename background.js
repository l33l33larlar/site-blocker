'use strict';

importScripts('shared.js');

function blockedUrl(site) {
  return chrome.runtime.getURL('blocked.html?site=' + encodeURIComponent(site));
}

// One redirect rule per blocked site. The rules live in the browser itself,
// so they keep working while this service worker is asleep.
async function syncRules() {
  const sites = await getSites();
  const existing = await chrome.declarativeNetRequest.getDynamicRules();
  const addRules = sites.map((s, i) => ({
    id: i + 1,
    priority: 1,
    action: {
      type: 'redirect',
      redirect: { extensionPath: '/blocked.html?site=' + encodeURIComponent(s.host) },
    },
    condition: { requestDomains: [s.host], resourceTypes: ['main_frame'] },
  }));
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: existing.map((r) => r.id),
    addRules,
  });
  await sweepTabs(sites);
}

// Rule updates must not overlap, so they run one after another.
let syncQueue = Promise.resolve();
function scheduleSync() {
  syncQueue = syncQueue.then(syncRules).catch((e) => console.error('Site Blocker: rule sync failed', e));
  return syncQueue;
}

function siteForUrl(sites, url) {
  if (!/^https?:/i.test(url || '')) return null;
  let host;
  try {
    host = new URL(url).hostname.toLowerCase().replace(/\.$/, '');
  } catch (e) {
    return null;
  }
  const hit = findCovering(sites, host);
  return hit ? hit.host : null;
}

async function redirectTab(tabId, site) {
  try {
    await chrome.tabs.update(tabId, { url: blockedUrl(site) });
  } catch (e) {
    // The tab was closed in the meantime.
  }
}

// Tabs that already show a site when it gets added to the list.
async function sweepTabs(sites) {
  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) {
    const site = siteForUrl(sites, tab.url);
    if (site) await redirectTab(tab.id, site);
  }
}

// Second net for pages that never reach the network rules: pages served from
// a site's own offline cache, and in-page navigation.
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (!changeInfo.url) return;
  const site = siteForUrl(await getSites(), changeInfo.url);
  if (site) await redirectTab(tabId, site);
});

// Version 1.0.0 stored a ready-made list of sites on install. The list now
// starts empty, so a copy installed back then gets that batch taken out
// again, once. The batch is recognisable because its entries all carry one
// timestamp; a site added by hand has its own and is kept.
const SEED_BATCH_MIN = 10;

function withoutSeed(sites) {
  const counts = new Map();
  for (const s of sites) counts.set(s.addedAt, (counts.get(s.addedAt) || 0) + 1);
  return sites.filter((s) => counts.get(s.addedAt) < SEED_BATCH_MIN);
}

// Runs every time the service worker starts, so it also runs after the
// extension is reloaded; it only writes the first time.
async function prepareStorage() {
  const { sites, seedCleared } = await chrome.storage.local.get(['sites', 'seedCleared']);
  if (!Array.isArray(sites)) {
    await chrome.storage.local.set({ sites: [], seedCleared: true });
  } else if (!seedCleared) {
    await chrome.storage.local.set({ sites: withoutSeed(sites), seedCleared: true });
  }
}

const storageReady = prepareStorage().catch((e) => console.error('Site Blocker: storage setup failed', e));

chrome.runtime.onInstalled.addListener(async (details) => {
  await storageReady;
  await scheduleSync();
  if (details.reason === 'install') chrome.runtime.openOptionsPage();
});

chrome.runtime.onStartup.addListener(() => {
  scheduleSync();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.sites) scheduleSync();
});
