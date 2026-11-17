import { type Page } from "@playwright/test";
import type { Idea } from "../src/lib/ideas";

export const fixtures: Idea[] = [
  {
    id: 1,
    parent_id: null,
    root_id: 1,
    depth: 0,
    content: "Turn empty city rooftops into shared neighborhood gardens.",
    mutation: "base",
    created_at: null,
  },
  {
    id: 2,
    parent_id: 1,
    root_id: 1,
    depth: 1,
    content: "A new perspective on shared neighborhood gardens.",
    mutation: "rephrase",
    created_at: "2026-11-17T10:00:00.000Z",
  },
  {
    id: 3,
    parent_id: null,
    root_id: 3,
    depth: 0,
    content: "A library where people borrow skills instead of books.",
    mutation: "base",
    created_at: "2026-11-17T10:01:00.000Z",
  },
];

// Browser tests isolate UI behavior from the public service. The API and actual
// compiled Unison engine have separate HTTP/resource and integration suites.
export async function mockBoard(page: Page, initial = fixtures) {
  const ideas = structuredClone(initial),
    writes: { body: unknown; key: string }[] = [];
  const requests = new Map<string, Idea>();
  let sockets = 0,
    failNextWrite = false;
  await page.routeWebSocket("**/ws", () => {
    sockets++;
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname;
    const reply = (
      body: unknown,
      status = 200,
      headers: Record<string, string> = {},
    ) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
        headers,
      });
    if (path === "/api/stats")
      return reply({
        total: ideas.length,
        seeds: ideas.filter((i) => i.parent_id === null).length,
        max_depth: Math.max(0, ...ideas.map((i) => i.depth)),
        capacity: 10000,
        max_branch_depth: 32,
      });
    const lineage = path.match(/^\/api\/idea\/(\d+)\/lineage$/);
    if (lineage) {
      const result: Idea[] = [];
      let id: number | null = Number(lineage[1]);
      while (id !== null) {
        const item = ideas.find((i) => i.id === id);
        if (!item) break;
        result.unshift(item);
        id = item.parent_id;
      }
      return result.length
        ? reply(result)
        : reply({ detail: "Idea not found" }, 404);
    }
    if (path !== "/api/idea") return reply({ detail: "Not found" }, 404);
    if (request.method() === "POST") {
      const body = request.postDataJSON(),
        key = request.headers()["idempotency-key"];
      writes.push({ body, key });
      if (failNextWrite) {
        failNextWrite = false;
        return reply(
          { detail: "Engine is busy. Please retry your action." },
          503,
        );
      }
      if (requests.has(key)) return reply(requests.get(key));
      const parent = ideas.find((i) => i.id === body.parent_id),
        id = Math.max(0, ...ideas.map((i) => i.id)) + 1;
      const idea: Idea = {
        id,
        parent_id: body.parent_id ?? null,
        content:
          body.mutation === "base"
            ? body.content
            : "A reproducible fixture result with a different perspective.",
        mutation: body.mutation,
        root_id: parent?.root_id ?? id,
        depth: parent ? parent.depth + 1 : 0,
        created_at: "2026-11-17T10:02:00.000Z",
      };
      ideas.push(idea);
      requests.set(key, idea);
      return reply(idea, 201);
    }
    const params = url.searchParams;
    let rows = ideas.filter(
      (i) =>
        (!params.get("q") ||
          i.content.toLowerCase().includes(params.get("q")!.toLowerCase())) &&
        (!params.get("mutation") || i.mutation === params.get("mutation")) &&
        (!params.get("ids") ||
          params.get("ids")!.split(",").includes(String(i.id))) &&
        (!params.get("root_id") ||
          i.root_id === Number(params.get("root_id"))) &&
        (!params.get("roots_only") || i.parent_id === null) &&
        (!params.has("after") || i.id > Number(params.get("after"))) &&
        (!params.has("before") || i.id < Number(params.get("before"))),
    );
    rows = rows.sort((a, b) =>
      params.has("after") ? a.id - b.id : b.id - a.id,
    );
    const limit = Number(params.get("limit") ?? 200),
      hasMore = rows.length > limit;
    rows = rows.slice(0, limit);
    const cursor = rows.at(-1)?.id;
    return reply(
      rows.sort((a, b) => a.id - b.id),
      200,
      { "X-Has-More": String(hasMore), "X-Next-Cursor": String(cursor ?? "") },
    );
  });
  return {
    ideas,
    writes,
    get sockets() {
      return sockets;
    },
    failWrite() {
      failNextWrite = true;
    },
  };
}
