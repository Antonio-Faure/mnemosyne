/** Human-readable interpretation of tool calls and their results. */

export function parseJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const text = value.trim();
  if (!text.startsWith("{") && !text.startsWith("[")) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

/** Tool outputs are often `[{"type":"text","text":"…"}]`: show the text only. */
export function toolText(value: unknown): string {
  const raw = String(value ?? "");
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      const texts = parsed
        .map((part) =>
          part && typeof part === "object" && "text" in part
            ? String((part as { text: unknown }).text)
            : null,
        )
        .filter((text): text is string => Boolean(text));
      if (texts.length) return texts.join("\n");
    }
  } catch {
    // plain text: keep it as-is
  }
  return raw;
}

function truncate(text: string, limit = 120): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > limit ? `${oneLine.slice(0, limit)}…` : oneLine;
}

function compactUrl(url: string): string {
  return url.replace(/^https?:\/\//, "");
}

/** One line of browser-harness Python, translated into an action. */
function describeBrowserExpression(expression: string): string | null {
  const expr = expression.trim();

  let match = expr.match(/^goto_url\(\s*["']([^"']+)["']/);
  if (match) return `Aller à l'URL : ${compactUrl(match[1])}`;

  match = expr.match(/^wait\(\s*([\d.]+)\s*\)/);
  if (match) {
    const seconds = Number(match[1]);
    return `Attendre ${match[1]} seconde${seconds > 1 ? "s" : ""}`;
  }

  match = expr.match(/^capture_screenshot\(\s*["']([^"']+)["']/);
  if (match) return "Prendre une capture d'écran";

  match = expr.match(/^fill_input\(\s*["']([^"']+)["']\s*,\s*["']([^"']*)["']/);
  if (match) {
    return `Remplir le champ « ${match[1]} » avec « ${truncate(match[2], 80)} »`;
  }

  match = expr.match(/^scroll\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/);
  if (match) {
    return `Faire défiler à (${match[1]}, ${match[2]}) de ${match[3]} px`;
  }

  match = expr.match(/^for\s+\w+\s+in\s+range\((\d+)\)\s*:/);
  if (match) return `Répéter ${match[1]} fois :`;

  match = expr.match(/^press_key\(\s*["']([^"']+)["']/);
  if (match) return `Appuyer sur la touche ${match[1]}`;

  if (/^dispatch_key\(/.test(expr)) return "Envoyer une touche au navigateur";

  match = expr.match(/^click_at_xy\(\s*([\d.]+)\s*,\s*([\d.]+)/);
  if (match) return `Cliquer à la position (${match[1]}, ${match[2]})`;

  if (/^new_tab\(/.test(expr)) return "Ouvrir un nouvel onglet";
  if (/^close_tab\(/.test(expr)) return "Fermer l'onglet";
  if (/^activate_tab\(/.test(expr)) return "Activer un onglet";
  if (/^list_tabs\(/.test(expr)) return "Lister les onglets ouverts";
  if (/^page_title\(\)/.test(expr)) return "Lire le titre de la page";
  if (/^page_info\(\)/.test(expr)) return "Récupérer les informations de la page";

  const fromImport = expr.match(/^from\s+(\S+)\s+import\s+/);
  if (fromImport) return `Importer depuis ${fromImport[1]}`;
  const plainImport = expr.match(/^import\s+(\S+)/);
  if (plainImport) return `Importer ${plainImport[1]}`;

  if (/globals\(\)/.test(expr)) return "Lister les fonctions disponibles";

  match = expr.match(/^js\(\s*["']([\s\S]*)/);
  if (match) {
    const snippet = match[1].replace(/\\"/g, '"');
    return `Exécuter du JavaScript : ${truncate(snippet, 110)}`;
  }

  match = expr.match(/^http_get\(\s*["']([^"']+)/);
  if (match) return `Récupérer l'URL : ${compactUrl(match[1])}`;

  if (/^ensure_real_tab\(/.test(expr)) return "S'assurer qu'un onglet réel est actif";
  if (/^ensure_daemon\(/.test(expr)) return "Vérifier le démon du navigateur";
  if (/^drain_events\(/.test(expr)) return "Lire les événements du navigateur";
  if (/^cdp\(/.test(expr)) return "Envoyer une commande Chrome DevTools";
  if (/^remember\(/.test(expr)) return "Mémoriser une information";
  if (/^ask_operator\(/.test(expr)) return "Demander à l'opérateur";

  return null;
}

/** A browser-harness snippet, line by line. */
export function describeBrowserCode(code: string): string[] {
  const steps: string[] = [];
  for (const raw of code.split("\n")) {
    const indent = (raw.match(/^\s*/)?.[0] ?? "").length;
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;

    const printed = line.match(/^print\((.*)\)$/);
    const expression = printed ? printed[1].trim() : line;
    const described =
      describeBrowserExpression(expression) ??
      (printed ? `Afficher : ${truncate(expression, 100)}` : `Exécuter : ${truncate(line, 100)}`);
    if (described) steps.push(indent > 0 ? `↳ ${described}` : described);
  }
  return steps;
}

export interface ToolDescription {
  steps: string[];
  code: string | null;
}

/** Turn a tool call into readable actions (and keep the raw code aside). */
export function describeTool(name: string, args: unknown): ToolDescription {
  const parsed = parseJson(args);
  const object =
    parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;

  const code = object && typeof object.code === "string" ? object.code : null;
  if (code) {
    return { steps: describeBrowserCode(code), code };
  }

  // The event store clips long arguments: when the JSON is truncated, salvage
  // the "code" string so the browser steps are still translated.
  if (typeof args === "string") {
    const truncated = args.match(/"code"\s*:\s*"([\s\S]*)/);
    if (truncated) {
      const code = truncated[1]
        .replace(/"\s*}\s*$/, "")
        .replace(/\\n/g, "\n")
        .replace(/\\r/g, "")
        .replace(/\\t/g, "\t")
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, "\\");
      return { steps: describeBrowserCode(code), code };
    }
  }

  const steps: string[] = [];
  if (object) {
    const path = object.path ?? object.file ?? object.filename;
    const url = object.url;
    const command = object.command ?? object.cmd;
    const query = object.query ?? object.q ?? object.pattern;
    const tool = name.toLowerCase();

    if (typeof command === "string") {
      steps.push(`Exécuter la commande : ${truncate(command, 120)}`);
    }
    if (typeof path === "string") {
      if (tool.includes("write") || tool.includes("edit")) steps.push(`Écrire dans ${path}`);
      else if (tool.includes("list")) steps.push(`Lister ${path}`);
      else steps.push(`Lire ${path}`);
    }
    if (typeof url === "string") steps.push(`Récupérer l'URL : ${compactUrl(url)}`);
    if (typeof query === "string") steps.push(`Rechercher : « ${truncate(query, 80)} »`);
  }

  return { steps, code: null };
}

export interface ResultDescription {
  kind: "page" | "error" | "empty" | "json" | "text";
  page?: { title?: string; url?: string };
  error?: string;
}

/** Summarize a tool output: page metadata, execution error, empty, JSON, text. */
export function describeResult(preview: unknown): ResultDescription {
  const text = toolText(preview);
  const trimmed = text.trim();

  if (!trimmed || trimmed === "(no output)") return { kind: "empty" };

  if (/Traceback \(most recent call last\)|\[stderr\]/i.test(text)) {
    const match = text.match(/([A-Za-z_.]*(?:Error|Exception)):\s*(.*)$/m);
    return {
      kind: "error",
      error: match ? `${match[1]}: ${match[2]}` : "Erreur d'exécution",
    };
  }

  const url = text.match(/["']url["']\s*:\s*["']([^"']+)["']/i)?.[1];
  const title = text.match(/["']title["']\s*:\s*["']([^"']*)["']/i)?.[1];
  if ((url || title) && /^\{[\s\S]*\}$/.test(trimmed)) {
    return { kind: "page", page: { title, url } };
  }

  const parsed = parseJson(text);
  if (parsed !== undefined && parsed !== null && typeof parsed === "object") {
    return { kind: "json" };
  }

  return { kind: "text" };
}
