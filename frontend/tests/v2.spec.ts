import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockBoard, fixtures } from "./board";

const axe = (page: import("@playwright/test").Page) =>
  new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

test("previews every rule, reuses existing branches and waters ideas", async ({
  page,
}) => {
  const board = await mockBoard(page);
  await page.goto("/#idea-1");
  const inspector = page.locator(".inspector");
  await expect(
    inspector.locator(".transform-button.expand .transform-preview"),
  ).toHaveText(/^Expand preview of Turn empty city/);
  // Idea 2 is the rephrase branch of idea 1: open it instead of writing again.
  const rephrase = inspector.locator(".transform-button.rephrase");
  await expect(rephrase).toContainText("Already grows here");
  await rephrase.click();
  await expect(inspector.locator(".selected-content")).toHaveText(
    fixtures[1].content,
  );
  expect(board.writes).toHaveLength(0);
  const water = inspector.getByRole("button", { name: /^Water/ });
  await water.click();
  await expect(
    inspector.getByRole("button", { name: /^Watered 1/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("status").filter({ hasText: "Thanks" })).toBeVisible();
  await inspector.getByRole("button", { name: /^Watered/ }).click();
  expect(board.water.get(2)).toBe(1);
  await expect(inspector.locator(".idea-metrics")).toContainText("1 waterings");
  expect(await axe(page).then((r) => r.violations)).toEqual([]);
});

test("shares a public link and downloads an idea card", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await mockBoard(page);
  await page.addInitScript(() => {
    // Exercise the fallback path deterministically on every platform.
    Object.defineProperty(navigator, "share", { value: undefined });
  });
  await page.goto("/#idea-2");
  await page.getByRole("button", { name: "Share idea" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Link copied" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    "http://127.0.0.1:4178/i/2",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download idea card" }).click();
  const card = await download;
  expect(card.suggestedFilename()).toBe("idea-2.png");
  const path = await card.path();
  const bytes = await import("node:fs/promises").then((fs) => fs.readFile(path!));
  expect(bytes.subarray(1, 4).toString()).toBe("PNG");
  expect(bytes.length).toBeGreaterThan(5000);
});

test("discovers sections, the daily spark and a surprise idea", async ({
  page,
}) => {
  await mockBoard(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Discover", exact: true }).click();
  const discover = page.getByRole("region", { name: "Discover ideas" });
  await expect(discover.getByText("Today’s spark".toUpperCase())).toBeVisible();
  await expect(
    discover.getByRole("heading", { name: "Fresh seeds" }),
  ).toBeVisible();
  await expect(discover.locator(".discover-card")).not.toHaveCount(0);
  await expect(discover.locator(".pulse-bars > span")).toHaveCount(30);
  expect(await axe(page).then((r) => r.violations)).toEqual([]);
  await discover.getByRole("button", { name: "Surprise me" }).click();
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[0].content,
  );
  await discover.getByRole("button", { name: "Plant this spark" }).click();
  await expect(
    page.getByRole("textbox", { name: "Your new idea" }),
  ).not.toHaveValue("");
});

test("previews a draft without publishing it", async ({ page }) => {
  const board = await mockBoard(page);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Your new idea" })
    .fill("A quiet library for loud ideas");
  await page.getByRole("button", { name: "Preview transformations" }).click();
  const preview = page.locator("#draft-preview");
  await expect(preview.locator("li")).toHaveCount(8);
  await expect(preview).toContainText("Question preview of A quiet library");
  expect(board.previews).toEqual(["A quiet library for loud ideas"]);
  expect(board.writes).toHaveLength(0);
  await page
    .getByRole("textbox", { name: "Your new idea" })
    .fill("Something else");
  await expect(preview).toHaveCount(0);
});

test("keyboard walks the tree and filters local and unexplored ideas", async ({
  page,
}) => {
  await mockBoard(page);
  await page.goto("/#idea-1");
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[0].content,
  );
  await page.keyboard.press("ArrowDown");
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[1].content,
  );
  await page.keyboard.press("ArrowUp");
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[0].content,
  );
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "List", exact: true }).click();
  await page.getByRole("button", { name: "Waiting for a next step" }).click();
  await expect(page.locator(".idea-list-card")).toHaveCount(2);
  await page.getByRole("button", { name: "Planted on this device" }).click();
  await expect(page.getByText("Your garden starts with one seed.")).toBeVisible();
  await page.getByRole("textbox", { name: "Your new idea" }).fill("Mine");
  await page.getByRole("button", { name: "Plant idea", exact: true }).click();
  await page.getByRole("button", { name: "Planted on this device" }).click();
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
  await expect(page.locator(".list-idea-content")).toContainText("Mine");
});

test("replays the garden growing in the graph", async ({ page }) => {
  await mockBoard(page);
  await page.goto("/");
  await expect(page.locator(".idea-node")).toHaveCount(3);
  await page.getByRole("button", { name: "Replay growth" }).click();
  const slider = page.getByRole("slider", { name: "Replay position" });
  await expect(slider).toBeVisible();
  await slider.fill("1");
  await expect(page.locator(".idea-node")).toHaveCount(1);
  await page.getByRole("button", { name: "Show all branches" }).click();
  await expect(page.locator(".idea-node")).toHaveCount(3);
});

test("phones use a bottom navigation and an inspector sheet", async ({
  page,
}) => {
  await mockBoard(page);
  await page.setViewportSize({ width: 360, height: 760 });
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(nav).toBeVisible();
  await expect(page.getByRole("button", { name: "New idea", exact: true })).toBeHidden();
  await nav.getByRole("button", { name: "Discover" }).click();
  await expect(nav.getByRole("button", { name: "Discover" })).toHaveAttribute(
    "aria-current",
    "true",
  );
  await page.locator(".discover-card").first().click();
  const sheet = page.locator(".inspector.has-selection");
  await expect(sheet).toBeVisible();
  const box = await sheet.boundingBox();
  expect(box!.y).toBeGreaterThan(60);
  expect(await axe(page).then((r) => r.violations)).toEqual([]);
  await page.getByRole("button", { name: "Close idea details" }).click();
  await expect(sheet).toHaveCount(0);
  await nav.getByRole("button", { name: "Saved" }).click();
  await expect(page.getByText("Keep the ideas that stay with you.")).toBeVisible();
  const width = await page.evaluate(() => document.body.scrollWidth);
  expect(width).toBeLessThanOrEqual(360);
});

test.describe("Romanian visitors", () => {
  test.use({ locale: "ro-RO" });
  test("detects Romanian, translates the interface and remembers a switch", async ({
    page,
  }) => {
    await mockBoard(page);
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "ro");
    await expect(
      page.getByRole("button", { name: "Plantează ideea", exact: true }),
    ).toBeVisible();
    await expect(page).toHaveTitle(/Descoperă/);
    expect(await axe(page).then((r) => r.violations)).toEqual([]);
    await page.getByRole("button", { name: /Switch language to English/ }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await page.reload();
    await expect(
      page.getByRole("button", { name: "Plant idea", exact: true }),
    ).toBeVisible();
  });
  test("localizes known server errors", async ({ page }) => {
    await mockBoard(page);
    await page.route("**/api/idea", (route) =>
      route.request().method() === "POST"
        ? route.fulfill({
            status: 422,
            contentType: "application/json",
            body: JSON.stringify({
              detail: [
                {
                  location: ["body"],
                  message: "Links and web addresses are not allowed in public ideas",
                },
              ],
            }),
          })
        : route.fallback(),
    );
    await page.goto("/");
    await page.getByRole("textbox", { name: "Ideea ta nouă" }).fill("vezi x.com");
    await page.getByRole("button", { name: "Plantează ideea", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(
      "Linkurile și adresele web nu sunt permise",
    );
  });
});

test("the live connection does not restart the first board load", async ({
  page,
}) => {
  await mockBoard(page);
  // A slow first response, as on real networks: the socket opens mid-load.
  let slow = true;
  await page.route("**/api/stats", async (route) => {
    if (slow) await new Promise((resolve) => setTimeout(resolve, 400));
    slow = false;
    await route.fallback();
  });
  const failed: string[] = [],
    boardLoads: string[] = [];
  page.on("requestfailed", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      failed.push(request.url());
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/idea" && !url.searchParams.has("roots_only"))
      boardLoads.push(url.search);
  });
  await page.goto("/");
  await expect(page.locator(".connection.live")).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(failed).toEqual([]);
  // One full load, then at most one incremental catch-up for the connect gap.
  expect(boardLoads[0]).not.toContain("after=");
  expect(boardLoads.slice(1).every((query) => query.includes("after="))).toBe(true);
  expect(boardLoads.length).toBeLessThanOrEqual(2);
});
