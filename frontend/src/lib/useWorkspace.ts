import { useCallback, useEffect, useRef, useState } from "react";
import { apiError, isIdea, mergeIdeas, type Idea, type Stats } from "./ideas";
export interface BoardQuery {
  q: string;
  mutation: string;
  root: string;
  /** Restricts the board to these IDs (saved or planted on this device). */
  ids: number[] | null;
  leaves: boolean;
}
interface QueryConfig {
  q: string;
  mutation: string;
  root: string;
  ids: string | null;
  leaves: boolean;
}
function queryParams(config: QueryConfig) {
  const params = new URLSearchParams({ limit: "200" });
  if (config.q) params.set("q", config.q);
  if (config.mutation) params.set("mutation", config.mutation);
  if (config.root) params.set("root_id", config.root);
  if (config.ids) params.set("ids", config.ids);
  if (config.leaves) params.set("leaves_only", "true");
  return params;
}
interface Snapshot {
  key: string;
  ideas: Idea[];
  cursor: number;
  hasMore: boolean;
  error: string;
}
export function useWorkspace(query: BoardQuery) {
  const key = JSON.stringify({
    q: query.q,
    mutation: query.mutation,
    root: query.root,
    ids: query.ids ? query.ids.join(",") : null,
    leaves: query.leaves,
  } satisfies QueryConfig);
  const [snapshot, setSnapshot] = useState<Snapshot>({
    key: "",
    ideas: [],
    cursor: 0,
    hasMore: false,
    error: "",
  });
  const snapshotRef = useRef(snapshot);
  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);
  const [stats, setStats] = useState<Stats | null>(null),
    [seeds, setSeeds] = useState<Idea[]>([]);
  const [revision, setRevision] = useState(0),
    [contentEpoch, setContentEpoch] = useState(0);
  const knownVersion = useRef<number | null>(null),
    epoch = useRef(0);
  const [connection, setConnection] = useState("connecting"),
    [moreBusy, setMoreBusy] = useState(false),
    moreLock = useRef(false);
  // Live reaction totals pushed by the server or returned to this visitor.
  const [water, setWaterMap] = useState<Record<number, number>>({});
  const setWater = useCallback(
    (id: number, total: number) =>
      setWaterMap((previous) =>
        previous[id] === total ? previous : { ...previous, [id]: total },
      ),
    [],
  );
  const refresh = useCallback(() => setRevision((n) => n + 1), []);
  const invalidate = useCallback(
    (version: number) => {
      if (knownVersion.current !== null && version <= knownVersion.current)
        return;
      knownVersion.current = version;
      epoch.current++;
      setContentEpoch(epoch.current);
      setSnapshot({ key: "", ideas: [], cursor: 0, hasMore: false, error: "" });
      setStats(null);
      setSeeds([]);
      setWaterMap({});
      refresh();
    },
    [refresh],
  );
  const acceptVersion = useCallback(
    (value: string | number | null) => {
      const version = Number(value ?? 0);
      if (!Number.isSafeInteger(version) || version < 0) return false;
      if (knownVersion.current === null) {
        knownVersion.current = version;
        return true;
      }
      if (version > knownVersion.current) {
        invalidate(version);
        return false;
      }
      return version === knownVersion.current;
    },
    [invalidate],
  );
  const upsert = useCallback(
    (idea: Idea) => {
      // A response started before a moderation event cannot repopulate a purged cache.
      if (contentEpoch !== epoch.current) return;
      const config = JSON.parse(key) as QueryConfig;
      const matches =
        (!config.q ||
          idea.content.toLowerCase().includes(config.q.toLowerCase())) &&
        (!config.mutation || idea.mutation === config.mutation) &&
        (!config.root || idea.root_id === Number(config.root)) &&
        (config.ids === null ||
          config.ids.split(",").includes(String(idea.id)));
      if (matches)
        setSnapshot((prev) =>
          prev.key !== key || contentEpoch !== epoch.current
            ? prev
            : { ...prev, ideas: mergeIdeas(prev.ideas, [idea]) },
        );
      refresh();
    },
    [key, refresh, contentEpoch],
  );

  useEffect(() => {
    const controller = new AbortController();
    const started = epoch.current;
    async function load() {
      try {
        const config = JSON.parse(key) as QueryConfig;
        const params = queryParams(config);
        const previous = snapshotRef.current,
          incremental = previous.key === key && previous.ideas.length > 0;
        if (incremental) params.set("after", String(previous.cursor));
        let ideas: Idea[] = [],
          hasMore = false;
        if (config.ids !== "") {
          const response = await fetch("/api/idea?" + params, {
            signal: controller.signal,
          });
          if (!response.ok) throw new Error(await apiError(response));
          if (
            controller.signal.aborted ||
            !acceptVersion(response.headers.get("X-Board-Revision"))
          )
            return;
          const body: unknown = await response.json();
          if (!Array.isArray(body) || !body.every(isIdea))
            throw new Error("The server returned an unexpected response.");
          ideas = body;
          const totals = body.filter((idea) => typeof idea.water === "number");
          if (totals.length)
            setWaterMap((previous) => {
              const next = { ...previous };
              for (const idea of totals) next[idea.id] = idea.water!;
              return next;
            });
          hasMore = response.headers.get("X-Has-More") === "true";
        }
        if (controller.signal.aborted || started !== epoch.current) return;
        setSnapshot((prev) => ({
          key,
          ideas:
            incremental && prev.key === key
              ? mergeIdeas(prev.ideas, ideas)
              : ideas,
          hasMore: incremental ? prev.hasMore : hasMore,
          cursor: Math.max(
            incremental ? prev.cursor : 0,
            ...ideas.map((i) => i.id),
          ),
          error: "",
        }));
        if (incremental && hasMore) setRevision((n) => n + 1);
        const [summary, roots] = await Promise.all([
          fetch("/api/stats", { signal: controller.signal }),
          fetch("/api/idea?roots_only=true&limit=100", {
            signal: controller.signal,
          }),
        ]);
        if (summary.ok) {
          const data = await summary.json();
          if (
            !controller.signal.aborted &&
            started === epoch.current &&
            acceptVersion(data.board_revision ?? 0)
          )
            setStats(data);
        }
        if (roots.ok) {
          const data: unknown = await roots.json();
          if (
            !controller.signal.aborted &&
            started === epoch.current &&
            acceptVersion(roots.headers.get("X-Board-Revision")) &&
            Array.isArray(data) &&
            data.every(isIdea)
          )
            setSeeds(data);
        }
      } catch (error) {
        if (!controller.signal.aborted && started === epoch.current)
          setSnapshot((prev) => ({
            key,
            ideas: prev.key === key ? prev.ideas : [],
            hasMore: prev.key === key && prev.hasMore,
            cursor: prev.key === key ? prev.cursor : 0,
            error:
              error instanceof Error
                ? error.message
                : "Cannot reach the workspace. Please try again.",
          }));
      }
    }
    void load();
    return () => controller.abort();
  }, [key, revision, acceptVersion]);

  const loadMore = useCallback(async () => {
    if (moreLock.current || !snapshot.ideas.length || !snapshot.hasMore) return;
    moreLock.current = true;
    setMoreBusy(true);
    const started = epoch.current;
    try {
      const params = queryParams(JSON.parse(key) as QueryConfig);
      params.set(
        "before",
        String(Math.min(...snapshot.ideas.map((i) => i.id))),
      );
      const response = await fetch("/api/idea?" + params, {
        signal: AbortSignal.timeout(10_000),
      });
      if (!response.ok) throw new Error(await apiError(response));
      if (
        !acceptVersion(response.headers.get("X-Board-Revision")) ||
        started !== epoch.current
      )
        return;
      const body: unknown = await response.json();
      if (!Array.isArray(body) || !body.every(isIdea))
        throw new Error("Invalid idea response");
      setSnapshot((prev) =>
        prev.key !== key || started !== epoch.current
          ? prev
          : {
              ...prev,
              ideas: mergeIdeas(prev.ideas, body),
              hasMore: response.headers.get("X-Has-More") === "true",
            },
      );
    } catch (error) {
      setSnapshot((prev) =>
        prev.key !== key || started !== epoch.current
          ? prev
          : {
              ...prev,
              error:
                error instanceof Error
                  ? error.message
                  : "Could not load older ideas.",
            },
      );
    } finally {
      moreLock.current = false;
      setMoreBusy(false);
    }
  }, [key, snapshot.ideas, snapshot.hasMore, acceptVersion]);

  useEffect(() => {
    let disposed = false,
      socket: WebSocket | null = null,
      attempt = 0;
    let timer: ReturnType<typeof setTimeout>;
    const connect = () => {
      if (disposed || !navigator.onLine) {
        if (!disposed) setConnection("offline");
        return;
      }
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`,
      );
      socket.onopen = () => {
        if (!disposed) {
          attempt = 0;
          setConnection("live");
          refresh();
        }
      };
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (
            data?.event === "board_changed" &&
            Number.isSafeInteger(data.revision) &&
            data.revision >= 0
          )
            invalidate(data.revision);
          else if (
            data?.event === "water" &&
            Number.isSafeInteger(data.id) &&
            Number.isSafeInteger(data.water)
          )
            setWater(data.id, data.water);
          else if (data?.event === "ideas_changed" || isIdea(data)) refresh();
        } catch {
          /* Ignore unrelated events. */
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (disposed) return;
        setConnection(navigator.onLine ? "reconnecting" : "offline");
        timer = setTimeout(
          connect,
          Math.min(30_000, 1000 * 2 ** attempt++) + Math.random() * 500,
        );
      };
    };
    timer = setTimeout(connect, 0);
    const online = () => {
      clearTimeout(timer);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
      timer = setTimeout(connect, 0);
      refresh();
    };
    const offline = () => {
      clearTimeout(timer);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
      setConnection("offline");
    };
    const visibility = () => {
      if (!document.hidden) refresh();
    };
    window.addEventListener("online", online);
    window.addEventListener("offline", offline);
    document.addEventListener("visibilitychange", visibility);
    const poll = setInterval(() => {
      if (!document.hidden && navigator.onLine) refresh();
    }, 25_000);
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearInterval(poll);
      socket?.close();
      window.removeEventListener("online", online);
      window.removeEventListener("offline", offline);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [refresh, invalidate, setWater]);
  return {
    ideas: snapshot.key === key ? snapshot.ideas : [],
    loading: snapshot.key !== key,
    error: snapshot.key === key ? snapshot.error : "",
    hasMore: snapshot.key === key && snapshot.hasMore,
    stats,
    seeds,
    connection,
    moreBusy,
    loadMore,
    refresh,
    upsert,
    contentEpoch,
    water,
    setWater,
  };
}
