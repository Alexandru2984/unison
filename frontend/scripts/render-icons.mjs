// Renders the PWA icons from inline SVG with Playwright's Chromium.
// Usage: node scripts/render-icons.mjs  (writes PNG files into public/)
import { chromium } from "@playwright/test";
import { fileURLToPath } from "node:url";

const out = fileURLToPath(new URL("../public/", import.meta.url));
const glyph = (stroke) =>
  `<g fill="none" stroke="${stroke}" stroke-width="3.5" stroke-linejoin="round"><path d="M32 24v12M15 44v-8h34v8"/><rect x="24" y="11" width="16" height="13" rx="2"/><rect x="7" y="44" width="16" height="12" rx="2"/><rect x="41" y="44" width="16" height="12" rx="2"/></g>`;
// "any" icons keep rounded corners; maskable/apple icons are full-bleed with
// the glyph inside the 80% safe zone.
const rounded = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="15" fill="#dceacb"/>${glyph("#30513b")}</svg>`;
const bleed = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#dceacb"/><g transform="translate(12.8 12.8) scale(0.6)">${glyph("#30513b")}</g></svg>`;
const apple = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#dceacb"/><g transform="translate(8 8) scale(0.75)">${glyph("#30513b")}</g></svg>`;
const icons = [
  ["icon-192.png", 192, rounded],
  ["icon-512.png", 512, rounded],
  ["icon-maskable-512.png", 512, bleed],
  ["apple-touch-icon.png", 180, apple],
];
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 1 });
for (const [name, size, svg] of icons) {
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(
    `<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`,
  );
  await page.screenshot({ path: out + name, omitBackground: true });
}
await browser.close();
console.log(`Rendered ${icons.length} icons into ${out}`);
