import { localizeError, type Lang } from "./i18n.ts";

export type KnownMutation =
  | "base"
  | "expand"
  | "rephrase"
  | "mutate_keywords"
  | "synthesize"
  | "question"
  | "twist"
  | "headline"
  | "flip";
// Newer servers may add rules; unknown names still render with a generic label.
export type Mutation = KnownMutation | (string & {});
export interface Idea {
  id: number;
  parent_id: number | null;
  content: string;
  mutation: Mutation;
  created_at: string | null;
  root_id: number;
  depth: number;
  /** Visible branches and reactions; absent from older servers. */
  children?: number;
  water?: number;
}
export interface Stats {
  total: number;
  seeds: number;
  max_depth: number;
  capacity: number;
  max_branch_depth: number;
  water?: number;
  activity?: { day: string; ideas: number }[];
}
export const mutations: {
  id: KnownMutation;
  name: string;
  description: string;
  symbol: string;
}[] = [
  {
    id: "expand",
    name: "Expand",
    description: "Elaborate on longer words and extend the premise.",
    symbol: "↗",
  },
  {
    id: "rephrase",
    name: "Rephrase",
    description: "Reverse word order to shift the perspective.",
    symbol: "⇄",
  },
  {
    id: "mutate_keywords",
    name: "Amplify",
    description: "Give longer keywords a louder voice.",
    symbol: "✳",
  },
  {
    id: "synthesize",
    name: "Synthesize",
    description: "Keep alternating words and find the essence.",
    symbol: "↙",
  },
  {
    id: "question",
    name: "Question",
    description: "Turn it into a what-if question. Repeat for new angles.",
    symbol: "?",
  },
  {
    id: "twist",
    name: "Twist",
    description: "Add a surprising constraint chosen by the text itself.",
    symbol: "↯",
  },
  {
    id: "headline",
    name: "Headline",
    description: "Condense it into a punchy title-case headline.",
    symbol: "H",
  },
  {
    id: "flip",
    name: "Flip",
    description: "Swap words for their opposites and test the reverse.",
    symbol: "⇅",
  },
];
export const mutationName = (id: Mutation) =>
  id === "base"
    ? "Seed / custom"
    : (mutations.find((m) => m.id === id)?.name ?? id);
export const isIdea = (value: unknown): value is Idea => {
  if (!value || typeof value !== "object") return false;
  const x = value as Idea;
  return (
    Number.isSafeInteger(x.id) &&
    x.id > 0 &&
    typeof x.content === "string" &&
    typeof x.mutation === "string" &&
    /^[a-z_]{1,32}$/.test(x.mutation) &&
    (x.parent_id === null || Number.isSafeInteger(x.parent_id)) &&
    Number.isInteger(x.depth) &&
    Number.isInteger(x.root_id)
  );
};
export function mergeIdeas(a: Idea[], b: Idea[]): Idea[] {
  return [
    ...new Map([...a, ...b].map((idea) => [idea.id, idea])).values(),
  ].sort((x, y) => x.id - y.id);
}
export function readStorage<T>(
  key: string,
  fallback: T,
  validate: (value: unknown) => value is T,
): T {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "null");
    return validate(value) ? value : fallback;
  } catch {
    return fallback;
  }
}
export function storeLocal(key: string, value: unknown): boolean {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
export const wordCount = (text: string) =>
  text.trim() ? text.trim().split(/\s+/u).length : 0;
export function exportMarkdown(ideas: Idea[]): string {
  // Escape raw HTML, Markdown links and headings from public user input.
  const escape = (s: string) =>
    s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/[\\`*_{}[\]()#+.!|~-]/g, "\\$&");
  return (
    "# Idea Evolution\n\nExport of the currently loaded selection.\n\n" +
    ideas
      .map(
        (i) =>
          `## Idea ${i.id} · ${mutationName(i.mutation)}\n\n${escape(i.content)}\n\nParent: ${i.parent_id ?? "none"} · Depth: ${i.depth}\n`,
      )
      .join("\n")
  );
}
export function download(name: string, content: string | Blob, type: string) {
  const url = URL.createObjectURL(
    content instanceof Blob ? content : new Blob([content], { type }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function apiError(
  response: Response,
  lang: Lang = "en",
): Promise<string> {
  const local = (message: string) => localizeError(lang, message);
  let detail: unknown = null;
  try {
    detail = (await response.json())?.detail;
  } catch {
    /* Nginx may return an HTML or plain-text error page. */
  }
  if (response.status === 429) {
    // Budget messages explain a longer wait; generic limiter messages do not.
    if (typeof detail === "string" && !detail.startsWith("Too many"))
      return local(detail);
    const wait = Number(response.headers.get("Retry-After"));
    return local(
      `A little breathing room. Try again in ${Number.isSafeInteger(wait) && wait > 0 ? wait : 30} seconds.`,
    );
  }
  if (typeof detail === "string") return local(detail);
  if (Array.isArray(detail) && detail.length)
    return detail
      .map((e: { message?: unknown }) =>
        local(typeof e?.message === "string" ? e.message : "Invalid input"),
      )
      .join(" · ");
  return local(
    `The request could not be completed (${response.status}). Please try again.`,
  );
}
export type DiffToken = { text: string; changed: boolean };
export function wordDiff(
  before: string,
  after: string,
): { before: DiffToken[]; after: DiffToken[]; truncated: boolean } {
  const a = before.match(/\s+|\S+/gu) ?? [],
    b = after.match(/\s+|\S+/gu) ?? [];
  if (a.length > 600 || b.length > 600)
    return {
      before: [{ text: before, changed: false }],
      after: [{ text: after, changed: false }],
      truncated: true,
    };
  const width = b.length + 1,
    grid = new Uint16Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--) {
      grid[i * width + j] =
        a[i] === b[j]
          ? 1 + grid[(i + 1) * width + j + 1]
          : Math.max(grid[(i + 1) * width + j], grid[i * width + j + 1]);
    }
  const left: DiffToken[] = [],
    right: DiffToken[] = [];
  let i = 0,
    j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      left.push({ text: a[i++], changed: false });
      right.push({ text: b[j++], changed: false });
    } else if (
      i < a.length &&
      (j === b.length || grid[(i + 1) * width + j] >= grid[i * width + j + 1])
    )
      left.push({ text: a[i++], changed: true });
    else right.push({ text: b[j++], changed: true });
  }
  return { before: left, after: right, truncated: false };
}

/** Bounded list of positive IDs kept on this device (newest last). */
export const validIdList =
  (max: number) =>
  (value: unknown): value is number[] =>
    Array.isArray(value) &&
    value.length <= max &&
    value.every((n) => Number.isSafeInteger(n) && n > 0);
export const remember = (list: number[], id: number, max: number) =>
  [...list.filter((n) => n !== id), id].slice(-max);
/** Splits text around case-insensitive matches of a query for safe highlighting. */
export function highlight(
  text: string,
  query: string,
): { text: string; match: boolean }[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [{ text, match: false }];
  const haystack = text.toLocaleLowerCase();
  // Case folding can change string length; fall back to no highlighting then.
  if (haystack.length !== text.length) return [{ text, match: false }];
  const parts: { text: string; match: boolean }[] = [];
  let index = 0;
  for (;;) {
    const found = haystack.indexOf(needle, index);
    if (found < 0 || parts.length > 40) break;
    if (found > index) parts.push({ text: text.slice(index, found), match: false });
    parts.push({ text: text.slice(found, found + needle.length), match: true });
    index = found + needle.length;
  }
  if (index < text.length) parts.push({ text: text.slice(index), match: false });
  return parts.length ? parts : [{ text, match: false }];
}
