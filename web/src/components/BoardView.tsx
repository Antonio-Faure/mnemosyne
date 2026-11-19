import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  RefreshCw,
  SearchX,
  Waypoints,
  X,
} from "lucide-react";

import { BoardCard } from "./BoardCard";
const SessionDrawer = lazy(() =>
  import("./SessionDrawer").then((module) => ({ default: module.SessionDrawer })),
);
import {
  BOARD_LABELS,
  COLUMN_HINTS,
  fetchBoard,
  outcomeClass,
  waitingClass,
  type BoardCard as BoardCardModel,
  type BoardColumn,
  type BoardId,
  type ColumnId,
} from "../lib/board";

const BOARDS: BoardId[] = ["resolver", "atelier"];
const COLUMN_ACCENT: Record<ColumnId, string> = {
  queued: "border-t-slate-500/60",
  running: "border-t-sky-500/60",
  waiting: "border-t-amber-500/60",
  done: "border-t-emerald-500/60",
  failed: "border-t-rose-500/60",
};

function storedBoard(): BoardId {
  const fromUrl = new URLSearchParams(window.location.search).get("board");
  if (fromUrl === "atelier" || fromUrl === "resolver") return fromUrl;
  const value = localStorage.getItem("obs.board");
  return value === "atelier" ? "atelier" : "resolver";
}

function filterKey(kind: "outcome" | "waiting", key: string): string {
  return `${kind}:${key}`;
}

function matchesFilter(card: BoardCardModel, filter: string | null): boolean {
  if (!filter) return true;
  const [kind, key] = filter.split(":", 2);
  if (kind === "outcome") return card.outcome === key;
  if (kind === "waiting") return card.waiting.some((item) => item.type === key);
  return true;
}

function summaryTone(column: ColumnId, key: string): string {
  if (column === "waiting") return waitingClass(key as never);
  return outcomeClass(key);
}

function Column({
  column,
  board,
  activeFilter,
  onFilter,
  onOpen,
}: {
  column: BoardColumn;
  board: BoardId;
  activeFilter: string | null;
  onFilter: (filter: string | null) => void;
  onOpen: (card: BoardCardModel) => void;
}) {
  const cards = column.cards.filter((card) => matchesFilter(card, activeFilter));
  const hint = COLUMN_HINTS[board][column.id];

  return (
    <section
      className={`flex min-h-0 min-w-[245px] flex-1 flex-col rounded-xl border border-t-2 border-ink-700/80 bg-ink-900/70 ${COLUMN_ACCENT[column.id]}`}
    >
      <header className="shrink-0 border-b border-ink-700/70 px-3 pb-2.5 pt-3">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-[11.5px] font-semibold uppercase tracking-[0.16em] text-slate-300">
            {column.label}
          </h2>
          <span className="rounded-full bg-ink-800 px-1.5 py-0.5 text-[10.5px] font-medium text-slate-400">
            {activeFilter ? `${cards.length}/${column.count}` : column.count}
          </span>
        </div>
        <p className="mt-0.5 text-[10.5px] text-slate-500">{hint}</p>
        {column.summary.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1">
            {column.summary.map((item) => {
              const key = filterKey(
                column.id === "waiting" ? "waiting" : "outcome",
                item.key,
              );
              const active = activeFilter === key;
              return (
                <button
                  key={item.key}
                  onClick={() => onFilter(active ? null : key)}
                  className={`rounded-full border px-1.5 py-0.5 text-[9.5px] font-medium transition ${summaryTone(
                    column.id,
                    item.key,
                  )} ${active ? "ring-1 ring-inset ring-white/40" : "opacity-80 hover:opacity-100"}`}
                  title={`Filtrer : ${item.label}`}
                >
                  {item.label} {item.count}
                </button>
              );
            })}
          </div>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {cards.length > 0 ? (
          cards.map((card) => (
            <BoardCard key={card.id} card={card} onOpen={() => onOpen(card)} />
          ))
        ) : (
          <div className="rounded-lg border border-dashed border-ink-700/70 px-3 py-6 text-center text-[10.5px] text-slate-500">
            {activeFilter ? "Aucune carte pour ce filtre." : "Rien ici pour l’instant."}
          </div>
        )}
      </div>
    </section>
  );
}

export function BoardView() {
  const [board, setBoard] = useState<BoardId>(storedBoard);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [openCard, setOpenCard] = useState<BoardCardModel | null>(null);

  useEffect(() => {
    localStorage.setItem("obs.board", board);
    const url = new URL(window.location.href);
    url.searchParams.set("board", board);
    window.history.replaceState(null, "", url);
    setActiveFilter(null);
  }, [board]);

  const query = useQuery({
    queryKey: ["board", board],
    queryFn: () => fetchBoard(board),
    refetchInterval: 5000,
    staleTime: 2000,
  });

  const columns = query.data?.columns ?? [];
  const openedCard = useMemo(() => {
    if (!openCard) return null;
    for (const column of columns) {
      const found = column.cards.find((card) => card.id === openCard.id);
      if (found) return found;
    }
    return openCard;
  }, [columns, openCard]);
  const total = useMemo(
    () => columns.reduce((sum, column) => sum + column.count, 0),
    [columns],
  );
  const filterLabel = useMemo(() => {
    if (!activeFilter) return null;
    const [kind, key] = activeFilter.split(":", 2);
    for (const column of columns) {
      const found = column.summary.find((item) => item.key === key);
      if (found && (kind === "waiting" || column.id !== "waiting")) return found.label;
    }
    return key;
  }, [activeFilter, columns]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-ink-950 text-slate-200">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-ink-700/80 bg-ink-850 px-3 py-2.5 sm:px-4">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-sky-500/10 text-sky-400 ring-1 ring-inset ring-sky-500/20">
          <Waypoints size={16} strokeWidth={1.8} />
        </span>
        <div className="leading-tight">
          <div className="text-[13px] font-semibold tracking-tight text-slate-100">
            Mnemosyne
          </div>
          <div className="text-[9px] uppercase tracking-[0.18em] text-slate-400">
            Observatoire
          </div>
        </div>

        <span className="h-6 w-px bg-ink-700/80" />

        <nav className="flex items-center gap-1 rounded-lg border border-ink-700/80 bg-ink-900/70 p-0.5">
          {BOARDS.map((id) => (
            <button
              key={id}
              onClick={() => setBoard(id)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                board === id
                  ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-500/25"
                  : "text-slate-400 hover:bg-ink-800 hover:text-slate-200"
              }`}
              aria-pressed={board === id}
            >
              {BOARD_LABELS[id]}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2 text-[10.5px] text-slate-500">
          {activeFilter ? (
            <button
              onClick={() => setActiveFilter(null)}
              className="inline-flex items-center gap-1 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-1 text-sky-300 hover:bg-sky-500/15"
              title="Retirer le filtre"
            >
              <SearchX size={11} />
              {filterLabel}
              <X size={10} />
            </button>
          ) : null}
          <span className="hidden sm:inline">
            {total} carte{total === 1 ? "" : "s"}
          </span>
          <span className="hidden h-4 w-px bg-ink-700 sm:block" />
          <span className="inline-flex items-center gap-1.5">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                query.isError ? "bg-rose-400" : "bg-emerald-400"
              }`}
            />
            {query.isFetching ? "mise à jour…" : "direct"}
          </span>
          <button
            onClick={() => query.refetch()}
            className="grid h-7 w-7 place-items-center rounded-md border border-ink-700 text-slate-400 transition hover:border-sky-500/40 hover:text-sky-200"
            title="Rafraîchir"
          >
            <RefreshCw size={12} className={query.isFetching ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-x-auto p-2.5 sm:p-3">
        {query.isLoading ? (
          <div className="flex h-full items-center justify-center text-[11px] text-slate-500">
            Chargement des tableaux…
          </div>
        ) : query.isError ? (
          <div className="mx-auto mt-10 flex max-w-md items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-[11px] text-rose-200">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">Le tableau n’a pas pu être chargé.</p>
              <p className="mt-0.5 text-rose-200/70">
                Vérifie que l’API observatoire répond, puis rafraîchis.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex h-full min-w-[1265px] flex-col gap-2">
            {total === 0 ? (
              <div className="flex items-center gap-2 rounded-lg border border-dashed border-ink-700 bg-ink-900/60 px-3 py-2 text-[10.5px] text-slate-500">
                <SearchX size={13} className="shrink-0" />
                {board === "resolver"
                  ? "Aucune résolution pour l’instant — les nouvelles phrases importées apparaîtront ici."
                  : "Aucune mission de source pour l’instant — les demandes du Résolveur apparaîtront ici."}
              </div>
            ) : null}
            <div className="flex min-h-0 flex-1 gap-2">
              {columns.map((column) => (
                <Column
                  key={column.id}
                  column={column}
                  board={board}
                  activeFilter={activeFilter}
                  onFilter={setActiveFilter}
                  onOpen={setOpenCard}
                />
              ))}
            </div>
          </div>
        )}
      </main>
      {openedCard ? (
        <Suspense
          fallback={
            <div className="fixed inset-0 z-[60] grid place-items-center bg-ink-950/80 text-[11px] text-slate-400 backdrop-blur-sm">
              Chargement de la session…
            </div>
          }
        >
          <SessionDrawer card={openedCard} onClose={() => setOpenCard(null)} />
        </Suspense>
      ) : null}
    </div>
  );
}
