import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import { mockBoard, fixtures } from "./board";

test("publishes and mutates without relying on a socket event", async ({
  page,
}) => {
  const board = await mockBoard(page);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Your new idea" })
    .fill("A garden of possibilities 🌱");
  await page.getByRole("button", { name: "Plant idea", exact: true }).click();
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    "A garden of possibilities 🌱",
  );
  await page.locator(".transform-button.expand").click();
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    "A reproducible fixture result with a different perspective.",
  );
  expect(board.writes).toHaveLength(2);
  expect(board.writes[1].body).toMatchObject({
    parent_id: 4,
    mutation: "expand",
    content: "",
  });
  await page
    .getByRole("button", { name: "Compare to parent", exact: true })
    .click();
  await expect(page.locator(".comparison del").first()).toBeVisible();
  await expect(page.locator(".comparison mark").first()).toBeVisible();
});

test("filters, saves, exports, and retains one socket during selection", async ({
  page,
}) => {
  const board = await mockBoard(page);
  await page.goto("/");
  await page.getByRole("button", { name: "List", exact: true }).click();
  await expect(page.locator(".idea-list-card")).toHaveCount(3);
  await page
    .getByRole("textbox", { name: "Search all ideas" })
    .fill("rooftops");
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
  await page.locator(".list-idea-content").click();
  await page
    .locator(".inspector")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await page.getByRole("button", { name: "Close idea details" }).click();
  await page.locator(".list-idea-content").click();
  expect(board.sockets).toBe(1);
  await page.getByRole("button", { name: "Clear search" }).click();
  await page.getByRole("button", { name: /Saved on this device/ }).click();
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
  await page.getByLabel("Export loaded ideas").click();
  const promise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download JSON", exact: true })
    .click();
  const downloaded = await promise;
  const downloadPath = await downloaded.path();
  expect(downloadPath).not.toBeNull();
  const exported = JSON.parse(await readFile(downloadPath!, "utf8"));
  expect(exported.ideas.map((idea: { id: number }) => idea.id)).toEqual([1]);
  await page.reload();
  await page.getByRole("button", { name: /Saved on this device/ }).click();
  await page.getByRole("button", { name: "List", exact: true }).click();
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
});

test("keeps drafts on failure and reuses the same request key on retry", async ({
  page,
}) => {
  const board = await mockBoard(page);
  board.failWrite();
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Your new idea" });
  await input.fill("A safe local draft");
  await page.getByRole("button", { name: "Plant idea", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Engine is busy");
  await expect(input).toHaveValue("A safe local draft");
  await page.getByRole("button", { name: "Plant idea", exact: true }).click();
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    "A safe local draft",
  );
  expect(board.writes[0].key).toBe(board.writes[1].key);
  expect(board.ideas).toHaveLength(4);
});

test("restores deep links and drafts and renders public text safely", async ({
  page,
}) => {
  const hostile = '<img src=x onerror="window.__injected=true">';
  await mockBoard(page, [
    ...fixtures,
    { ...fixtures[0], id: 4, root_id: 4, content: hostile },
  ]);
  await page.goto("/#idea-2");
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[1].content,
  );
  const input = page.getByRole("textbox", { name: "Your new idea" });
  await input.fill("Recovered local draft");
  await page.reload();
  await expect(input).toHaveValue("Recovered local draft");
  await page.getByRole("button", { name: "Close idea details" }).click();
  await page.getByRole("button", { name: "List", exact: true }).click();
  await expect(
    page.locator(".list-idea-content").filter({ hasText: hostile }),
  ).toBeVisible();
  expect(await page.evaluate(() => "__injected" in window)).toBe(false);
  await expect(page.locator(".idea-list img")).toHaveCount(0);
});

test("fits phones and tablets, opens the composer and persists the theme", async ({
  page,
}) => {
  await mockBoard(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".idea-list-card")).toHaveCount(3);
  for (const width of [320, 360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    await page.evaluate(() => new Promise(requestAnimationFrame));
    const bounds = await page.evaluate(() => ({
      viewport: innerWidth,
      content: document.body.scrollWidth,
    }));
    expect(bounds.content, `overflow at ${width}px`).toBeLessThanOrEqual(
      bounds.viewport,
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "New idea", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Your new idea" }),
  ).toBeFocused();
  await page.getByText("Try a starting point", { exact: true }).click();
  await page
    .locator(".composer-starters")
    .getByRole("button", { name: "Climate" })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your new idea" }),
  ).toHaveValue(/repairing/);
  await page
    .getByRole("button", { name: "Close library", exact: true })
    .click();
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "How it works" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("has accessible list, graph, mobile controls and guide", async ({
  page,
}) => {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await mockBoard(page, [
    ...fixtures,
    { ...fixtures[1], id: 4, mutation: "expand" },
    { ...fixtures[1], id: 5, mutation: "mutate_keywords" },
    { ...fixtures[1], id: 6, mutation: "synthesize" },
  ]);
  await page.goto("/");
  await expect(page.locator(".idea-node")).toHaveCount(6);
  for (const view of ["Graph", "List"]) {
    await page.getByRole("button", { name: view, exact: true }).click();
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(result.violations).toEqual([]);
  }
  await page.getByRole("button", { name: /^Rephrase #002/ }).click();
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[1].content,
  );
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  for (const view of ["List", "Graph"]) {
    await page.getByRole("button", { name: view, exact: true }).click();
    const dark = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(dark.violations).toEqual([]);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "How it works" }).click();
  const dialog = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(dialog.violations).toEqual([]);
  expect(failures).toEqual([]);
});

test("serves canonical metadata, crawl files and social image", async ({
  page,
  request,
}) => {
  await mockBoard(page);
  await page.goto("/");
  await expect(page).toHaveTitle(/Idea Evolution/);
  await expect(page.locator("link[rel=canonical]")).toHaveAttribute(
    "href",
    "https://unison.micutu.com/",
  );
  expect((await request.get("/robots.txt")).status()).toBe(200);
  expect(await (await request.get("/sitemap.xml")).text()).toContain(
    "https://unison.micutu.com/",
  );
  const social = await request.get("/social-card.png");
  expect(social.headers()["content-type"]).toContain("image/png");
});

test("loads older pages without losing newer results", async ({ page }) => {
  const data = Array.from({ length: 205 }, (_, index) => ({
    ...fixtures[0],
    id: index + 1,
    root_id: index + 1,
    content: `Pagination idea ${index + 1}`,
  }));
  await mockBoard(page, data);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".idea-list-card")).toHaveCount(200);
  await page.getByRole("button", { name: "Load older ideas" }).click();
  await expect(page.locator(".idea-list-card")).toHaveCount(205);
  await expect(
    page.getByRole("button", { name: "Load older ideas" }),
  ).toHaveCount(0);
});

test("reports privately with an accessible mobile dialog", async ({ page }) => {
  const board = await mockBoard(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#idea-2");
  await page.getByRole("button", { name: "Report this idea" }).click();
  const modal = page.getByRole("dialog", { name: "Report idea #2" });
  await expect(modal).toBeVisible();
  await expect(
    modal.getByRole("button", { name: "Send report" }),
  ).toBeDisabled();
  await modal
    .getByRole("radio", { name: "Personal or confidential information" })
    .check();
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await modal.getByRole("button", { name: "Send report" }).click();
  await expect(page.getByRole("dialog")).toContainText("Report received.");
  expect(board.reports).toEqual([{ ideaId: 2, reason: "privacy" }]);
  expect(board.ideas).toHaveLength(3);
  await page.getByRole("button", { name: "Done", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[1].content,
  );
});

test("moderation removes live cached text, bookmarks, comparisons and export results", async ({
  page,
}) => {
  const board = await mockBoard(page);
  await page.goto("/#idea-2");
  await page.getByRole("button", { name: "List", exact: true }).click();
  await page
    .locator(".inspector")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Compare to parent", exact: true })
    .click();
  await expect(page.locator(".comparison")).toBeVisible();
  await expect(page.locator(".connection.live")).toBeVisible();
  board.moderate(1);
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
  await expect(page.locator(".comparison")).toHaveCount(0);
  await expect(page.locator(".inspector")).toContainText(
    "This idea is out of reach.",
  );
  await expect(
    page.getByText(fixtures[0].content, { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText(fixtures[1].content, { exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Export loaded ideas").click();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download JSON", exact: true })
    .click();
  const result = JSON.parse(
    await readFile((await (await download).path())!, "utf8"),
  );
  expect(result.ideas.map((i: { id: number }) => i.id)).toEqual([3]);
  await page.getByLabel("Export loaded ideas").click();
  await page.getByRole("button", { name: /Saved on this device/ }).click();
  await expect(page.locator(".idea-list-card")).toHaveCount(0);
  board.restore();
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[1].content,
  );
});

test("polling revision changes purge cached text when live notification is unavailable", async ({
  page,
}) => {
  const board = await mockBoard(page);
  await page.goto("/#idea-2");
  await expect(page.locator(".inspector .selected-content")).toHaveText(
    fixtures[1].content,
  );
  await page.getByRole("button", { name: "List", exact: true }).click();
  board.moderate(1, false);
  // Visibility refresh uses the same HTTP revision check as the periodic fallback.
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
  await expect(page.locator(".inspector .selected-content")).toHaveCount(0);
  await expect(page.locator(".inspector")).toContainText(
    "This idea is out of reach.",
  );
});

test("report failure stays visible and permits retry", async ({ page }) => {
  await mockBoard(page);
  await page.goto("/#idea-2");
  await page.route("**/api/idea/2/report", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Reporting is temporarily unavailable." }),
    }),
  );
  await page.getByRole("button", { name: "Report this idea" }).click();
  await page.getByRole("radio", { name: "Spam or advertising" }).check();
  await page.getByRole("button", { name: "Send report" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Reporting is temporarily unavailable.",
  );
  await expect(
    page.getByRole("radio", { name: "Spam or advertising" }),
  ).toBeChecked();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("a delayed write response cannot repopulate a moderated branch", async ({
  page,
}) => {
  const board = await mockBoard(page);
  await page.goto("/#idea-2");
  await page.getByRole("button", { name: "List", exact: true }).click();
  const release = board.pauseWrite();
  await page.locator(".transform-button.expand").click();
  await expect.poll(() => board.ideas.length).toBe(4);
  board.moderate(1);
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
  release();
  await expect(page.locator(".inspector")).toContainText(
    "This idea is out of reach.",
  );
  await expect(
    page.getByText(
      "A reproducible fixture result with a different perspective.",
      { exact: true },
    ),
  ).toHaveCount(0);
  await expect(page.locator(".idea-list-card")).toHaveCount(1);
});
