"use strict";
const CACHE_NAME = "dcp-shell-v1";
const SHELL = ["./index.html", "./manifest.webmanifest", "./icons/dcp.svg"];
const scopeURL = new URL(self.registration.scope);
const apiPrefix = new URL("./api/", scopeURL).pathname;

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("dcp-shell-") && key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== scopeURL.origin) return;
  // Authentication/API requests are always network-only and are never cached.
  if (url.pathname.startsWith(apiPrefix) || /\/api\/auth\//.test(url.pathname)) {
    event.respondWith(fetch(request, { cache: "no-store" }));
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(async () => (await caches.match("./index.html")) || Response.error()));
    return;
  }
  if (SHELL.some(path => new URL(path, scopeURL).pathname === url.pathname)) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
  }
});
