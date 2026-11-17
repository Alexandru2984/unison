import { test } from "node:test";
import assert from "node:assert/strict";
import {
  exportMarkdown,
  isIdea,
  mergeIdeas,
  mutationName,
  readStorage,
  wordCount,
  wordDiff,
  type Idea,
} from "../src/lib/ideas.ts";
const seed: Idea = {
  id: 1,
  parent_id: null,
  content: "A seed",
  mutation: "base",
  created_at: null,
  root_id: 1,
  depth: 0,
};

test("reconciles a POST result and repeated live events without duplicates", () => {
  const update = { ...seed, content: "An updated snapshot" },
    second = { ...seed, id: 2 };
  assert.deepEqual(mergeIdeas([second, seed], [update, second]), [
    update,
    second,
  ]);
});
test("word comparison preserves Unicode, whitespace and repeated tokens", () => {
  for (const [left, right] of [
    ["a a garden", "a garden a"],
    ["🌱 Grădină\nnew", "Grădină\nnew 🌱"],
    ["", "hello"],
    ["same", "same"],
  ]) {
    const diff = wordDiff(left, right);
    assert.equal(diff.before.map((t) => t.text).join(""), left);
    assert.equal(diff.after.map((t) => t.text).join(""), right);
    assert.deepEqual(
      diff.before.filter((t) => !t.changed).map((t) => t.text),
      diff.after.filter((t) => !t.changed).map((t) => t.text),
    );
  }
});
test("long comparisons stay bounded and keep the complete text", () => {
  const long = "garden ".repeat(700),
    diff = wordDiff(long, "short");
  assert.equal(diff.truncated, true);
  assert.equal(diff.before[0].text, long);
});
test("Markdown exports escape executable HTML and active link syntax", () => {
  const content = "<img src=x onerror=alert(1)> [open](javascript:alert(1))";
  const markdown = exportMarkdown([{ ...seed, content }]);
  assert(!markdown.includes("<img"));
  assert(!markdown.includes("[open]("));
  assert(markdown.includes("&lt;img"));
  assert(markdown.includes("loaded selection"));
});
test("storage failures are contained and word counts handle whitespace", () => {
  assert.equal(
    readStorage(
      "unavailable",
      "fallback",
      (x): x is string => typeof x === "string",
    ),
    "fallback",
  );
  assert.equal(wordCount("  Grădină\t🌱\nshared "), 3);
  assert.equal(wordCount(" \n\t"), 0);
});
test("accepts transformations added by a newer server without breaking the page", () => {
  assert.equal(isIdea({ ...seed, mutation: "twist" }), true);
  assert.equal(isIdea({ ...seed, mutation: "future_rule" }), true);
  assert.equal(mutationName("future_rule"), "future_rule");
  assert.equal(mutationName("flip"), "Flip");
  for (const mutation of ["", "<script>", "x".repeat(33), 5, null])
    assert.equal(isIdea({ ...seed, mutation }), false);
});
