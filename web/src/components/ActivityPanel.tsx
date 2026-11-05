import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  ArrowDown,
  Briefcase,
  ChevronDown,
  ChevronRight,
  Code2,
  Flag,
  Globe,
  Inbox,
  MessageSquare,
  Network,
  Sparkles,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ObsEvent, Session } from "../lib/types";
import { isRenderable, kindColor, matchesNode, type NodeId } from "../lib/events";
import { formatTime, fullTimestamp } from "../lib/format";
import { describeResult, describeTool, parseJson, toolText } from "../lib/describe";

interface Props {
  session: Session | null;
  events: ObsEvent[];
  cursor: number;
  step: NodeId;
  pinned: boolean;
  loading?: boolean;
  onFollow: () => void;
  onSeek: (index: number) => void;
}

const STEPS: Record<NodeId, { label: string; color: string; icon: LucideIcon }> = {
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
  return <div className="text-[10px] text-slate-500">{children}</div>;
}

function JsonValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) {
    return <span className="text-slate-500">—</span>;
  }
  if (typeof value === "string") {
    if (value.includes("\n") || value.length > 90) {
      return (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-ink-900/80 p-1.5 font-mono text-[10.5px] leading-relaxed text-slate-200">
          {value}
        </pre>
      );
    }
    return <span className="text-slate-200">{value}</span>;
  }
  if (typeof value === "number") {
    return <span className="font-mono text-amber-200">{value}</span>;
  }
  if (typeof value === "boolean") {
    return <span className="font-mono text-sky-200">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    return (
      <ul className="ml-3 list-disc space-y-0.5">
        {value.map((item, index) => (
          <li key={index}>
            <JsonValue value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    return (
      <div className={depth ? "ml-2 space-y-1 border-l border-ink-600 pl-2" : "space-y-1"}>
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <div key={key}>
            <div className="text-[9px] uppercase tracking-wider text-slate-500">
              {key}
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
            className="flex gap-1.5 text-[11.5px] leading-snug text-slate-200"
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
            className="flex items-center gap-1 text-[10px] text-slate-500 transition hover:text-slate-300"
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
  const parsed = parseJson(text);
  if (parsed !== undefined && parsed !== null && typeof parsed === "object") {
    return (
      <div className="rounded-md bg-ink-900/70 p-2">
        <JsonValue value={parsed} />
      </div>
    );
  }
  const jsonLike = /^[[{]/.test(text.trim());
  if (jsonLike) {
    return (
      <div className="rounded-md bg-ink-900/70 p-2">
        <button
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-center gap-1 text-left text-[10.5px] text-slate-400 transition hover:text-slate-200"
        >
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          <span className="font-mono uppercase tracking-wider">résultat JSON</span>
          <span className="ml-auto text-slate-500">{text.length} car.</span>
        </button>
        {open ? (
          <pre className="mt-1 max-h-52 overflow-auto whitespace-pre-wrap break-words font-mono text-[10.5px] leading-relaxed text-slate-300">
            {text}
          </pre>
        ) : (
          <div className="mt-1 truncate font-mono text-[10px] text-slate-500">
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
      className={`relative block w-full cursor-pointer overflow-hidden rounded-lg border px-2.5 py-2 text-left transition ${
        current
          ? "obs-live border-sky-500/50 bg-sky-500/[0.07]"
          : "border-transparent hover:border-ink-600 hover:bg-ink-800"
      }`}
      style={
        current
          ? ({ "--obs-color": color, "--obs-inset": "0px" } as CSSProperties)
          : undefined
      }
    >
      <span
        className="absolute left-0 top-0 h-full w-[2px]"
        style={{ background: color }}
      />
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[9.5px] text-slate-500">
          {formatTime(event.ts)}
        </span>
        <Icon size={11} style={{ color }} />
        <span
          className="truncate text-[9.5px] font-semibold uppercase tracking-wider"
          style={{ color }}
        >
          {label}
        </span>
        <button
          onClick={(clickEvent) => {
            clickEvent.stopPropagation();
            onToggle();
          }}
          className="ml-auto rounded p-0.5 text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
          title={open ? "Masquer les détails" : "Détails complets (JSON, horodatage)"}
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
      </div>

      <div className="mt-1 space-y-1">{children}</div>

      {open && (
        <div className="mt-1.5 rounded-md border border-ink-600 bg-ink-900/80 p-2">
          <div className="mb-1 font-mono text-[9.5px] text-slate-500">
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
    <aside className="absolute bottom-4 right-4 top-4 z-20 flex w-[420px] flex-col overflow-hidden rounded-xl border border-ink-600 bg-ink-850/95 shadow-2xl backdrop-blur">
      <div className="border-b border-ink-700 p-3">
        <div className="flex items-center gap-2">
          <span
            className="grid h-6 w-6 place-items-center rounded-md"
            style={{ background: `${meta.color}1f`, color: meta.color }}
          >
            <Icon size={13} />
          </span>
          <div className="min-w-0">
            <div className="text-[9px] uppercase tracking-[0.20em] text-slate-500">
              étape en cours
            </div>
            <div className="text-[12.5px] font-semibold text-slate-100">
              {stepLabel}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-[10px] text-slate-500">
              {loading
                ? "chargement…"
                : session
                  ? `${filtered.length} événement${filtered.length > 1 ? "s" : ""}`
                  : "—"}
            </span>
            {pinned ? (
              <button
                onClick={onFollow}
                className="rounded-md bg-sky-500/15 px-2 py-1 text-[10px] font-medium text-sky-300 ring-1 ring-sky-500/40 transition hover:bg-sky-500/25"
                title="Revenir au suivi automatique de la timeline"
              >
                suivre
              </button>
            ) : (
              <span
                className="rounded-md bg-ink-700 px-2 py-1 text-[10px] text-slate-400"
                title="Le panneau suit automatiquement l'étape en cours. Cliquez un nœud du canvas pour épingler une étape."
              >
                suivi auto
              </span>
            )}
          </div>
        </div>
        {session && (
          <div className="mt-2 truncate font-mono text-[9.5px] text-slate-500">
            {session.id} · {session.title}
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2.5">
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
                    <p className="whitespace-pre-wrap break-words text-[12px] leading-relaxed text-slate-200">
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
                    label={event.actor === "coder" ? "Codeur" : "Navigateur"}
                    icon={Sparkles}
                    color={event.actor === "coder" ? "#818cf8" : "#38bdf8"}
                  >
                    {payload.text ? (
                      <Markdown text={String(payload.text)} />
                    ) : (
                      <p className="text-[11.5px] italic text-slate-500">
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
                    {described.kind === "page" && (
                      <div className="rounded-md bg-ink-900/70 p-2 text-[11.5px] leading-snug text-slate-200">
                        <span className="text-slate-500">Page</span> «{" "}
                        {described.page?.title || "sans titre"} »
                        {described.page?.url && (
                          <>
                            <span className="mx-1 text-slate-600">·</span>
                            <a
                              href={described.page.url}
                              target="_blank"
                              rel="noreferrer"
                              className="break-all text-sky-300 underline"
                            >
                              {described.page.url.replace(/^https?:\/\//, "")}
                            </a>
                          </>
                        )}
                      </div>
                    )}
                    {described.kind === "error" && (
                      <div className="rounded-md bg-rose-500/10 p-2 text-[11px] text-rose-300">
                        {described.error}
                      </div>
                    )}
                    {described.kind === "empty" && !artifacts.length && (
                      <div className="text-[11px] italic text-slate-500">
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
                    <p className="whitespace-pre-wrap break-words text-[12px] leading-relaxed text-slate-200">
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
                      <p className="whitespace-pre-wrap break-words text-[11.5px] leading-relaxed text-slate-300">
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
                  <Block {...common} label="Session ouverte" icon={Network} color="#94a3b8">
                    <Meta>
                      {payload.type ?? "—"} · départ {payload.agent ?? "—"}
                    </Meta>
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
                      <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-md bg-ink-900/70 p-2 font-mono text-[10px] text-slate-400">
                        {pretty(payload.payload)}
                      </pre>
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
        {!filtered.length && (
          <div className="p-3 text-[12px] text-slate-500">
            {loading
              ? "chargement de la session…"
              : session
                ? "Aucun événement pour cette étape."
                : "Aucune session sélectionnée."}
          </div>
        )}
      </div>
    </aside>
  );
}
