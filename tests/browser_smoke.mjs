import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

const html = await readFile(new URL("../dashboard/index.html", import.meta.url), "utf8");
const server = createServer((_req, res) => {
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(html);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto(`http://127.0.0.1:${address.port}/`);
  await page.getByRole("heading", { name: "Development Control Platform" }).waitFor();

  // Route colors must preview, persist locally, and restore their matching controls.
  await page.locator('[data-tab="route-colors"]').click();
  const readColor = page.locator('[data-route-color="route_read"]');
  await readColor.evaluate((el) => {
    el.value = "#123456";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  assert.equal(await page.locator("html").evaluate((el) => getComputedStyle(el).getPropertyValue("--route-read").trim()), "#123456");
  await page.locator("#route-color-save").click();
  await page.reload();
  await page.locator('[data-tab="route-colors"]').click();
  assert.equal(await page.locator('[data-route-color="route_read"]').inputValue(), "#123456", "saved palette should be reflected in the color control after reload");
  await page.locator("#route-color-reset").click();
  assert.equal(await page.locator('[data-route-color="route_read"]').inputValue(), "#2563eb");

  // Route registry add/edit/delete stays local to the browser.
  await page.locator('[data-tab="ui-routes"]').click();
  await page.locator("#route-id").fill("browser-test");
  await page.locator("#route-label").fill("Browser test route");
  await page.locator("#route-target").selectOption("repo");
  await page.locator("#route-add").click();
  assert.equal(await page.locator('[data-route-edit="browser-test"]').count(), 1);
  await page.locator('[data-route-edit="browser-test"]').click();
  await page.locator("#route-label").fill("Edited browser test route");
  await page.locator("#route-add").click();
  assert.equal(await page.locator("#route-registry-table").getByText("Edited browser test route").count(), 1);
  await page.locator('[data-route-delete="browser-test"]').click();
  assert.equal(await page.locator('[data-route-edit="browser-test"]').count(), 0);

  // Connection editing and registry preview exercise the same local graph.
  await page.locator("#edge-from").selectOption("home");
  await page.locator("#edge-to").selectOption("user");
  await page.locator("#edge-add").click();
  assert.equal(await page.locator("#route-edge-list").getByText("user").count(), 1);
  await page.locator('[data-tab="ui-simulator"]').click();
  const frame = page.locator("#sim-preview");
  assert.equal(await frame.getAttribute("sandbox"), "allow-scripts", "simulator must not grant same-origin access");
  await page.locator("#sim-code").fill("<!doctype html><html><body><h1 id='browser-proof'>Sandbox browser test passed</h1></body></html>");
  await page.locator("#sim-run").click();
  assert.equal(await frame.contentFrame().locator("#browser-proof").textContent(), "Sandbox browser test passed");
  await page.locator("#sim-route-select").selectOption("home");
  await page.locator("#sim-open-route").click();
  assert.equal(await frame.contentFrame().locator("#route-title").textContent(), "Overview");


  // Code Navigator must use the existing route/color managers and make its
  // actions truthful: trace the real view, then run DOM-only checks.
  await page.locator('[data-tab="code-navigator"]').click();
  await page.locator('[data-code-nav-route="ui-routes"]').click();
  await page.locator("#code-nav-trace-calls").click();
  assert.match(await page.locator("#code-nav-result").textContent(), /Trace Calls — declared mapping only/);
  await page.locator("#code-nav-run-checks").click();
  assert.match(await page.locator("#code-nav-result").textContent(), /Mapped elements present: 5\/5/);
  assert.match(await page.locator("#code-nav-evidence").textContent(), /CI \/ deployment evidence: UNKNOWN/);
  await page.locator("#code-nav-show-ui").click();
  assert.equal(await page.locator("#ui-routes").evaluate((el) => el.classList.contains("active")), true);
  await page.locator('[data-tab="code-navigator"]').click();
  await page.locator("#code-nav-filter").selectOption("security");
  assert.equal(await page.locator('[data-code-nav-route="evidence"]').count(), 1);
  assert.equal(await page.locator('[data-code-nav-route="ui-routes"]').count(), 0);
  await page.locator("#code-nav-search").fill("nonexistent-route-query");
  assert.equal(await page.locator('[data-code-nav-route]').count(), 0);
  await page.locator("#code-nav-search").fill("");
  await page.locator("#code-nav-filter").selectOption("all");

  assert.deepEqual(pageErrors, [], "dashboard should not raise uncaught browser errors");
  console.log("Browser smoke tests passed: route colors, registry CRUD, connections, sandbox, route preview, and Code Navigator mapping/actions.");
} finally {
  await browser.close();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}
