import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import BottomNav, { type NavTarget } from "./components/BottomNav";
import Composer from "./components/Composer";
import Discover from "./components/Discover";
import GraphView from "./components/GraphView";
import Header from "./components/Header";
import HelpDialog from "./components/HelpDialog";
import Icon from "./components/Icon";
import IdeaList from "./components/IdeaList";
import Inspector from "./components/Inspector";
import Library, { type Scope } from "./components/Library";
import ReportDialog from "./components/ReportDialog";
import { fetchRandom, waterIdea } from "./lib/api";
import { ideaCard } from "./lib/card";
import {
  detectLanguage,
  isLang,
  localizeError,
  translator,
  type Lang,
} from "./lib/i18n";
import {
  apiError,
  download,
  exportMarkdown,
  isIdea,
  mergeIdeas,
  mutations,
  readStorage,
  remember,
  storeLocal,
  validIdList,
  type Idea,
  type Mutation,
} from "./lib/ideas";
import { ideaLabel, ruleName, shortId } from "./lib/rules";
import { I18nContext } from "./lib/useI18n";
import { useWorkspace } from "./lib/useWorkspace";
import "./App.css";

type BoardView = "graph" | "list";
interface Watered {
  day: string;
  ids: number[];
}
const MAX_SAVED = 100;
const validDraft = (x: unknown): x is string =>
  typeof x === "string" && x.length <= 2000;
const validTheme = (x: unknown): x is string => x === "light" || x === "dark";
const validFlag = (x: unknown): x is boolean => typeof x === "boolean";
const validWatered = (x: unknown): x is Watered =>
  !!x &&
  typeof x === "object" &&
  typeof (x as Watered).day === "string" &&
  validIdList(500)((x as Watered).ids);
const utcDay = () => new Date().toISOString().slice(0, 10);
const typing = (target: EventTarget | null) =>
  target instanceof HTMLElement &&
  (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) ||
    target.isContentEditable);
const haptic = () => {
  try {
    navigator.vibrate?.(12);
  } catch {
    /* Vibration is optional. */
  }
};
// App shortcuts (manifest) open a view or the composer directly.
const launch = new URLSearchParams(location.search);
function hashId() {
  const match = location.hash.match(/^#idea-([1-9]\d{0,9})$/);
  return match ? Number(match[1]) : null;
}

export default function App() {
  const [lang, setLang] = useState<Lang>(() =>
    readStorage(
      "idea-evolution:lang",
      detectLanguage(navigator.languages ?? [navigator.language]),
      isLang,
    ),
  );
  const t = useMemo(() => translator(lang), [lang]);
  const i18n = useMemo(() => ({ lang, t }), [lang, t]);
  const [draft, setDraft] = useState(() =>
    readStorage("idea-evolution:draft", "", validDraft),
  );
  const [bookmarks, setBookmarks] = useState<number[]>(() =>
    readStorage("idea-evolution:bookmarks", [], validIdList(MAX_SAVED)),
  );
  const [mine, setMine] = useState<number[]>(() =>
    readStorage("idea-evolution:mine", [], validIdList(MAX_SAVED)),
  );
  const [today] = useState(utcDay);
  const [watered, setWatered] = useState<Watered>(() =>
    readStorage("idea-evolution:watered", { day: "", ids: [] }, validWatered),
  );
  const [onboarded, setOnboarded] = useState(() =>
    readStorage("idea-evolution:onboarded", false, validFlag),
  );
  const [theme, setTheme] = useState(() =>
    readStorage(
      "idea-evolution:theme",
      matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
      validTheme,
    ),
  );
  const [boardView, setBoardView] = useState<BoardView>(() =>
    innerWidth < 720 ? "list" : "graph",
  );
  const [discovering, setDiscovering] = useState(
    () => launch.get("view") === "discover",
  );
  const view = discovering ? "discover" : boardView;
  const [search, setSearch] = useState(""),
    [debouncedSearch, setDebouncedSearch] = useState("");
  const [mutation, setMutation] = useState(""),
    [root, setRoot] = useState(""),
    [scope, setScope] = useState<Scope>("all");
  const [focusPath, setFocusPath] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(hashId);
  const [selectedSnapshot, setSelectedSnapshot] = useState<{
    idea: Idea;
    epoch: number;
  } | null>(null);
  const [lineageState, setLineageState] = useState<{
    id: number | null;
    ideas: Idea[];
    epoch: number;
  }>({ id: null, ideas: [], epoch: 0 });
  const [lineageError, setLineageError] = useState("");
  const [submitting, setSubmitting] = useState<Mutation | null>(null),
    [watering, setWatering] = useState<number | null>(null),
    [surprising, setSurprising] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [fresh, setFresh] = useState<number | null>(null);
  const [branchDraft, setBranchDraft] = useState(false),
    [inspectorTab, setInspectorTab] = useState<"detail" | "compare">("detail");
  const [libraryOpen, setLibraryOpen] = useState(
    () => launch.get("action") === "plant",
  );
  const [reportTarget, setReportTarget] = useState<number | null>(null);
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
    ids: scope === "saved" ? bookmarks : scope === "mine" ? mine : null,
    leaves: scope === "leaves",
  });
  const lineage = useMemo(
    () =>
      lineageState.id === selectedId &&
      lineageState.epoch === board.contentEpoch
        ? lineageState.ideas
        : [],
    [lineageState, selectedId, board.contentEpoch],
  );
  const selected =
    board.ideas.find((i) => i.id === selectedId) ??
    lineage.find((i) => i.id === selectedId) ??
    (selectedSnapshot?.idea.id === selectedId &&
    selectedSnapshot.epoch === board.contentEpoch
      ? selectedSnapshot.idea
      : null);
  const parent = selected
    ? (lineage.find((i) => i.id === selected.parent_id) ??
      board.ideas.find((i) => i.id === selected.parent_id))
    : undefined;
  const childCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const idea of board.ideas)
      if (idea.parent_id !== null)
        counts.set(idea.parent_id, (counts.get(idea.parent_id) ?? 0) + 1);
    return counts;
  }, [board.ideas]);
  // The server counts every visible branch; loaded ones may be newer.
  const branches = useCallback(
    (idea: Idea) => Math.max(idea.children ?? 0, childCounts.get(idea.id) ?? 0),
    [childCounts],
  );
  const children = useMemo(
    () =>
      selected ? board.ideas.filter((i) => i.parent_id === selected.id) : [],
    [board.ideas, selected],
  );
  const wateredToday = watered.day === today ? watered.ids : [];
  const waterTotal = (idea: Idea) => board.water[idea.id] ?? idea.water ?? 0;

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
    document.documentElement.lang = lang;
    document.title = t("meta.title");
    document
      .querySelector('meta[name="description"]')
      ?.setAttribute("content", t("meta.description"));
    storeLocal("idea-evolution:lang", lang);
  }, [lang, t]);
  useEffect(() => {
    storeLocal("idea-evolution:draft", draft);
  }, [draft]);
  useEffect(() => {
    storeLocal("idea-evolution:bookmarks", bookmarks);
  }, [bookmarks]);
  useEffect(() => {
    storeLocal("idea-evolution:mine", mine);
  }, [mine]);
  useEffect(() => {
    storeLocal("idea-evolution:watered", watered);
  }, [watered]);
  useEffect(() => {
    if (onboarded) storeLocal("idea-evolution:onboarded", true);
  }, [onboarded]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (fresh === null) return;
    const timer = setTimeout(() => setFresh(null), 2400);
    return () => clearTimeout(timer);
  }, [fresh]);
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
          throw new Error("The server returned an unexpected response.");
        if (!controller.signal.aborted) {
          setLineageState({
            id: selectedId,
            ideas: data,
            epoch: board.contentEpoch,
          });
          setLineageError("");
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setLineageError(
            reason instanceof Error ? reason.message : "Could not load this idea.",
          );
      });
    return () => controller.abort();
  }, [selectedId, board.contentEpoch]);

  const selectIdea = useCallback(
    (idea: Idea) => {
      setSelectedId(idea.id);
      setSelectedSnapshot({ idea, epoch: board.contentEpoch });
      setLineageError("");
      setBranchDraft(false);
      setInspectorTab("detail");
      history.replaceState(null, "", `#idea-${idea.id}`);
    },
    [board.contentEpoch],
  );
  const openId = useCallback(
    (id: number) => {
      const known =
        board.ideas.find((i) => i.id === id) ??
        lineage.find((i) => i.id === id);
      if (known) return selectIdea(known);
      setSelectedId(id);
      setSelectedSnapshot(null);
      setLineageError("");
      setBranchDraft(false);
      setInspectorTab("detail");
      history.replaceState(null, "", `#idea-${id}`);
    },
    [board.ideas, lineage, selectIdea],
  );
  const clearSelection = useCallback(() => {
    setSelectedId(null);
    setFocusPath(false);
    setBranchDraft(false);
    history.replaceState(null, "", location.pathname + location.search);
  }, []);
  const toggleBookmark = useCallback(
    (idea: Idea) => {
      if (!bookmarks.includes(idea.id) && bookmarks.length >= MAX_SAVED)
        return setNotice(t("notice.saveLimit"));
      setBookmarks((previous) =>
        previous.includes(idea.id)
          ? previous.filter((id) => id !== idea.id)
          : [...previous, idea.id],
      );
    },
    [bookmarks, t],
  );
  const resetFilters = () => {
    setSearch("");
    setDebouncedSearch("");
    setMutation("");
    setRoot("");
    setScope("all");
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
  const plantText = (text: string) => {
    setDraft(text);
    startSeed();
  };
  const chooseScope = (next: Scope) => {
    setScope(next);
    setRoot("");
    setFocusPath(false);
    setDiscovering(false);
    setLibraryOpen(false);
  };
  const surprise = useCallback(async () => {
    if (surprising) return;
    setSurprising(true);
    try {
      const idea = await fetchRandom(lang);
      selectIdea(idea);
      setNotice(t("notice.random"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("error.idea"));
    } finally {
      setSurprising(false);
    }
  }, [surprising, lang, selectIdea, t]);

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (typing(event.target)) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (document.querySelector("dialog[open]")) return;
      const key = event.key;
      if (key === "/") {
        event.preventDefault();
        setDiscovering(false);
        requestAnimationFrame(() => searchInput.current?.focus());
      } else if (key.toLowerCase() === "n") {
        event.preventDefault();
        setLibraryOpen(true);
        setBranchDraft(false);
        requestAnimationFrame(() => composer.current?.focus());
      } else if (key.toLowerCase() === "r") {
        event.preventDefault();
        void surprise();
      } else if (key === "Escape") {
        setLibraryOpen(false);
        clearSelection();
      } else if (selected && key.startsWith("Arrow")) {
        // Walk the tree: up to the parent, down to a branch, sideways to siblings.
        let target: number | null | undefined = null;
        if (key === "ArrowUp") target = selected.parent_id;
        else if (key === "ArrowDown")
          target = board.ideas.find((i) => i.parent_id === selected.id)?.id;
        else {
          const siblings = board.ideas.filter(
            (i) => i.parent_id === selected.parent_id,
          );
          const index = siblings.findIndex((i) => i.id === selected.id);
          const step = key === "ArrowLeft" ? -1 : key === "ArrowRight" ? 1 : 0;
          if (index >= 0 && step) target = siblings[index + step]?.id;
        }
        if (target) {
          event.preventDefault();
          openId(target);
        }
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [clearSelection, surprise, selected, board.ideas, openId]);

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
      if (!response.ok) throw new Error(await apiError(response, lang));
      const idea: unknown = await response.json();
      if (!isIdea(idea)) throw new Error(t("error.unreadable"));
      pendingRequest.current = null;
      const duplicate = response.headers.get("X-Idea-Duplicate") === "true";
      if (operation === "base") {
        setDraft("");
        resetFilters();
        setDiscovering(false);
      }
      if (!duplicate) {
        setMine((previous) => remember(previous, idea.id, MAX_SAVED));
        setFresh(idea.id);
        haptic();
      }
      setOnboarded(true);
      board.upsert(idea);
      selectIdea(idea);
      setNotice(
        duplicate
          ? t("notice.duplicate")
          : operation === "base"
            ? t("notice.planted")
            : t("notice.branched", { rule: ruleName(t, operation) }),
      );
      setLibraryOpen(false);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.name === "TimeoutError"
            ? t("error.timeout")
            : reason.message
          : t("error.publish"),
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
      setError(t("error.clipboard"));
    }
  }
  async function share(idea: Idea) {
    const url = `${location.origin}/i/${idea.id}`;
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: "Idea Evolution", text: t("share.text"), url });
        return;
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === "AbortError")
          return;
      }
    }
    await copyText(url, t("notice.linkCopied"));
  }
  async function card(idea: Idea) {
    try {
      const image = await ideaCard(
        idea,
        {
          tag: ideaLabel(t, idea),
          footer: t("card.footer"),
          meta: `${shortId(idea.id)} · ${t("idea.depth")} ${idea.depth} · ${t("idea.waterCount", { n: waterTotal(idea) })}`,
        },
        theme === "dark",
      );
      download(`idea-${idea.id}.png`, image, "image/png");
      setNotice(t("notice.card"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("error.publish"));
    }
  }
  async function water(idea: Idea) {
    if (watering !== null) return;
    setWatering(idea.id);
    try {
      const result = await waterIdea(idea.id, lang);
      board.setWater(idea.id, result.water);
      setWatered((previous) => ({
        day: today,
        ids: remember(previous.day === today ? previous.ids : [], idea.id, 500),
      }));
      if (result.counted) {
        setNotice(t("notice.watered"));
        haptic();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("error.publish"));
    } finally {
      setWatering(null);
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
      items.length === 1
        ? t("export.doneOne")
        : t("export.done", { n: items.length }),
    );
  }
  function navigate(target: NavTarget) {
    if (target === "plant") return startSeed();
    setLibraryOpen(false);
    if (target === "discover") return setDiscovering(true);
    setDiscovering(false);
    if (target === "saved") {
      setScope("saved");
      setRoot("");
    } else if (scope === "saved") setScope("all");
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
  const activeFilters = !!(
    search ||
    mutation ||
    root ||
    scope !== "all" ||
    focusPath
  );
  const shownError = error || board.error;
  const discoverVersion = `${board.contentEpoch}:${board.stats?.total ?? ""}:${board.stats?.water ?? ""}`;

  return (
    <I18nContext.Provider value={i18n}>
      <div className={`app-shell view-${view}`}>
        <a className="skip-link" href="#workspace">
          {t("skip")}
        </a>
        <Header
          theme={theme}
          onToggleTheme={() => setTheme((v) => (v === "light" ? "dark" : "light"))}
          onToggleLanguage={() => setLang((v) => (v === "en" ? "ro" : "en"))}
          onHelp={() => help.current?.showModal()}
          onNewIdea={startSeed}
        />
        <div className="workspace-shell">
          <Library
            open={libraryOpen}
            scope={scope}
            root={root}
            counts={{
              all: board.stats?.total,
              saved: bookmarks.length,
              mine: mine.length,
            }}
            seeds={board.seeds}
            seedTotal={board.stats?.seeds}
            onClose={() => setLibraryOpen(false)}
            onScope={chooseScope}
            onSeed={(idea) => {
              setRoot(String(idea.id));
              setScope("all");
              setFocusPath(false);
              setDiscovering(false);
              selectIdea(idea);
              setLibraryOpen(false);
            }}
          >
            <Composer
              draft={draft}
              onDraft={setDraft}
              branchFrom={branchDraft && selected ? selected.id : null}
              planting={submitting === "base"}
              disabled={submitting !== null}
              storageAvailable={storageAvailable}
              composerRef={composer}
              onSubmit={(event) => void submit("base", event)}
              onCancelBranch={() => setBranchDraft(false)}
              onStarter={(text) => {
                setDraft(text);
                setBranchDraft(false);
                focusComposer();
              }}
            />
          </Library>
          <main id="workspace" className="workspace" tabIndex={-1}>
            <section className="workspace-intro">
              <div>
                <div className="eyebrow">{t("intro.eyebrow")}</div>
                <h1>
                  {t("intro.title")}
                  <span>.</span>
                </h1>
                <p>{t("intro.lead")}</p>
              </div>
              <dl className="workspace-stats" aria-label={t("stats.label")}>
                <div>
                  <dt>{t("stats.ideas")}</dt>
                  <dd>{board.stats?.total ?? "—"}</dd>
                </div>
                <div>
                  <dt>{t("stats.seeds")}</dt>
                  <dd>{board.stats?.seeds ?? "—"}</dd>
                </div>
                <div>
                  <dt>{t("stats.depth")}</dt>
                  <dd>{board.stats?.max_depth ?? "—"}</dd>
                </div>
                <div>
                  <dt>{t("stats.water")}</dt>
                  <dd>{board.stats?.water ?? "—"}</dd>
                </div>
              </dl>
            </section>
            {!onboarded && (
              <section className="onboarding" aria-label={t("onboarding.label")}>
                <span className="onboarding-icon">
                  <Icon name="spark" size={18} />
                </span>
                <p>{t("onboarding.text")}</p>
                <button
                  className="button subtle"
                  onClick={() => setOnboarded(true)}
                >
                  {t("onboarding.dismiss")}
                </button>
              </section>
            )}
            <div className="workspace-toolbar">
              <div className="search-box">
                <Icon name="search" size={17} />
                <input
                  ref={searchInput}
                  value={search}
                  maxLength={200}
                  inputMode="search"
                  enterKeyHint="search"
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setDiscovering(false);
                  }}
                  placeholder={t("search.placeholder")}
                  aria-label={t("search.label")}
                />
                {search ? (
                  <button
                    className="icon-button tiny"
                    onClick={() => setSearch("")}
                    aria-label={t("search.clear")}
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
                aria-label={t("view.label")}
              >
                {(["graph", "list"] as const).map((item) => (
                  <button
                    key={item}
                    aria-pressed={view === item}
                    onClick={() => {
                      setBoardView(item);
                      setDiscovering(false);
                    }}
                  >
                    <Icon name={item} size={16} />
                    <span>{t(`view.${item}`)}</span>
                  </button>
                ))}
                <button
                  aria-pressed={view === "discover"}
                  onClick={() => setDiscovering(true)}
                >
                  <Icon name="compass" size={16} />
                  <span>{t("view.discover")}</span>
                </button>
              </div>
              <details className="export-menu">
                <summary className="icon-button" aria-label={t("export.label")}>
                  <Icon name="download" />
                </summary>
                <div>
                  <span>{t("export.heading")}</span>
                  <button
                    disabled={!board.ideas.length}
                    onClick={() => exportIdeas("json")}
                  >
                    {t("export.json")}
                  </button>
                  <button
                    disabled={!board.ideas.length}
                    onClick={() => exportIdeas("md")}
                  >
                    {t("export.md")}
                  </button>
                </div>
              </details>
            </div>
            <div className="filterbar">
              <button
                className="mobile-library-toggle button subtle"
                aria-expanded={libraryOpen}
                onClick={() => setLibraryOpen(!libraryOpen)}
              >
                <Icon name="plus" size={15} /> {t("filter.toggle")}
              </button>
              <label>
                <span className="sr-only">{t("filter.label")}</span>
                <select
                  value={mutation}
                  onChange={(event) => {
                    setMutation(event.target.value);
                    setDiscovering(false);
                  }}
                >
                  <option value="">{t("filter.all")}</option>
                  <option value="base">{t("filter.base")}</option>
                  {mutations.map((m) => (
                    <option key={m.id} value={m.id}>
                      {ruleName(t, m.id)}
                    </option>
                  ))}
                </select>
              </label>
              {activeFilters && (
                <button className="text-button" onClick={resetFilters}>
                  {t("filter.clear")}
                </button>
              )}
              <span className="filter-count">
                {board.loading
                  ? t("status.finding")
                  : t("status.loaded", {
                      n: `${board.ideas.length}${board.hasMore ? "+" : ""}`,
                    })}
              </span>
              <span className={`connection ${board.connection}`} role="status">
                <span />
                {board.connection === "live"
                  ? t("status.live")
                  : board.connection === "offline"
                    ? t("status.offline")
                    : t("status.reconnecting")}
              </span>
            </div>
            {shownError && (
              <div className="error-banner" role="alert">
                <span>{localizeError(lang, shownError)}</span>
                <button
                  className="text-button"
                  onClick={() => {
                    setError("");
                    board.refresh();
                  }}
                >
                  {t("error.refresh")}
                </button>
                <button
                  className="icon-button tiny"
                  aria-label={t("error.dismiss")}
                  onClick={() => setError("")}
                >
                  <Icon name="close" size={15} />
                </button>
              </div>
            )}
            {board.connection === "offline" && (
              <div className="offline-banner">{t("error.offline")}</div>
            )}
            <div
              className={`canvas ${view === "graph" ? "" : "list-canvas"}`}
              aria-busy={view !== "discover" && board.loading}
            >
              {view === "discover" ? (
                <Discover
                  version={discoverVersion}
                  stats={board.stats}
                  water={board.water}
                  surprising={surprising}
                  onSelect={selectIdea}
                  onPlant={plantText}
                  onSurprise={() => void surprise()}
                />
              ) : board.loading ? (
                <div className="empty-state">
                  <span className="spinner" />
                  <p>{t("loading.garden")}</p>
                </div>
              ) : board.ideas.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon">
                    <Icon
                      name={
                        scope === "saved"
                          ? "star"
                          : scope === "mine"
                            ? "user"
                            : search
                              ? "search"
                              : "spark"
                      }
                      size={32}
                    />
                  </span>
                  <h2>
                    {scope === "saved"
                      ? t("empty.savedTitle")
                      : scope === "mine"
                        ? t("empty.mineTitle")
                        : activeFilters
                          ? t("empty.filterTitle")
                          : t("empty.title")}
                  </h2>
                  <p>
                    {scope === "saved"
                      ? t("empty.savedText")
                      : scope === "mine"
                        ? t("empty.mineText")
                        : activeFilters
                          ? t("empty.filterText")
                          : t("empty.text")}
                  </p>
                  <button
                    className="button primary"
                    onClick={activeFilters ? resetFilters : startSeed}
                  >
                    {activeFilters ? t("empty.showAll") : t("empty.plantFirst")}
                    <Icon name="arrow" size={16} />
                  </button>
                </div>
              ) : view === "graph" ? (
                <GraphView
                  ideas={graphIdeas}
                  selectedId={selectedId}
                  bookmarks={bookmarks}
                  water={board.water}
                  branches={branches}
                  fresh={fresh}
                  theme={theme}
                  canFocus={!!selected}
                  focusPath={focusPath}
                  onFocusPath={() => setFocusPath((f) => !f)}
                  onSelect={selectIdea}
                  onBookmark={toggleBookmark}
                />
              ) : (
                <IdeaList
                  ideas={board.ideas}
                  selectedId={selectedId}
                  bookmarks={bookmarks}
                  water={board.water}
                  branches={branches}
                  query={debouncedSearch}
                  fresh={fresh}
                  hasMore={board.hasMore}
                  moreBusy={board.moreBusy}
                  onLoadMore={() => void board.loadMore()}
                  onSelect={selectIdea}
                  onBookmark={toggleBookmark}
                />
              )}
            </div>
            <footer className="canvas-footer">
              <span>
                {view === "graph"
                  ? t("graph.hintGraph")
                  : t("graph.hintList")}
                {view === "graph" && board.ideas.length > 160
                  ? t("graph.limit")
                  : ""}
              </span>
              {board.hasMore && view !== "discover" && (
                <button
                  className="text-button"
                  disabled={board.moreBusy}
                  onClick={() => void board.loadMore()}
                >
                  {board.moreBusy ? t("graph.loading") : t("graph.more")}{" "}
                  <Icon name="chevron" size={13} />
                </button>
              )}
              <span className="engine-label">
                <span /> {t("graph.engine")}
              </span>
            </footer>
          </main>
          <Inspector
            selectedId={selectedId}
            selected={selected}
            parent={parent}
            lineage={lineage}
            loadedChildren={children}
            branchCount={selected ? branches(selected) : 0}
            lineageError={lineageError ? localizeError(lang, lineageError) : ""}
            saved={!!selected && bookmarks.includes(selected.id)}
            watered={!!selected && wateredToday.includes(selected.id)}
            waterTotal={selected ? waterTotal(selected) : 0}
            watering={watering !== null}
            submitting={submitting}
            tab={inspectorTab}
            epoch={board.contentEpoch}
            onTab={setInspectorTab}
            onTransform={(rule) => void submit(rule)}
            onOpen={selectIdea}
            onOpenId={openId}
            onClose={clearSelection}
            onBookmark={toggleBookmark}
            onWater={(idea) => void water(idea)}
            onCopy={(idea) => void copyText(idea.content, t("notice.copied"))}
            onShare={(idea) => void share(idea)}
            onCard={(idea) => void card(idea)}
            onReport={setReportTarget}
            onCustomBranch={() => {
              setBranchDraft(true);
              setLibraryOpen(true);
              focusComposer();
            }}
            onExportLineage={() => exportIdeas("md", lineage)}
            onStarter={plantText}
          />
        </div>
        {libraryOpen && (
          <div
            className="sheet-backdrop library-backdrop"
            aria-hidden="true"
            onClick={() => setLibraryOpen(false)}
          />
        )}
        {selectedId !== null && (
          <div
            className="sheet-backdrop inspector-backdrop"
            aria-hidden="true"
            onClick={clearSelection}
          />
        )}
        <BottomNav
          active={
            libraryOpen
              ? "plant"
              : discovering
                ? "discover"
                : scope === "saved"
                  ? "saved"
                  : "garden"
          }
          savedCount={bookmarks.length}
          onNavigate={navigate}
        />
        <div className="toast-container" role="status" aria-live="polite">
          {notice && (
            <div className="toast">
              <Icon name="check" size={17} />
              {notice}
            </div>
          )}
        </div>
        {reportTarget !== null && (
          <ReportDialog
            ideaId={reportTarget}
            onClose={() => setReportTarget(null)}
          />
        )}
        <HelpDialog ref={help} />
      </div>
    </I18nContext.Provider>
  );
}
