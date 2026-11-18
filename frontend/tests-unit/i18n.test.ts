import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  detectLanguage,
  localizeError,
  messageKeys,
  placeholders,
  translator,
} from "../src/lib/i18n.ts";
import { highlight } from "../src/lib/ideas.ts";
import { dailySpark, sparkCount } from "../src/lib/spark.ts";
import { wrapText } from "../src/lib/card.ts";

test("both dictionaries use the same placeholders for every message", () => {
  for (const key of messageKeys())
    assert.deepEqual(placeholders("ro", key), placeholders("en", key), key);
});

test("interpolates values and keeps unknown placeholders visible", () => {
  const t = translator("ro");
  assert.equal(t("idea.save", { id: 7 }), "Salvează ideea 7");
  assert.equal(t("idea.save"), "Salvează ideea {id}");
});

test("detects Romanian and English browser preferences", () => {
  assert.equal(detectLanguage(["ro-RO", "en-US"]), "ro");
  assert.equal(detectLanguage(["de-DE", "en-GB"]), "en");
  assert.equal(detectLanguage(["fr-FR"]), "en");
  assert.equal(detectLanguage([]), "en");
});

test("every translated server message matches the backend source exactly", () => {
  const backend = ["main.py", "text_policy.py", "moderation.py", "security.py"]
    .map((name) => readFileSync(new URL(`../../backend/${name}`, import.meta.url), "utf8"))
    .join("\n");
  const en = translator("en");
  for (const key of messageKeys().filter((k) => k.startsWith("server.")))
    assert.ok(backend.includes(en(key)), `${key}: ${en(key)}`);
});

test("localizes known errors and passes unknown text through", () => {
  assert.equal(
    localizeError("ro", "Idea not found"),
    "Ideea nu a fost găsită",
  );
  assert.equal(
    localizeError("ro", "A little breathing room. Try again in 12 seconds."),
    "Puțin răgaz. Încearcă din nou în 12 secunde.",
  );
  assert.equal(localizeError("ro", "Failed to fetch"), translator("ro")("error.unreachable"));
  assert.equal(localizeError("ro", "Something new"), "Something new");
});

test("the daily spark is stable for a day and rotates", () => {
  const day = new Date("2026-11-18T08:00:00Z"),
    later = new Date("2026-11-18T23:59:00Z"),
    next = new Date("2026-11-19T00:01:00Z");
  assert.equal(dailySpark("en", day), dailySpark("en", later));
  assert.notEqual(dailySpark("en", day), dailySpark("en", next));
  assert.equal(sparkCount("en"), sparkCount("ro"));
});

test("search highlighting never changes the text", () => {
  for (const [text, query] of [
    ["Rooftop gardens on rooftops", "rooftop"],
    ["Grădină și GRĂDINĂ", "grădină"],
    ["no match", "zzz"],
    ["", "a"],
  ]) {
    const parts = highlight(text, query);
    assert.equal(parts.map((p) => p.text).join(""), text);
  }
  assert.deepEqual(
    highlight("ab AB", "ab").filter((p) => p.match).map((p) => p.text),
    ["ab", "AB"],
  );
});

test("card text wraps long words and ellipsizes extra lines", () => {
  const measure = (value: string) => value.length;
  assert.deepEqual(wrapText("aa bb cc", 5, measure, 3), ["aa bb", "cc"]);
  assert.deepEqual(wrapText("abcdefghij", 4, measure, 5), ["abcd", "efgh", "ij"]);
  const lines = wrapText("one two three four five six", 7, measure, 2);
  assert.equal(lines.length, 2);
  assert.ok(lines[1].endsWith("…"));
  assert.ok(lines.every((line) => measure(line) <= 7));
});
