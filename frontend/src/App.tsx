import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import Icon from "./components/Icon";
import {
  apiError,
  download,
  exportMarkdown,
  isIdea,
  mergeIdeas,
  mutationName,
  mutations,
  readStorage,
  storeLocal,
  wordCount,
  wordDiff,
  type Idea,
  type Mutation,
} from "./lib/ideas";
import { useWorkspace } from "./lib/useWorkspace";
import "./App.css";

const IdeaGraph = lazy(() => import("./components/IdeaGraph"));
const starters = [
  {
    category: "Community",
    text: "Turn empty city rooftops into shared neighborhood gardens.",
  },
  {
    category: "Learning",
    text: "A library where people borrow skills instead of books.",
  },
  {
    category: "Climate",
    text: "Make repairing everyday objects easier than replacing them.",
  },
  {
    category: "Technology",
    text: "Build a calmer internet that rewards curiosity and collaboration.",
  },
  {
    category: "Creativity",
    text: "A museum of unfinished ideas that anyone can continue.",
  },
  {
    category: "Everyday life",
    text: "Create tiny adventures for people on their daily commute.",
  },
];
const validBookmarks = (x: unknown): x is number[] =>
  Array.isArray(x) &&
  x.length <= 100 &&
  x.every((n) => Number.isSafeInteger(n) && n > 0);
const validDraft = (x: unknown): x is string =>
  typeof x === "string" && x.length <= 2000;
const validTheme = (x: unknown): x is string => x === "light" || x === "dark";
function hashId() {
  const match = location.hash.match(/^#idea-([1-9]\d{0,9})$/);
  return match ? Number(match[1]) : null;
}

export default function App() {
  const [draft, setDraft] = useState(() =>
    readStorage("idea-evolution:draft", "", validDraft),
  );
  const [bookmarks, setBookmarks] = useState<number[]>(() =>
    readStorage("idea-evolution:bookmarks", [], validBookmarks),
  );
  const [theme, setTheme] = useState(() =>
    readStorage(
      "idea-evolution:theme",
      matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
      validTheme,
    ),
  );
  const [view, setView] = useState<"graph" | "list">(() =>
    innerWidth < 720 ? "list" : "graph",
  );
  const [search, setSearch] = useState(""),
    [debouncedSearch, setDebouncedSearch] = useState("");
  const [mutation, setMutation] = useState(""),
    [root, setRoot] = useState(""),
    [savedOnly, setSavedOnly] = useState(false);
  const [horizontal, setHorizontal] = useState(false),
    [focusPath, setFocusPath] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(hashId);
  const [selectedSnapshot, setSelectedSnapshot] = useState<Idea | null>(null);
  const [lineageState, setLineageState] = useState<{
    id: number | null;
    ideas: Idea[];
  }>({ id: null, ideas: [] });
  const [lineageError, setLineageError] = useState("");
  const [submitting, setSubmitting] = useState<Mutation | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [branchDraft, setBranchDraft] = useState(false),
    [inspectorTab, setInspectorTab] = useState<"detail" | "compare">("detail");
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [storageAvailable] = useState(() => {
    try {
      const key = "idea-evolution:storage-check";
      localStorage.setItem(key, "1");
      localStorage.removeItem(key);
      return true;
    } catch {
      return false;
    }
  });
  const composer = useRef<HTMLTextAreaElement>(null),
    searchInput = useRef<HTMLInputElement>(null),
    help = useRef<HTMLDialogElement>(null);
  const pendingRequest = useRef<{ body: string; key: string } | null>(null),
    submitLock = useRef(false);
  const board = useWorkspace({
    q: debouncedSearch,
    mutation,
    root,
    saved: savedOnly,
    bookmarks,
  });
  const lineage = useMemo(
    () => (lineageState.id === selectedId ? lineageState.ideas : []),
    [lineageState, selectedId],
  );
  const selected =
    board.ideas.find((i) => i.id === selectedId) ??
    lineage.find((i) => i.id === selectedId) ??
    (selectedSnapshot?.id === selectedId ? selectedSnapshot : null);
  const parent = selected
    ? (lineage.find((i) => i.id === selected.parent_id) ??
      board.ideas.find((i) => i.id === selected.parent_id))
    : undefined;
  const children = selected
    ? board.ideas.filter((i) => i.parent_id === selected.id)
    : [];

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 280);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", theme === "dark" ? "#131c17" : "#f8f9f6");
    storeLocal("idea-evolution:theme", theme);
  }, [theme]);
  useEffect(() => {
    storeLocal("idea-evolution:draft", draft);
  }, [draft]);
  useEffect(() => {
    storeLocal("idea-evolution:bookmarks", bookmarks);
  }, [bookmarks]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    const onHash = () => setSelectedId(hashId());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (selectedId === null) return;
    const controller = new AbortController();
    void fetch(`/api/idea/${selectedId}/lineage`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiError(response));
        const data: unknown = await response.json();
        if (!Array.isArray(data) || !data.every(isIdea))
          throw new Error("The idea could not be read.");
        if (!controller.signal.aborted) {
          setLineageState({ id: selectedId, ideas: data });
          setLineageError("");
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setLineageError(
            reason instanceof Error
              ? reason.message
              : "Could not load this idea.",
          );
      });
    return () => controller.abort();
  }, [selectedId]);

  const selectIdea = useCallback((idea: Idea) => {
    setSelectedId(idea.id);
    setSelectedSnapshot(idea);
    setLineageError("");
    setBranchDraft(false);
    setInspectorTab("detail");
    history.replaceState(null, "", `#idea-${idea.id}`);
    if (innerWidth < 720)
      requestAnimationFrame(() =>
        document.querySelector(".inspector.has-selection")?.scrollIntoView({
          behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "instant"
            : "smooth",
          block: "start",
        }),
      );
  }, []);
  const clearSelection = useCallback(() => {
    setSelectedId(null);
    setFocusPath(false);
    setBranchDraft(false);
    history.replaceState(null, "", location.pathname + location.search);
  }, []);
  const toggleBookmark = useCallback(
    (idea: Idea) => {
      setBookmarks((previous) =>
        previous.includes(idea.id)
          ? previous.filter((id) => id !== idea.id)
          : previous.length < 100
            ? [...previous, idea.id]
            : previous,
      );
      if (!bookmarks.includes(idea.id) && bookmarks.length >= 100)
        setNotice("You can save up to 100 ideas on this device.");
    },
    [bookmarks],
  );
  const resetFilters = () => {
    setSearch("");
    setDebouncedSearch("");
    setMutation("");
    setRoot("");
    setSavedOnly(false);
    setFocusPath(false);
  };
  const focusComposer = () =>
    requestAnimationFrame(() => {
      composer.current?.focus();
      composer.current?.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "center",
      });
    });
  const startSeed = () => {
    setBranchDraft(false);
    setLibraryOpen(true);
    focusComposer();
  };
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLElement &&
        (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) ||
          event.target.isContentEditable)
      )
        return;
      if (event.ctrlKey || event.metaKey || event.altKey || help.current?.open)
        return;
      if (event.key === "/") {
        event.preventDefault();
        searchInput.current?.focus();
      }
      if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        setLibraryOpen(true);
        setBranchDraft(false);
        requestAnimationFrame(() => composer.current?.focus());
      }
      if (event.key === "Escape") clearSelection();
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [clearSelection]);

  async function submit(operation: Mutation, event?: FormEvent) {
    event?.preventDefault();
    if (
      submitLock.current ||
      (operation === "base" && !draft.trim()) ||
      (operation !== "base" && !selected)
    )
      return;
    submitLock.current = true;
    setSubmitting(operation);
    setError("");
    const body = JSON.stringify({
      content: operation === "base" ? draft.trim() : "",
      parent_id:
        operation === "base"
          ? branchDraft
            ? (selected?.id ?? null)
            : null
          : selected?.id,
      mutation: operation,
    });
    if (pendingRequest.current?.body !== body)
      pendingRequest.current = { body, key: crypto.randomUUID() };
    try {
      const response = await fetch("/api/idea", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": pendingRequest.current.key,
        },
        body,
        signal: AbortSignal.timeout(15_000),
      });
      if (!response.ok) throw new Error(await apiError(response));
      const idea: unknown = await response.json();
      if (!isIdea(idea))
        throw new Error(
          "The response could not be read. Retry to check your submission.",
        );
      pendingRequest.current = null;
      if (operation === "base") {
        setDraft("");
        resetFilters();
      }
      board.upsert(idea);
      selectIdea(idea);
      setNotice(
        operation === "base"
          ? "Your idea is planted. Let it grow."
          : `${mutationName(operation)} complete. A new branch is ready.`,
      );
      setLibraryOpen(false);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.name === "TimeoutError"
            ? "The server took too long. Retry your action to check the same submission; your draft is still here."
            : reason.message
          : "Unable to publish. Your draft is still here.",
      );
    } finally {
      submitLock.current = false;
      setSubmitting(null);
    }
  }

  async function copyText(text: string, message: string) {
    try {
      await navigator.clipboard.writeText(text);
      setNotice(message);
    } catch {
      setError(
        "Clipboard access is unavailable. You can select and copy the text directly.",
      );
    }
  }
  function exportIdeas(format: "json" | "md", items = board.ideas) {
    if (!items.length) return;
    const name = `idea-evolution-${new Date().toISOString().slice(0, 10)}`;
    if (format === "json")
      download(
        `${name}.json`,
        JSON.stringify(
          {
            format: "idea-evolution",
            version: 1,
            exported_at: new Date().toISOString(),
            scope: "loaded selection",
            ideas: items,
          },
          null,
          2,
        ),
        "application/json",
      );
    else
      download(
        `${name}.md`,
        exportMarkdown(items),
        "text/markdown;charset=utf-8",
      );
    setNotice(
      `Exported ${items.length} loaded ${items.length === 1 ? "idea" : "ideas"}.`,
    );
  }

  const graphIdeas = useMemo(() => {
    if (!focusPath || !selected) return board.ideas.slice(-160);
    const nodes = mergeIdeas(lineage, [selected]),
      included = new Set(nodes.map((i) => i.id));
    for (let step = 0; step < 32; step++)
      for (const idea of board.ideas) {
        if (idea.parent_id !== null && included.has(idea.parent_id))
          included.add(idea.id);
      }
    return mergeIdeas(
      nodes,
      board.ideas.filter((i) => included.has(i.id)),
    ).slice(0, 160);
  }, [board.ideas, lineage, selected, focusPath]);
  const diff = useMemo(
    () =>
      parent && selected ? wordDiff(parent.content, selected.content) : null,
    [parent, selected],
  );
  const activeFilters = !!(
    search ||
    mutation ||
    root ||
    savedOnly ||
    focusPath
  );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark">
            <Icon name="graph" size={23} />
          </span>
          <span>
            idea<span className="brand-light">evolution</span>
            <small>THE POSSIBILITY LAB</small>
          </span>
        </a>
        <div className="header-center">
          <span className="public-dot" /> Community workspace{" "}
          <span className="pill">Public</span>
        </div>
        <div className="top-actions">
          <button
            className="icon-button"
            onClick={() => help.current?.showModal()}
            aria-label="How it works"
          >
            <Icon name="help" />
          </button>
          <button
            className="icon-button"
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
          >
            <Icon name={theme === "light" ? "moon" : "sun"} />
          </button>
          <button className="button primary new-idea-top" onClick={startSeed}>
            <Icon name="plus" /> New idea
          </button>
        </div>
      </header>
      <div className="workspace-shell">
        <aside
          className={`library ${libraryOpen ? "mobile-open" : ""}`}
          aria-label="Idea library"
        >
          <div className="library-title">
            <span className="eyebrow">YOUR EXPLORER</span>
            <button
              className="icon-button mobile-close"
              onClick={() => setLibraryOpen(false)}
              aria-label="Close library"
            >
              <Icon name="close" />
            </button>
          </div>
          <nav className="library-nav" aria-label="Workspace filters">
            <button
              className={!savedOnly && !root ? "active" : ""}
              onClick={resetFilters}
            >
              <Icon name="graph" />
              <span>All ideas</span>
              <span className="count">{board.stats?.total ?? "—"}</span>
            </button>
            <button
              className={savedOnly ? "active" : ""}
              onClick={() => {
                setSavedOnly(true);
                setRoot("");
                setFocusPath(false);
              }}
            >
              <Icon name="star" />
              <span>Saved on this device</span>
              <span className="count">{bookmarks.length}</span>
            </button>
          </nav>
          <div className="seed-browser">
            <div className="section-label">
              <span>RECENT SEED IDEAS</span>
              <span>{board.stats?.seeds ?? "—"}</span>
            </div>
            <div className="seed-list">
              {board.seeds
                .slice()
                .reverse()
                .map((idea) => (
                  <button
                    key={idea.id}
                    className={root === String(idea.id) ? "active" : ""}
                    onClick={() => {
                      setRoot(String(idea.id));
                      setSavedOnly(false);
                      setFocusPath(false);
                      selectIdea(idea);
                      setLibraryOpen(false);
                    }}
                  >
                    <span className="seed-dot" />
                    <span>{idea.content}</span>
                    <Icon name="chevron" size={13} />
                  </button>
                ))}
              {!board.seeds.length && (
                <p className="muted small">
                  Your next idea could start something.
                </p>
              )}
            </div>
          </div>
          <form
            className="composer"
            onSubmit={(event) => void submit("base", event)}
          >
            <div className="composer-heading">
              <span className="composer-icon">
                <Icon name="spark" />
              </span>
              <div>
                <h2>
                  {branchDraft && selected
                    ? "A different direction"
                    : "Plant a new idea"}
                </h2>
                <p>
                  {branchDraft && selected
                    ? `Branching from #${selected.id}`
                    : "A small thought. A world of possibilities."}
                </p>
              </div>
            </div>
            <label className="sr-only" htmlFor="idea-draft">
              Your new idea
            </label>
            <textarea
              id="idea-draft"
              ref={composer}
              value={draft}
              maxLength={2000}
              rows={4}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="What if we could…"
              onKeyDown={(event) => {
                if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="composer-meta">
              <span>
                {storageAvailable
                  ? "Draft stays on this device"
                  : "Storage unavailable; keep this tab open"}
              </span>
              <span>{draft.length}/2000</span>
            </div>
            <button
              className="button primary full"
              type="submit"
              disabled={!draft.trim() || submitting !== null}
            >
              {submitting === "base" ? (
                <>
                  <span className="spinner" /> Planting…
                </>
              ) : (
                <>
                  Plant idea <Icon name="arrow" size={17} />
                </>
              )}
            </button>
            {branchDraft && (
              <button
                type="button"
                className="text-button"
                onClick={() => setBranchDraft(false)}
              >
                Start a separate seed instead
              </button>
            )}
            <details className="composer-starters">
              <summary>Try a starting point</summary>
              {starters.map((starter) => (
                <button
                  type="button"
                  key={starter.category}
                  onClick={() => {
                    setDraft(starter.text);
                    setBranchDraft(false);
                    focusComposer();
                  }}
                >
                  {starter.category}
                  <Icon name="arrow" size={12} />
                </button>
              ))}
            </details>
            <p className="privacy-note">
              <Icon name="lock" size={12} /> Published ideas are public. Keep
              personal details and secrets out.
            </p>
          </form>
          <div className="library-footer">
            <span className="unison-mark">u</span>
            <span>
              Powered by <strong>Unison</strong>
              <small>Pure functions. Reproducible results.</small>
            </span>
          </div>
        </aside>
        <main id="workspace" className="workspace" tabIndex={-1}>
          <section className="workspace-intro">
            <div>
              <div className="eyebrow">
                THINK IT. BRANCH IT. SEE WHAT GROWS.
              </div>
              <h1>
                The idea garden<span>.</span>
              </h1>
              <p>Good ideas get better when they have room to evolve.</p>
            </div>
            <div className="workspace-stats" aria-label="Workspace statistics">
              <div>
                <strong>{board.stats?.total ?? "—"}</strong>
                <span>ideas planted</span>
              </div>
              <div>
                <strong>{board.stats?.seeds ?? "—"}</strong>
                <span>seed ideas</span>
              </div>
              <div>
                <strong>{board.stats?.max_depth ?? "—"}</strong>
                <span>deepest branch</span>
              </div>
            </div>
          </section>
          <div className="workspace-toolbar">
            <div className="search-box">
              <Icon name="search" size={17} />
              <input
                ref={searchInput}
                value={search}
                maxLength={200}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search the whole garden…"
                aria-label="Search all ideas"
              />
              {search ? (
                <button
                  className="icon-button tiny"
                  onClick={() => setSearch("")}
                  aria-label="Clear search"
                >
                  <Icon name="close" size={14} />
                </button>
              ) : (
                <kbd>/</kbd>
              )}
            </div>
            <div
              className="view-switch"
              role="group"
              aria-label="Workspace view"
            >
              <button
                aria-pressed={view === "graph"}
                onClick={() => setView("graph")}
              >
                <Icon name="graph" size={16} />
                <span>Graph</span>
              </button>
              <button
                aria-pressed={view === "list"}
                onClick={() => setView("list")}
              >
                <Icon name="list" size={16} />
                <span>List</span>
              </button>
            </div>
            <details className="export-menu">
              <summary className="icon-button" aria-label="Export loaded ideas">
                <Icon name="download" />
              </summary>
              <div>
                <span>EXPORT LOADED IDEAS</span>
                <button
                  disabled={!board.ideas.length}
                  onClick={() => exportIdeas("json")}
                >
                  Download JSON
                </button>
                <button
                  disabled={!board.ideas.length}
                  onClick={() => exportIdeas("md")}
                >
                  Download Markdown
                </button>
              </div>
            </details>
          </div>
          <div className="filterbar">
            <button
              className="mobile-library-toggle button subtle"
              onClick={() => setLibraryOpen(!libraryOpen)}
            >
              <Icon name="plus" size={15} /> Ideas & draft
            </button>
            <label>
              <span className="sr-only">Filter by transformation</span>
              <select
                value={mutation}
                onChange={(event) => setMutation(event.target.value)}
              >
                <option value="">All transformations</option>
                <option value="base">Seeds & custom branches</option>
                {mutations.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            {activeFilters && (
              <button className="text-button" onClick={resetFilters}>
                Clear filters
              </button>
            )}
            <span className="filter-count">
              {board.loading
                ? "Finding ideas…"
                : `${board.ideas.length}${board.hasMore ? "+" : ""} loaded`}
            </span>
            <span className={`connection ${board.connection}`} role="status">
              <span />
              {board.connection === "live"
                ? "Live sync"
                : board.connection === "offline"
                  ? "Offline"
                  : "Reconnecting"}
            </span>
          </div>
          {(error || board.error) && (
            <div className="error-banner" role="alert">
              <span>{error || board.error}</span>
              <button
                className="text-button"
                onClick={() => {
                  setError("");
                  board.refresh();
                }}
              >
                Refresh board
              </button>
              <button
                className="icon-button tiny"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <Icon name="close" size={15} />
              </button>
            </div>
          )}
          {board.connection === "offline" && (
            <div className="offline-banner">
              You’re offline. Your draft is safe on this device. Reconnect to
              publish or sync ideas.
            </div>
          )}
          <div
            className={`canvas ${view === "list" ? "list-canvas" : ""}`}
            aria-busy={board.loading}
          >
            {board.loading ? (
              <div className="empty-state">
                <span className="spinner" />
                <p>Opening the garden…</p>
              </div>
            ) : board.ideas.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">
                  <Icon
                    name={savedOnly ? "star" : search ? "search" : "spark"}
                    size={32}
                  />
                </span>
                <h2>
                  {savedOnly
                    ? "Keep the ideas that stay with you."
                    : activeFilters
                      ? "A little more room to explore."
                      : "Something good starts with a thought."}
                </h2>
                <p>
                  {savedOnly
                    ? "Save an idea with the star. Your collection stays on this device."
                    : activeFilters
                      ? "No ideas match these filters. Try another word or clear the filters."
                      : "Plant your first idea, then take it in a new direction."}
                </p>
                <button
                  className="button primary"
                  onClick={activeFilters ? resetFilters : startSeed}
                >
                  {activeFilters ? "Show all ideas" : "Plant the first idea"}
                  <Icon name="arrow" size={16} />
                </button>
              </div>
            ) : view === "graph" ? (
              <Suspense
                fallback={
                  <div className="empty-state">
                    <span className="spinner" />
                    <p>Drawing the branches…</p>
                  </div>
                }
              >
                <IdeaGraph
                  ideas={graphIdeas}
                  selectedId={selectedId}
                  bookmarks={bookmarks}
                  horizontal={horizontal}
                  theme={theme}
                  onSelect={selectIdea}
                  onBookmark={toggleBookmark}
                />
              </Suspense>
            ) : (
              <div className="idea-list">
                {board.ideas
                  .slice()
                  .reverse()
                  .map((idea) => (
                    <article
                      key={idea.id}
                      className={`idea-list-card ${idea.id === selectedId ? "selected" : ""}`}
                    >
                      <button
                        className="list-idea-content"
                        onClick={() => selectIdea(idea)}
                      >
                        <div className="list-meta">
                          <span className={`tag ${idea.mutation}`}>
                            {idea.parent_id === null
                              ? "Seed idea"
                              : mutationName(idea.mutation)}
                          </span>
                          <span>
                            #{String(idea.id).padStart(3, "0")} · depth{" "}
                            {idea.depth}
                          </span>
                        </div>
                        <p>{idea.content}</p>
                        <span className="list-bottom">
                          {idea.created_at
                            ? new Date(idea.created_at).toLocaleDateString(
                                undefined,
                                { month: "short", day: "numeric" },
                              )
                            : "Earlier idea"}
                          <span>
                            Explore idea <Icon name="arrow" size={14} />
                          </span>
                        </span>
                      </button>
                      <button
                        className={`icon-button list-save ${bookmarks.includes(idea.id) ? "is-saved" : ""}`}
                        aria-label={`${bookmarks.includes(idea.id) ? "Unsave" : "Save"} idea ${idea.id}`}
                        aria-pressed={bookmarks.includes(idea.id)}
                        onClick={() => toggleBookmark(idea)}
                      >
                        <Icon name="star" size={17} />
                      </button>
                    </article>
                  ))}
              </div>
            )}
            {view === "graph" && board.ideas.length > 0 && (
              <div className="canvas-tools">
                <button
                  className="canvas-chip"
                  onClick={() => setHorizontal((h) => !h)}
                >
                  <Icon name="graph" size={14} />
                  {horizontal ? "Horizontal" : "Vertical"}
                </button>
                {selected && (
                  <button
                    className={`canvas-chip ${focusPath ? "active" : ""}`}
                    aria-pressed={focusPath}
                    onClick={() => setFocusPath((f) => !f)}
                  >
                    <Icon name="focus" size={14} />
                    {focusPath ? "Show all branches" : "Focus lineage"}
                  </button>
                )}
              </div>
            )}
          </div>
          <footer className="canvas-footer">
            <span>
              {view === "graph"
                ? "Scroll to zoom · drag the canvas to explore"
                : "Select an idea to explore its next chapter"}
              {view === "graph" && board.ideas.length > 160
                ? " · Graph shows up to 160 nodes"
                : ""}
            </span>
            {board.hasMore && (
              <button
                className="text-button"
                disabled={board.moreBusy}
                onClick={() => void board.loadMore()}
              >
                {board.moreBusy ? "Loading…" : "Load older ideas"}{" "}
                <Icon name="chevron" size={13} />
              </button>
            )}
            <span className="engine-label">
              <span /> Deterministic by design
            </span>
          </footer>
        </main>
        <aside
          className={`inspector ${selectedId !== null ? "has-selection" : ""}`}
          aria-label="Idea details"
        >
          {selected ? (
            <>
              <div className="inspector-heading">
                <span className="eyebrow">IDEA INSPECTOR</span>
                <button
                  className="icon-button"
                  onClick={clearSelection}
                  aria-label="Close idea details"
                >
                  <Icon name="close" size={17} />
                </button>
              </div>
              <div className="selected-title">
                <span className={`tag ${selected.mutation}`}>
                  {selected.parent_id === null
                    ? "Seed idea"
                    : mutationName(selected.mutation)}
                </span>
                <span className="mono">
                  #{String(selected.id).padStart(3, "0")}
                </span>
              </div>
              <h2>A thought in progress.</h2>
              <div
                className="inspector-tabs"
                role="group"
                aria-label="Idea details view"
              >
                <button
                  aria-pressed={inspectorTab === "detail"}
                  onClick={() => setInspectorTab("detail")}
                >
                  Overview
                </button>
                <button
                  aria-pressed={inspectorTab === "compare"}
                  disabled={!parent}
                  onClick={() => setInspectorTab("compare")}
                >
                  Compare to parent
                </button>
              </div>
              {inspectorTab === "compare" && diff && parent ? (
                <div className="comparison">
                  <div>
                    <span className="eyebrow">PARENT #{parent.id}</span>
                    <p>
                      {diff.before.map((token, i) =>
                        token.changed ? (
                          <del key={i}>{token.text}</del>
                        ) : (
                          token.text
                        ),
                      )}
                    </p>
                  </div>
                  <div>
                    <span className="eyebrow">CURRENT #{selected.id}</span>
                    <p>
                      {diff.after.map((token, i) =>
                        token.changed ? (
                          <mark key={i}>{token.text}</mark>
                        ) : (
                          token.text
                        ),
                      )}
                    </p>
                  </div>
                  {diff.truncated && (
                    <p className="small muted">
                      Full text shown; word highlighting is limited for longer
                      ideas.
                    </p>
                  )}
                  <p className="small muted">
                    {wordCount(selected.content) - wordCount(parent.content) >=
                    0
                      ? "+"
                      : ""}
                    {wordCount(selected.content) - wordCount(parent.content)}{" "}
                    words from parent
                  </p>
                </div>
              ) : (
                <>
                  <p className="selected-content">{selected.content}</p>
                  <div className="idea-metrics">
                    <span>
                      <strong>{wordCount(selected.content)}</strong> words
                    </span>
                    <span>
                      <strong>{selected.depth}</strong> depth
                    </span>
                    <span>
                      <strong>{children.length}</strong> loaded branches
                    </span>
                  </div>
                  <div className="detail-actions">
                    <button
                      className={`button subtle ${bookmarks.includes(selected.id) ? "is-saved" : ""}`}
                      aria-pressed={bookmarks.includes(selected.id)}
                      onClick={() => toggleBookmark(selected)}
                    >
                      <Icon name="star" size={15} />
                      {bookmarks.includes(selected.id) ? "Saved" : "Save"}
                    </button>
                    <button
                      className="icon-button"
                      onClick={() =>
                        void copyText(selected.content, "Idea copied.")
                      }
                      aria-label="Copy idea text"
                    >
                      <Icon name="copy" size={16} />
                    </button>
                    <button
                      className="icon-button"
                      onClick={() =>
                        void copyText(
                          `${location.origin}/#idea-${selected.id}`,
                          "Link copied. Anyone with the link can view this public idea.",
                        )
                      }
                      aria-label="Copy public idea link"
                    >
                      <Icon name="share" size={16} />
                    </button>
                  </div>
                </>
              )}
              {lineageError && (
                <p className="small error-text" role="alert">
                  {lineageError}
                </p>
              )}
              <section className="transform-section">
                <div className="section-label">
                  <span>TAKE IT SOMEWHERE NEW</span>
                  <Icon name="spark" size={14} />
                </div>
                <p className="small muted">
                  Pick a rule. Unison creates a reproducible branch.
                </p>
                <div className="transforms">
                  {mutations.map((m) => (
                    <button
                      key={m.id}
                      className={`transform-button ${m.id}`}
                      title={m.description}
                      disabled={submitting !== null || selected.depth >= 32}
                      onClick={() => void submit(m.id)}
                    >
                      <span className="transform-symbol">
                        {submitting === m.id ? (
                          <span className="spinner" />
                        ) : (
                          m.symbol
                        )}
                      </span>
                      <span>
                        <strong>{m.name}</strong>
                        <small>{m.description}</small>
                      </span>
                      <Icon name="chevron" size={15} />
                    </button>
                  ))}
                </div>
                <button
                  className="button subtle full custom-branch"
                  disabled={submitting !== null || selected.depth >= 32}
                  onClick={() => {
                    setBranchDraft(true);
                    setLibraryOpen(true);
                    focusComposer();
                  }}
                >
                  <Icon name="branch" size={15} /> Write your own branch
                </button>
                {selected.depth >= 32 && (
                  <p className="small muted">
                    This branch reached its depth limit. Plant a new seed to
                    continue.
                  </p>
                )}
              </section>
              {lineage.length > 1 && (
                <section className="lineage-section">
                  <div className="section-label">THE PATH HERE</div>
                  <ol>
                    {lineage.map((idea) => (
                      <li key={idea.id}>
                        <button
                          className={idea.id === selected.id ? "current" : ""}
                          onClick={() => selectIdea(idea)}
                        >
                          <span className={`lineage-dot ${idea.mutation}`} />
                          <span>
                            <strong>
                              #{idea.id} ·{" "}
                              {idea.parent_id === null
                                ? "Seed idea"
                                : mutationName(idea.mutation)}
                            </strong>
                            <small>{idea.content}</small>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ol>
                  <button
                    className="text-button"
                    onClick={() => exportIdeas("md", lineage)}
                  >
                    <Icon name="download" size={14} /> Export this lineage
                  </button>
                </section>
              )}
              {children.length > 0 && (
                <section className="children-section">
                  <div className="section-label">
                    NEXT CHAPTERS · {children.length} LOADED
                  </div>
                  {children.slice(0, 10).map((child) => (
                    <button
                      key={child.id}
                      className="child-link"
                      onClick={() => selectIdea(child)}
                    >
                      <span>
                        #{child.id} · {mutationName(child.mutation)}
                      </span>
                      <Icon name="arrow" size={14} />
                    </button>
                  ))}
                </section>
              )}
            </>
          ) : selectedId !== null ? (
            <div className="inspector-welcome">
              <Icon name="search" size={28} />
              <h2>
                {lineageError
                  ? "This idea is out of reach."
                  : "Opening this idea…"}
              </h2>
              <p>{lineageError || "Tracing its path through the garden."}</p>
              <button className="button subtle" onClick={clearSelection}>
                Back to exploring
              </button>
            </div>
          ) : (
            <>
              <div className="inspector-heading">
                <span className="eyebrow">
                  A LITTLE CURIOSITY GOES A LONG WAY
                </span>
                <Icon name="spark" size={16} />
              </div>
              <div className="inspector-welcome">
                <div className="garden-art" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                  <Icon name="spark" size={26} />
                </div>
                <span className="eyebrow">ONE THOUGHT. MANY DIRECTIONS.</span>
                <h2>
                  Where could your
                  <br />
                  next idea take you?
                </h2>
                <p>
                  Select an idea in the garden to see its story, or plant
                  something of your own.
                </p>
              </div>
              <div className="how-steps">
                <div>
                  <span>01</span>
                  <p>
                    <strong>Plant a thought</strong>Start with a question or a
                    possibility.
                  </p>
                </div>
                <div>
                  <span>02</span>
                  <p>
                    <strong>Explore a direction</strong>Expand, rephrase,
                    amplify or synthesize.
                  </p>
                </div>
                <div>
                  <span>03</span>
                  <p>
                    <strong>Follow what grows</strong>Compare branches. Save
                    what inspires you.
                  </p>
                </div>
              </div>
              <section className="starter-section">
                <div className="section-label">NEED A STARTING POINT?</div>
                {starters.map((starter) => (
                  <button
                    key={starter.category}
                    onClick={() => {
                      setDraft(starter.text);
                      startSeed();
                    }}
                  >
                    <span>
                      <small>{starter.category}</small>
                      <strong>{starter.text}</strong>
                    </span>
                    <Icon name="plus" size={16} />
                  </button>
                ))}
              </section>
              <p className="engine-note">
                Four pure text transformations, computed by Unison. The same
                input and rule produce the same output.
              </p>
            </>
          )}
        </aside>
      </div>
      <div className="toast-container" role="status" aria-live="polite">
        {notice && (
          <div className="toast">
            <Icon name="check" size={17} />
            {notice}
          </div>
        )}
      </div>
      <dialog ref={help} className="help-dialog" aria-labelledby="help-title">
        <div className="inspector-heading">
          <span className="eyebrow">WELCOME TO THE POSSIBILITY LAB</span>
          <button
            className="icon-button"
            aria-label="Close guide"
            onClick={() => help.current?.close()}
          >
            <Icon name="close" />
          </button>
        </div>
        <h2 id="help-title">Every idea is a starting point.</h2>
        <p>
          Plant an idea on the shared public board. Select it, choose a
          transformation, and explore a new branch. Each rule runs as a pure
          Unison function.
        </p>
        <div className="help-rules">
          {mutations.map((m) => (
            <div key={m.id}>
              <strong>
                {m.symbol} {m.name}
              </strong>
              <p>{m.description}</p>
            </div>
          ))}
        </div>
        <p>
          Save favorites and recover drafts on this device. Search the entire
          board, compare a branch with its parent, copy a public link, or export
          the ideas you’ve loaded.
        </p>
        <div className="shortcut-list">
          <span>
            <kbd>/</kbd> Search
          </span>
          <span>
            <kbd>N</kbd> New idea
          </span>
          <span>
            <kbd>Esc</kbd> Clear selection
          </span>
          <span>
            <kbd>Ctrl / ⌘ + Enter</kbd> Publish draft
          </span>
        </div>
        <p className="privacy-note">
          Everything you publish is public. Drafts and bookmarks are stored in
          this browser. Clearing browser data removes them. Live updates
          reconnect automatically; polling keeps the board current when live
          sync is unavailable.
        </p>
        <button
          className="button primary"
          onClick={() => help.current?.close()}
        >
          Let’s explore <Icon name="arrow" size={16} />
        </button>
      </dialog>
    </div>
  );
}
