import { apiError, isIdea, type Idea } from "./ideas.ts";
import type { Lang } from "./i18n.ts";

export interface PreviewRow {
  mutation: string;
  content: string | null;
  unchanged: boolean;
  existing_id: number | null;
}
export const DISCOVER_SECTIONS = [
  "trending",
  "branching",
  "unexplored",
  "fresh",
  "deepest",
] as const;
export type DiscoverSection = (typeof DISCOVER_SECTIONS)[number];
export type Discoveries = Record<DiscoverSection, Idea[]>;

const isPreviewRow = (value: unknown): value is PreviewRow => {
  if (!value || typeof value !== "object") return false;
  const row = value as PreviewRow;
  return (
    typeof row.mutation === "string" &&
    (row.content === null || typeof row.content === "string") &&
    typeof row.unchanged === "boolean" &&
    (row.existing_id === null ||
      row.existing_id === undefined ||
      (Number.isSafeInteger(row.existing_id) && row.existing_id > 0))
  );
};

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function json(
  url: string,
  lang: Lang,
  init: RequestInit = {},
): Promise<unknown> {
  const response = await fetch(url, init);
  if (!response.ok)
    throw new ApiError(await apiError(response, lang), response.status);
  return response.json();
}

function previewResults(data: unknown): PreviewRow[] {
  const rows = (data as { results?: unknown })?.results;
  if (!Array.isArray(rows) || !rows.every(isPreviewRow))
    throw new Error("The server returned an unexpected response.");
  return rows.map((row) => ({ ...row, existing_id: row.existing_id ?? null }));
}

export async function previewIdea(id: number, lang: Lang, signal: AbortSignal) {
  return previewResults(await json(`/api/idea/${id}/preview`, lang, { signal }));
}

export async function previewDraft(
  content: string,
  lang: Lang,
  signal: AbortSignal,
) {
  return previewResults(
    await json("/api/preview", lang, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
      signal,
    }),
  );
}

export async function waterIdea(id: number, lang: Lang) {
  const data = (await json(`/api/idea/${id}/water`, lang, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    signal: AbortSignal.timeout(10_000),
  })) as { water?: unknown; counted?: unknown };
  if (!Number.isSafeInteger(data?.water) || typeof data.counted !== "boolean")
    throw new Error("The server returned an unexpected response.");
  return { water: data.water as number, counted: data.counted };
}

export async function fetchDiscoveries(
  lang: Lang,
  signal: AbortSignal,
): Promise<Discoveries> {
  const data = (await json("/api/discover", lang, { signal })) as Record<
    string,
    unknown
  >;
  const result = {} as Discoveries;
  for (const name of DISCOVER_SECTIONS) {
    const rows = data?.[name];
    result[name] = Array.isArray(rows) ? rows.filter(isIdea).slice(0, 8) : [];
  }
  return result;
}

export async function fetchRandom(lang: Lang): Promise<Idea> {
  const idea = await json("/api/random", lang, {
    signal: AbortSignal.timeout(10_000),
  });
  if (!isIdea(idea))
    throw new Error("The server returned an unexpected response.");
  return idea;
}
