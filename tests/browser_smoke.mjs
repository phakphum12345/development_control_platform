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
  assert.equal(await page.getByText("Edited browser test route").count(), 1);
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

  assert.deepEqual(pageErrors, [], "dashboard should not raise uncaught browser errors");
  console.log("Browser smoke tests passed: route colors, registry CRUD, connections, sandbox, and route preview.");
} finally {
  await browser.close();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}
