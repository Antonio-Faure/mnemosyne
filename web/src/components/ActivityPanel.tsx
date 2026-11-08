import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  ArrowDown,
  Briefcase,
  ChevronDown,
  ChevronRight,
  Code2,
  Cog,
  Flag,
  Globe,
  Inbox,
  MessageSquare,
  Network,
  ScanSearch,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ObsEvent, Session } from "../lib/types";
import { isRenderable, kindColor, matchesNode, type NodeId } from "../lib/events";
import { formatTime, fullTimestamp } from "../lib/format";
import {
  describeResult,
  describeTool,
  findValue,
  pageFrom,
  parseJson,
  salvageList,
  toolText,
  type PageInfo,
} from "../lib/describe";

interface Props {
  session: Session | null;
  events: ObsEvent[];
  cursor: number;
  step: NodeId;
  pinned: boolean;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  overlay?: boolean;
  onClose?: () => void;
  onFollow: () => void;
  onSeek: (index: number) => void;
}

const STEPS: Record<NodeId, { label: string; color: string; icon: LucideIcon }> = {
  agency: { label: "Agency · file", color: "#f59e0b", icon: Cog },
  resolver: { label: "Résolveur", color: "#f472b6", icon: ScanSearch },
  orchestrator: { label: "Orchestrateur", color: "#60a5fa", icon: Network },
  browser: { label: "Navigateur", color: "#38bdf8", icon: Globe },
  coder: { label: "Codeur", color: "#818cf8", icon: Code2 },
  mailbox: { label: "Mailbox", color: "#fbbf24", icon: Inbox },
  job: { label: "Système · job", color: "#34d399", icon: Briefcase },
};

/** Pretty-print a JSON string when possible (tool arguments). */
function pretty(value: unknown): string {
  if (typeof value !== "string") {
    try {
      return JSON.stringify(value, null, 2) ?? String(value);
    } catch {
      return String(value);
    }
  }
  const text = value.trim();
  if (!text || (!text.startsWith("{") && !text.startsWith("["))) return text;
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

function Meta({ children }: { children: ReactNode }) {
  return <div className="text-[10px] text-slate-400">{children}</div>;
}

const FIELD_LABELS: Record<string, string> = {
  url: "URL",
  title: "Titre",
  w: "Largeur",
  h: "Hauteur",
  sx: "Scroll X",
  sy: "Scroll Y",
  pw: "Largeur page",
  ph: "Hauteur page",
  text: "Texte",
  type: "Type",
  name: "Nom",
  path: "Chemin",
  selector: "Sélecteur",
  code: "Code",
  status: "Statut",
  message: "Message",
  query: "Recherche",
  command: "Commande",
  preview: "Aperçu",
  artifacts: "Captures",
  from: "De",
  to: "À",
  id: "Identifiant",
};

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key.replace(/_/g, " ");
}

const URL_RE = /^https?:\/\/\S+$/;

function isPrimitive(value: unknown): boolean {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
}

const LABEL_KEYS = ["t", "title", "name", "label", "text", "type"];

function inlineValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

/** One row of an array of objects: primary label + compact fields. */
function ObjectRow({ item }: { item: Record<string, unknown> }) {
  const labelKey = LABEL_KEYS.find((key) => {
    const value = item[key];
    return typeof value === "string" && value.trim() !== "";
  });
  const label = labelKey ? String(item[labelKey]) : null;
  const rest = Object.entries(item)
    .filter(([key, value]) => key !== labelKey && value !== null && value !== "")
    .slice(0, 6);
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded bg-ink-900/50 px-1.5 py-1">
      {label && (
        <span className="max-w-full truncate text-[11px] font-medium text-slate-200">
          {label}
        </span>
      )}
      {rest.map(([key, value]) => (
        <span
          key={key}
          title={inlineValue(value)}
          className="max-w-full truncate font-mono text-[10px] text-slate-400"
        >
          <span className="text-slate-400">{fieldLabel(key)}</span>{" "}
          {inlineValue(value)}
        </span>
      ))}
      {Object.keys(item).filter((key) => key !== labelKey).length > rest.length && (
        <span className="text-[9px] text-slate-400">
          +{Object.keys(item).filter((key) => key !== labelKey).length - rest.length}
        </span>
      )}
    </div>
  );
}

/** Structured value: labelled fields, link URLs, chips for simple lists. */
function JsonValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) {
    return <span className="text-slate-400">—</span>;
  }
  if (typeof value === "string") {
    if (URL_RE.test(value)) {
      return (
        <a
          href={value}
          target="_blank"
          rel="noreferrer"
          className="break-all text-sky-300 underline"
        >
          {value.replace(/^https?:\/\//, "")}
        </a>
      );
    }
    if (value.includes("\n") || value.length > 90) {
      return (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-ink-900/80 p-1.5 font-mono text-[10.5px] leading-relaxed text-slate-200">
          {value}
        </pre>
      );
    }
    return <span className="break-words text-slate-200">{value}</span>;
  }
  if (typeof value === "number") {
    return (
      <span className="font-mono text-amber-200">{value.toLocaleString("fr-FR")}</span>
    );
  }
  if (typeof value === "boolean") {
    return <span className="font-mono text-sky-200">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.every(isPrimitive)) {
      const shown = value.slice(0, 30);
      return (
        <div className="flex flex-wrap gap-1">
          {shown.map((item, index) => (
            <span
              key={index}
              title={String(item ?? "")}
              className="max-w-full truncate rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-200"
            >
              {String(item ?? "—")}
            </span>
          ))}
          {value.length > shown.length && (
            <span className="text-[10px] text-slate-400">
              +{value.length - shown.length} autres
            </span>
          )}
        </div>
      );
    }
    if (
      value.every(
        (item) =>
          item !== null && typeof item === "object" && !Array.isArray(item),
      )
    ) {
      const rows = value.slice(0, 30) as Record<string, unknown>[];
      return (
        <div className="space-y-1">
          {rows.map((item, index) => (
            <ObjectRow key={index} item={item} />
          ))}
          {value.length > rows.length && (
            <div className="text-[10px] text-slate-400">
              +{value.length - rows.length} autres
            </div>
          )}
        </div>
      );
    }
    const shown = value.slice(0, 40);
    return (
      <ul className="ml-3 list-disc space-y-1">
        {shown.map((item, index) => (
          <li key={index}>
            <JsonValue value={item} depth={depth + 1} />
          </li>
        ))}
        {value.length > shown.length && (
          <li className="text-[10px] text-slate-400">
            +{value.length - shown.length} autres
          </li>
        )}
      </ul>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return <span className="text-slate-400">(vide)</span>;
    return (
      <div className={depth ? "ml-2 space-y-1 border-l border-ink-600 pl-2" : "space-y-1"}>
        {entries.map(([key, item]) => (
          <div key={key}>
            <div className="text-[9px] uppercase tracking-wider text-slate-400">
              {fieldLabel(key)}
            </div>
            <div className="mt-0.5">
              <JsonValue value={item} depth={depth + 1} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  return <span className="text-slate-300">{String(value)}</span>;
}

/** A second value attached to a result (coordinates, URL, …). */
function ExtraValue({ text }: { text: string }) {
  const parsed = findValue(text);
  const structured =
    parsed && !parsed.prefix && !parsed.suffix ? parsed.value : null;
  return structured !== null ? (
    <JsonValue value={structured} />
  ) : (
    <pre className="whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-slate-400">
      {text}
    </pre>
  );
}

/** Browser page metadata, rendered as a readable card (no raw dict). */
function PageCard({ page }: { page: PageInfo }) {
  const metrics: string[] = [];
  if (page.width !== undefined && page.height !== undefined) {
    metrics.push(`fenêtre ${page.width}×${page.height}`);
  }
  if (page.scrollX !== undefined || page.scrollY !== undefined) {
    metrics.push(`scroll ${page.scrollX ?? 0}, ${page.scrollY ?? 0}`);
  }
  if (page.pageWidth !== undefined && page.pageHeight !== undefined) {
    metrics.push(`page ${page.pageWidth}×${page.pageHeight}`);
  }
  const extra = page.extra && page.extra !== page.url ? page.extra : null;
  return (
    <div className="rounded-md bg-ink-900/70 p-2 text-[11.5px] leading-snug text-slate-200">
      {page.prefix && (
        <div className="mb-1 whitespace-pre-wrap break-words text-[11px] text-slate-300">
          {page.prefix}
        </div>
      )}
      <div>
        <span className="text-slate-400">Page</span> « {page.title || "sans titre"} »
      </div>
      {page.url && (
        <a
          href={page.url}
          target="_blank"
          rel="noreferrer"
          className="mt-0.5 block break-all text-sky-300 underline"
        >
          {page.url.replace(/^https?:\/\//, "")}
        </a>
      )}
      {metrics.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {metrics.map((metric) => (
            <span
              key={metric}
              className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
            >
              {metric}
            </span>
          ))}
        </div>
      )}
      {extra && (
        <div className="mt-1 border-t border-ink-700 pt-1">
          <ExtraValue text={extra} />
        </div>
      )}
    </div>
  );
}

/** Tool arguments rendered from their JSON: fields, code blocks, lists. */
function ArgsView({ args }: { args: unknown }) {
  const parsed = parseJson(args);
  if (parsed === undefined) {
    return (
      <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-ink-900/70 p-2 font-mono text-[10.5px] leading-relaxed text-slate-300">
        {String(args ?? "")}
      </pre>
    );
  }
  return (
    <div className="rounded-md bg-ink-900/70 p-2">
      <JsonValue value={parsed} />
    </div>
  );
}

/** Tool call translated into human actions, with the raw code on demand. */
function ToolArgs({ name, args }: { name?: string; args: unknown }) {
  const described = useMemo(
    () => describeTool(String(name ?? ""), args),
    [name, args],
  );
  const [showCode, setShowCode] = useState(false);

  if (!described.steps.length) {
    return <ArgsView args={args} />;
  }

  return (
    <div className="rounded-md bg-ink-900/70 p-2">
      <ul className="space-y-1">
        {described.steps.map((step, index) => (
          <li
            key={index}
            className="flex gap-1.5 text-[12px] leading-snug text-slate-200"
          >
            <span className="mt-[5px] h-1 w-1 shrink-0 rounded-full bg-sky-400" />
            <span>{step}</span>
          </li>
        ))}
      </ul>
      {described.code && (
        <div className="mt-1.5">
          <button
            onClick={() => setShowCode((value) => !value)}
            className="flex items-center gap-1 text-[10px] text-slate-400 transition hover:text-slate-300"
          >
            {showCode ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            code source
          </button>
          {showCode && (
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-ink-950/70 p-2 font-mono text-[10.5px] leading-relaxed text-slate-400">
              {described.code}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/** Tool output: structured JSON when it parses, otherwise a readable block.
 * JSON-ish payloads (e.g. a Python dict repr) stay collapsed by default. */
function ResultView({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const found = findValue(text);
  if (found) {
    const page = pageFrom(found.value);
    if (page) {
      return (
        <PageCard
          page={{
            ...page,
            prefix: found.prefix || undefined,
            extra: found.suffix || undefined,
          }}
        />
      );
    }
    return (
      <div className="rounded-md bg-ink-900/70 p-2">
        {found.prefix && (
          <div className="mb-1 whitespace-pre-wrap break-words text-[11px] text-slate-300">
            {found.prefix}
          </div>
        )}
        <JsonValue value={found.value} />
        {found.suffix && (
          <div className="mt-1 border-t border-ink-700 pt-1">
            <ExtraValue text={found.suffix} />
          </div>
        )}
        <button
          onClick={() => setOpen((value) => !value)}
          className="mt-1.5 flex items-center gap-1 text-[10px] text-slate-400 transition hover:text-slate-300"
        >
          {open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          valeur brute
        </button>
        {open && (
          <pre className="mt-1 max-h-52 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-slate-400">
            {pretty(found.value)}
          </pre>
        )}
      </div>
    );
  }
  const jsonLike = /^[[{]/.test(text.trim());
  const salvaged = salvageList(text);
  if (salvaged) {
    return (
      <div className="rounded-md bg-ink-900/70 p-2">
        <JsonValue value={salvaged.items} />
        {salvaged.truncated && (
          <div className="mt-1 text-[10px] italic text-slate-400">
            liste tronquée par l'aperçu
          </div>
        )}
      </div>
    );
  }
  if (jsonLike) {
    return (
      <div className="rounded-md bg-ink-900/70 p-2">
        <button
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-center gap-1 text-left text-[10.5px] text-slate-400 transition hover:text-slate-200"
        >
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          <span className="font-mono uppercase tracking-wider">sortie structurée</span>
          <span className="ml-auto text-slate-400">{text.length} car.</span>
        </button>
        {open ? (
          <pre className="mt-1 max-h-52 overflow-auto whitespace-pre-wrap break-words font-mono text-[10.5px] leading-relaxed text-slate-300">
            {text}
          </pre>
        ) : (
          <div className="mt-1 truncate font-mono text-[10px] text-slate-400">
            {text.slice(0, 140)}
          </div>
        )}
      </div>
    );
  }
  return (
    <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-words rounded-md bg-ink-900/70 p-2 font-mono text-[10.5px] leading-relaxed text-slate-300">
      {text || "(sortie vide)"}
    </pre>
  );
}

function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

interface BlockProps {
  event: ObsEvent;
  label: string;
  color: string;
  icon: LucideIcon;
  current: boolean;
  open: boolean;
  onToggle: () => void;
  onSeek: () => void;
  children: ReactNode;
}

function Block({
  event,
  label,
  color,
  icon: Icon,
  current,
  open,
  onToggle,
  onSeek,
  children,
}: BlockProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSeek}
      onKeyDown={(keyEvent) => {
        if (keyEvent.key === "Enter" || keyEvent.key === " ") {
          keyEvent.preventDefault();
          onSeek();
        }
      }}
      className={`relative block w-full cursor-pointer rounded-lg px-3 py-2.5 text-left transition ${
        current
          ? "obs-live border border-sky-500/30 bg-sky-500/[0.06]"
          : "border border-transparent hover:bg-ink-800/60"
      }`}
      style={
        current
          ? ({ "--obs-color": color, "--obs-inset": "0px" } as CSSProperties)
          : undefined
      }
      aria-current={current ? "step" : undefined}
    >
      <span
        className="absolute -left-[20px] top-[13px] h-2 w-2 rounded-full ring-2 ring-ink-850"
        style={{ background: color }}
      />
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[10px] tabular-nums text-slate-400">
          {formatTime(event.ts)}
        </span>
        <Icon size={11} style={{ color }} />
        <span
          className="truncate text-[10px] font-semibold uppercase tracking-[0.1em]"
          style={{ color }}
        >
          {label}
        </span>
        <button
          onClick={(clickEvent) => {
            clickEvent.stopPropagation();
            onToggle();
          }}
          className="ml-auto rounded p-0.5 text-slate-600 transition hover:bg-ink-700 hover:text-slate-200"
          title={open ? "Masquer les détails" : "Détails complets (JSON, horodatage)"}
          aria-label={open ? "Masquer les détails" : "Afficher les détails"}
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
      </div>

      <div className="mt-1.5 space-y-1">{children}</div>

      {open && (
        <div className="mt-1.5 rounded-md border border-ink-600 bg-ink-900/80 p-2">
          <div className="mb-1 font-mono text-[10px] text-slate-400">
            {fullTimestamp(event.ts)} · {event.kind} · #{event.id}
          </div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-slate-300">
            {JSON.stringify(
              {
                kind: event.kind,
                actor: event.actor,
                ts: event.ts,
                payload: event.payload,
              },
              null,
              2,
            )}
          </pre>
        </div>
      )}
    </div>
  );
}

export function ActivityPanel({
  session,
  events,
  cursor,
  step,
  pinned,
  loading = false,
  error = false,
  onRetry,
  overlay = false,
  onClose,
  onFollow,
  onSeek,
}: Props) {
  const meta = STEPS[step];
  const stepLabel =
    step === "job" && session?.type === "agency"
      ? "Agency · moteur de file"
      : meta.label;
  const Icon = meta.icon;

  const indices = useMemo(() => {
    const map = new Map<number, number>();
    events.forEach((event, index) => map.set(event.id, index));
    return map;
  }, [events]);

  const filtered = useMemo(
    () =>
      events.filter(
        (event) => matchesNode(event, step) && isRenderable(event),
      ),
    [events, step],
  );
  const currentId = useMemo(() => {
    for (let index = Math.min(cursor, events.length - 1); index >= 0; index -= 1) {
      if (isRenderable(events[index])) return events[index].id;
    }
    return null;
  }, [events, cursor]);
  const currentRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: "nearest" });
  }, [currentId, step]);

  const toggle = (id: number) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <aside
      className={`${
        overlay
          ? "fixed bottom-3 right-3 top-[68px] z-40 w-[min(500px,calc(100vw-24px))] rounded-xl shadow-2xl"
          : "absolute bottom-4 right-4 top-4 z-20 w-[440px]"
      } flex flex-col overflow-hidden border border-ink-600/90 bg-ink-850/95 backdrop-blur-md`}
      aria-label="Étape en cours"
    >
      <div className="shrink-0 border-b border-ink-700/80 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span
            className="grid h-7 w-7 shrink-0 place-items-center rounded-lg ring-1 ring-inset"
            style={{
              background: `${meta.color}14`,
              color: meta.color,
              boxShadow: `inset 0 0 0 1px ${meta.color}24`,
            }}
          >
            <Icon size={14} strokeWidth={1.9} />
          </span>
          <div className="min-w-0">
            <div className="text-[9px] font-medium uppercase tracking-[0.14em] text-slate-400">
              Étape en cours
            </div>
            <div className="mt-0.5 truncate text-[14px] font-semibold tracking-tight text-slate-100">
              {stepLabel}
            </div>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            <span className="font-mono text-[10px] tabular-nums text-slate-400">
              {loading
                ? "…"
                : session
                  ? `${filtered.length} év.`
                  : "—"}
            </span>
            {pinned ? (
              <button
                onClick={onFollow}
                className="rounded-md bg-sky-500/15 px-2 py-1 text-[10px] font-medium text-sky-300 ring-1 ring-inset ring-sky-500/30 transition hover:bg-sky-500/25"
                title="Revenir au suivi automatique de la timeline"
              >
                suivre
              </button>
            ) : (
              <span
                className="rounded-md bg-ink-700/70 px-2 py-1 text-[10px] text-slate-400"
                title="Le panneau suit automatiquement l'étape en cours. Cliquez un nœud du canvas pour épingler une étape."
              >
                suivi auto
              </span>
            )}
            {overlay && (
              <button
                onClick={onClose}
                className="grid h-7 w-7 place-items-center rounded-md text-slate-400 transition hover:bg-ink-800 hover:text-slate-200"
                title="Fermer l'étape"
                aria-label="Fermer l'étape en cours"
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>
        {session && (
          <div className="mt-2 truncate font-mono text-[10px] text-slate-400">
            {session.id}
            <span className="mx-1.5 text-slate-700">·</span>
            <span className="font-sans text-slate-400">{session.title}</span>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {filtered.length > 0 && (
          <div className="relative space-y-1 border-l border-ink-700/70 pl-4">
            {filtered.map((event) => {
          const index = indices.get(event.id) ?? 0;
          const payload = event.payload ?? {};
          const current = event.id === currentId;
          const open = expanded.has(event.id);
          const seek = () => onSeek(index);
          const common = {
            event,
            current,
            open,
            onToggle: () => toggle(event.id),
            onSeek: seek,
            color: kindColor(event.kind),
          };

          switch (event.kind) {
            case "activation.start":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block {...common} label="Mission" icon={Flag} color="#22d3ee">
                    <p className="whitespace-pre-wrap break-words text-[12.5px] leading-[1.65] text-slate-200/95">
                      {String(payload.objective ?? "—")}
                    </p>
                    <Meta>
                      agent {event.actor} · cap {payload.turn_cap ?? "—"} tours ·{" "}
                      {payload.messages ?? 0} message(s) injecté(s)
                    </Meta>
                  </Block>
                </div>
              );

            case "llm.call":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label={
                      event.actor === "coder"
                        ? "Codeur"
                        : event.actor === "resolver"
                          ? "Résolveur"
                          : "Navigateur"
                    }
                    icon={Sparkles}
                    color={
                      event.actor === "coder"
                        ? "#818cf8"
                        : event.actor === "resolver"
                          ? "#f472b6"
                          : "#38bdf8"
                    }
                  >
                    {payload.text ? (
                      <Markdown text={String(payload.text)} />
                    ) : (
                      <p className="text-[11.5px] italic text-slate-400">
                        (pas de texte — l'agent appelle un outil)
                      </p>
                    )}
                    <Meta>
                      {payload.model ?? "—"} ·{" "}
                      {Number(payload.prompt_tokens ?? 0).toLocaleString("fr-FR")} prompt
                      {" · "}
                      {Number(payload.completion_tokens ?? 0).toLocaleString("fr-FR")} sortie
                      {" · "}
                      {Number(payload.cached_tokens ?? 0).toLocaleString("fr-FR")} cache
                      {payload.messages_count ? ` · ${payload.messages_count} msg` : ""}
                    </Meta>
                  </Block>
                </div>
              );

            case "tool.call":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label={`Outil · ${payload.name ?? "?"}`}
                    icon={Wrench}
                    color="#c084fc"
                  >
                    <ToolArgs name={payload.name} args={payload.args} />
                  </Block>
                </div>
              );

            case "tool.result": {
              const artifacts = Array.isArray(payload.artifacts)
                ? (payload.artifacts as { name?: string; url: string }[])
                : [];
              const text = toolText(payload.preview);
              const described = describeResult(payload.preview);
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label={`Résultat · ${payload.name ?? "outil"}`}
                    icon={ArrowDown}
                    color="#f0abfc"
                  >
                    {artifacts.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {artifacts.map((artifact) => (
                          <a
                            key={artifact.url}
                            href={artifact.url}
                            target="_blank"
                            rel="noreferrer"
                            className="block overflow-hidden rounded-md border border-ink-600 transition hover:border-sky-500/60"
                            title={artifact.name ?? "capture"}
                          >
                            <img
                              src={artifact.url}
                              alt={artifact.name ?? "capture d'écran"}
                              loading="lazy"
                              className="max-h-52 w-auto"
                            />
                          </a>
                        ))}
                      </div>
                    )}
                    {described.kind === "page" && described.page && (
                      <PageCard page={described.page} />
                    )}
                    {described.kind === "error" && (
                      <div className="rounded-md bg-rose-500/10 p-2">
                        <div className="text-[11px] text-rose-300">
                          {described.error}
                        </div>
                        {described.traceback && (
                          <details className="mt-1">
                            <summary className="cursor-pointer text-[10px] text-rose-300/80">
                              trace complète
                            </summary>
                            <pre className="mt-1 max-h-52 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-rose-200/80">
                              {described.traceback}
                            </pre>
                          </details>
                        )}
                      </div>
                    )}
                    {described.kind === "empty" && !artifacts.length && (
                      <div className="text-[11px] italic text-slate-400">
                        Aucune sortie
                      </div>
                    )}
                    {(described.kind === "json" || described.kind === "text") && (
                      <ResultView text={text} />
                    )}
                  </Block>
                </div>
              );
            }

            case "mailbox.message":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label={`Message · ${payload.from ?? "?"} → ${payload.to ?? "?"}`}
                    icon={MessageSquare}
                    color="#fbbf24"
                  >
                    <p className="whitespace-pre-wrap break-words text-[12.5px] leading-[1.65] text-slate-200/95">
                      {String(payload.body || payload.preview || "—")}
                    </p>
                  </Block>
                </div>
              );

            case "activation.end":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block {...common} label="Fin d'activation" icon={Flag} color="#38bdf8">
                    <Meta>
                      {payload.turns ?? "?"} tour(s)
                      {payload.duration_s !== undefined ? ` · ${payload.duration_s}s` : ""}
                      {payload.branch ? ` · branche ${payload.branch}` : ""}
                    </Meta>
                    {payload.finish && <Markdown text={String(payload.finish)} />}
                    {payload.error && (
                      <p className="rounded-md bg-rose-500/10 p-2 text-[11px] text-rose-300">
                        {String(payload.error)}
                      </p>
                    )}
                  </Block>
                </div>
              );

            case "activation.returned":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label="Retour à l'orchestrateur"
                    icon={Network}
                    color="#60a5fa"
                  >
                    <Meta>
                      {String(payload.status ?? "?")} · retour{" "}
                      {String(payload.agent ?? "?")}
                    </Meta>
                  </Block>
                </div>
              );

            case "task.status":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label={`Statut · ${payload.from ?? "?"} → ${payload.to ?? "?"}`}
                    icon={Network}
                    color="#60a5fa"
                  >
                    {payload.note && (
                      <p className="whitespace-pre-wrap break-words text-[12px] leading-relaxed text-slate-300">
                        {String(payload.note)}
                      </p>
                    )}
                  </Block>
                </div>
              );

            case "session.created":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block {...common} label="Session ouverte" icon={Cog} color="#f59e0b">
                    <Meta>
                      {payload.type ?? "—"} · départ {payload.agent ?? "—"}
                    </Meta>
                    {payload.title && (
                      <p className="whitespace-pre-wrap break-words text-[11.5px] leading-relaxed text-slate-200">
                        {String(payload.title)}
                      </p>
                    )}
                  </Block>
                </div>
              );

            case "job.start":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label={`Job · ${payload.kind ?? "?"} démarré`}
                    icon={Briefcase}
                    color="#34d399"
                  >
                    {payload.payload && (
                      <div className="rounded-md bg-ink-900/70 p-2">
                        <JsonValue value={payload.payload} />
                      </div>
                    )}
                  </Block>
                </div>
              );

            case "job.end":
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label={`Job · ${payload.status ?? "terminé"}`}
                    icon={Briefcase}
                    color="#10b981"
                  >
                    <Meta>
                      {payload.duration_s !== undefined ? `${payload.duration_s}s` : "—"}
                      {payload.activity ? ` · ${payload.activity}` : ""}
                    </Meta>
                    {payload.error && (
                      <p className="rounded-md bg-rose-500/10 p-2 text-[11px] text-rose-300">
                        {String(payload.error)}
                      </p>
                    )}
                  </Block>
                </div>
              );

            default:
              return (
                <div
                  key={event.id}
                  ref={current ? currentRef : undefined}
                >
                  <Block
                    {...common}
                    label={event.kind}
                    icon={Network}
                    color="#94a3b8"
                  >
                    <Meta>{event.actor ?? "système"}</Meta>
                  </Block>
                </div>
              );
          }
        })}
          </div>
        )}
        {!filtered.length && (
          <div className="flex h-full min-h-[200px] flex-col items-center justify-center px-6 text-center">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-ink-800 text-slate-600 ring-1 ring-inset ring-ink-700">
              <Icon size={18} />
            </span>
            <p className="mt-3 text-[12px] font-medium text-slate-300">
              {loading
                ? "Chargement de la session…"
                : error
                  ? "Timeline indisponible"
                  : session
                    ? "Aucun événement pour cette étape"
                    : "Aucune session sélectionnée"}
            </p>
            <p className="mt-1 max-w-[28ch] text-[10.5px] leading-relaxed text-slate-400">
              {error
                ? "La lecture des événements a échoué."
                : session
                  ? "La timeline de cette étape est vide pour l'instant."
                  : "Choisissez une session dans la liste pour dérouler son replay."}
            </p>
            {error && onRetry && (
              <button
                onClick={onRetry}
                className="mt-3 rounded-md border border-ink-600 bg-ink-800 px-2.5 py-1 text-[10.5px] text-slate-300 transition hover:border-sky-500/40 hover:text-sky-200"
              >
                Réessayer
              </button>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
