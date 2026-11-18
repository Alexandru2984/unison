import { test, expect } from "@playwright/test";
import { mockBoard } from "./board";

test.describe("installable app", () => {
  test.use({ serviceWorkers: "allow" });
  test("ships a manifest, icons and an offline app shell", async ({
    page,
    context,
    request,
  }) => {
    await mockBoard(page);
    await page.goto("/");
    const href = await page
      .locator('link[rel="manifest"]')
      .getAttribute("href");
    const manifest = await (await request.get(href!)).json();
    expect(manifest.display).toBe("standalone");
    expect(manifest.start_url).toBe("/?source=pwa");
    for (const icon of manifest.icons) {
      const response = await request.get(icon.src);
      expect(response.headers()["content-type"]).toContain("image/png");
      const bytes = await response.body();
      // PNG width and height live at fixed offsets of the IHDR chunk.
      const [width, height] = [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
      expect(`${width}x${height}`).toBe(icon.sizes);
    }
    await page.evaluate(async () => {
      await navigator.serviceWorker.ready;
    });
    await page.reload();
    await expect
      .poll(() => page.evaluate(() => !!navigator.serviceWorker.controller))
      .toBe(true);
    await context.setOffline(true);
    await page.reload();
    await expect(page.locator(".app-shell")).toBeVisible();
    await expect(page.locator(".offline-banner")).toBeVisible();
    await context.setOffline(false);
  });

  test("app shortcuts open Discover and the composer", async ({ page }) => {
    await mockBoard(page);
    await page.goto("/?view=discover");
    await expect(page.getByRole("region", { name: "Discover ideas" })).toBeVisible();
    await page.goto("/?action=plant");
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("textbox", { name: "Your new idea" })).toBeVisible();
  });
});
