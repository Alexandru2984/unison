import { useCallback, useEffect, useRef, useState } from "react";
import { apiError, isIdea, mergeIdeas, type Idea, type Stats } from "./ideas";

export interface BoardQuery {
  q: string;
  mutation: string;
  root: string;
  saved: boolean;
  bookmarks: number[];
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
    ids: query.saved ? query.bookmarks.join(",") : null,
  });
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
  const [stats, setStats] = useState<Stats | null>(null);
  const [seeds, setSeeds] = useState<Idea[]>([]);
  const [revision, setRevision] = useState(0);
  const [connection, setConnection] = useState("connecting");
  const [moreBusy, setMoreBusy] = useState(false);
  const refresh = useCallback(() => setRevision((n) => n + 1), []);
  const upsert = useCallback(
    (idea: Idea) => {
      // A returned POST result is immediately visible, even without a socket.
      const config = JSON.parse(key);
      const matches =
        (!config.q ||
          idea.content.toLowerCase().includes(config.q.toLowerCase())) &&
        (!config.mutation || idea.mutation === config.mutation) &&
        (!config.root || idea.root_id === Number(config.root)) &&
        (config.ids === null ||
          config.ids.split(",").includes(String(idea.id)));
      if (matches)
        setSnapshot((prev) =>
          prev.key !== key
            ? prev
            : { ...prev, ideas: mergeIdeas(prev.ideas, [idea]) },
        );
      refresh();
    },
    [refresh, key],
  );

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const config = JSON.parse(key) as {
          q: string;
          mutation: string;
          root: string;
          ids: string | null;
        };
        const params = new URLSearchParams({ limit: "200" });
        if (config.q) params.set("q", config.q);
        if (config.mutation) params.set("mutation", config.mutation);
        if (config.root) params.set("root_id", config.root);
        if (config.ids) params.set("ids", config.ids);
        const previous = snapshotRef.current;
        const incremental = previous.key === key && previous.ideas.length > 0;
        if (incremental) params.set("after", String(previous.cursor));
        let ideas: Idea[] = [],
          hasMore = false;
        if (config.ids !== "") {
          const response = await fetch("/api/idea?" + params, {
            signal: controller.signal,
          });
          if (!response.ok) throw new Error(await apiError(response));
          const body: unknown = await response.json();
          if (!Array.isArray(body) || !body.every(isIdea))
            throw new Error("The server returned an unexpected response.");
          ideas = body;
          hasMore = response.headers.get("X-Has-More") === "true";
        }
        if (controller.signal.aborted) return;
        setSnapshot((prev) => ({
          key,
          ideas:
            incremental && prev.key === key
              ? mergeIdeas(prev.ideas, ideas)
              : ideas,
          hasMore: incremental ? prev.hasMore : hasMore,
          cursor: Math.max(
            incremental ? prev.cursor : 0,
            ...ideas.map((idea) => idea.id),
          ),
          error: "",
        }));
        // Incremental pages advance monotonically; another refresh catches up if needed.
        if (incremental && hasMore) setRevision((n) => n + 1);
        const [summary, roots] = await Promise.all([
          fetch("/api/stats", { signal: controller.signal }),
          fetch("/api/idea?roots_only=true&limit=100", {
            signal: controller.signal,
          }),
        ]);
        if (summary.ok) {
          const data = await summary.json();
          if (!controller.signal.aborted) setStats(data);
        }
        if (roots.ok) {
          const data: unknown = await roots.json();
          if (
            !controller.signal.aborted &&
            Array.isArray(data) &&
            data.every(isIdea)
          )
            setSeeds(data);
        }
      } catch (error) {
        if (!controller.signal.aborted)
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
  }, [key, revision]);

  const loadMore = useCallback(async () => {
    if (moreBusy || !snapshot.ideas.length) return;
    setMoreBusy(true);
    try {
      const config = JSON.parse(key);
      const params = new URLSearchParams({
        limit: "200",
        before: String(Math.min(...snapshot.ideas.map((i) => i.id))),
      });
      if (config.q) params.set("q", config.q);
      if (config.mutation) params.set("mutation", config.mutation);
      if (config.root) params.set("root_id", config.root);
      if (config.ids) params.set("ids", config.ids);
      const response = await fetch("/api/idea?" + params, {
        signal: AbortSignal.timeout(10_000),
      });
      if (!response.ok) throw new Error(await apiError(response));
      const body: unknown = await response.json();
      if (!Array.isArray(body) || !body.every(isIdea))
        throw new Error("Invalid idea response");
      setSnapshot((prev) =>
        prev.key !== key
          ? prev
          : {
              ...prev,
              ideas: mergeIdeas(prev.ideas, body),
              hasMore: response.headers.get("X-Has-More") === "true",
            },
      );
    } catch (error) {
      setSnapshot((prev) =>
        prev.key !== key
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
      setMoreBusy(false);
    }
  }, [key, moreBusy, snapshot.ideas]);

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
          if (isIdea(JSON.parse(event.data))) refresh();
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
  }, [refresh]);
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
  };
}
