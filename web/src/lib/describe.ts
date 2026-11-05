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

/** Parse strict JSON, then Python literals (`{'url': …}`): browser-harness
 *  prints Python reprs, not JSON. */
export function parseLoose(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const text = value.trim();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    // fall through to the Python literal parser
  }
  if (!/^[\[{('"]/.test(text)) return undefined;
  try {
    return parsePythonLiteral(text);
  } catch {
    return undefined;
  }
}

/** Minimal recursive-descent parser for Python literals (dict/list/tuple,
 *  strings with escapes, numbers, True/False/None). Returns the position where
 *  the value ends so callers can read a prefix/suffix. */
interface ReadLiteral {
  value: unknown;
  end: number;
}

function readPythonLiteral(source: string): ReadLiteral {
  let pos = 0;
  const fail = (): never => {
    throw new SyntaxError("python literal");
  };
  const ws = () => {
    while (pos < source.length && /\s/.test(source[pos])) pos += 1;
  };
  const parseString = (): string => {
    const quote = source[pos];
    if (quote !== "'" && quote !== '"') fail();
    pos += 1;
    let out = "";
    while (pos < source.length) {
      const ch = source[pos];
      pos += 1;
      if (ch === quote) return out;
      if (ch !== "\\") {
        out += ch;
        continue;
      }
      const esc = source[pos];
      pos += 1;
      switch (esc) {
        case "n":
          out += "\n";
          break;
        case "r":
          out += "\r";
          break;
        case "t":
          out += "\t";
          break;
        case "b":
          out += "\b";
          break;
        case "f":
          out += "\f";
          break;
        case "v":
          out += "\v";
          break;
        case "0":
          out += "\0";
          break;
        case "\\":
          out += "\\";
          break;
        case "'":
          out += "'";
          break;
        case '"':
          out += '"';
          break;
        case "x": {
          const hex = source.slice(pos, pos + 2);
          if (!/^[0-9a-f]{2}$/i.test(hex)) fail();
          out += String.fromCharCode(parseInt(hex, 16));
          pos += 2;
          break;
        }
        case "u": {
          const hex = source.slice(pos, pos + 4);
          if (!/^[0-9a-f]{4}$/i.test(hex)) fail();
          out += String.fromCharCode(parseInt(hex, 16));
          pos += 4;
          break;
        }
        default:
          out += esc;
      }
    }
    return fail();
  };
  const parseBare = (): string => {
    const match = source.slice(pos).match(/^[A-Za-z_][\w-]*/);
    if (!match) return fail();
    pos += match[0].length;
    return match[0];
  };
  const parseValue = (): unknown => {
    ws();
    const ch = source[pos];
    if (ch === "{" || ch === "[" || ch === "(") {
      const close = ch === "{" ? "}" : ch === "[" ? "]" : ")";
      const isObject = ch === "{";
      pos += 1;
      const obj: Record<string, unknown> = {};
      const arr: unknown[] = [];
      ws();
      if (source[pos] === close) {
        pos += 1;
        return isObject ? obj : arr;
      }
      for (;;) {
        ws();
        if (isObject) {
          const key =
            source[pos] === "'" || source[pos] === '"' ? parseString() : parseBare();
          ws();
          if (source[pos] !== ":") fail();
          pos += 1;
          obj[key] = parseValue();
        } else {
          arr.push(parseValue());
        }
        ws();
        if (source[pos] === ",") {
          pos += 1;
          continue;
        }
        if (source[pos] === close) {
          pos += 1;
          return isObject ? obj : arr;
        }
        fail();
      }
    }
    if (ch === "'" || ch === '"') return parseString();
    if (
      /^[bBrRuU]$/.test(ch ?? "") &&
      (source[pos + 1] === "'" || source[pos + 1] === '"')
    ) {
      pos += 1;
      return parseString();
    }
    if (source.startsWith("True", pos)) {
      pos += 4;
      return true;
    }
    if (source.startsWith("False", pos)) {
      pos += 5;
      return false;
    }
    if (source.startsWith("None", pos)) {
      pos += 4;
      return null;
    }
    if (source.startsWith("true", pos)) {
      pos += 4;
      return true;
    }
    if (source.startsWith("false", pos)) {
      pos += 5;
      return false;
    }
    if (source.startsWith("null", pos)) {
      pos += 4;
      return null;
    }
    const number = source
      .slice(pos)
      .match(/^-?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][+-]?\d+)?/);
    if (number) {
      pos += number[0].length;
      return Number(number[0]);
    }
    return fail();
  };

  const value = parseValue();
  ws();
  return { value, end: pos };
}

/** Whole-string Python literal (throws on trailing characters). */
function parsePythonLiteral(source: string): unknown {
  const { value, end } = readPythonLiteral(source);
  let pos = end;
  while (pos < source.length && /\s/.test(source[pos])) pos += 1;
  if (pos !== source.length) throw new SyntaxError("trailing characters");
  return value;
}

/** Parse a value at the start of the text, even when other text follows. */
function readLoosePrefix(source: string): ReadLiteral | null {
  try {
    return { value: JSON.parse(source), end: source.length };
  } catch {
    // Python's repr / trailing content: use the tolerant parser
  }
  try {
    return readPythonLiteral(source);
  } catch {
    return null;
  }
}

export interface ParsedValue {
  prefix: string;
  value: unknown;
  suffix: string;
}

/** Find a structured value in a text: whole payload, or embedded after a
 *  title line (`🐴 Wikidata\n{'url': …}`), or followed by extra content. */
export function findValue(text: string): ParsedValue | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const whole = readLoosePrefix(trimmed);
  if (whole && trimmed.slice(whole.end).trim() === "") {
    return { prefix: "", value: whole.value, suffix: "" };
  }
  for (let index = 0; index < trimmed.length; index += 1) {
    const ch = trimmed[index];
    if (ch !== "{" && ch !== "[") continue;
    const prefix = trimmed.slice(0, index).trim();
    // Do not mistake an item of a clipped list/dict for the result itself.
    if (/[\[{,(:]$/.test(prefix)) continue;
    const parsed = readLoosePrefix(trimmed.slice(index));
    if (!parsed) continue;
    return {
      prefix,
      value: parsed.value,
      suffix: trimmed.slice(index + parsed.end).trim(),
    };
  }
  return null;
}

export interface PageInfo {
  title?: string;
  url?: string;
  prefix?: string;
  extra?: string;
  width?: number;
  height?: number;
  scrollX?: number;
  scrollY?: number;
  pageWidth?: number;
  pageHeight?: number;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** Browser `page_info()` dict → readable page metadata. */
export function pageFrom(value: unknown): PageInfo | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const obj = value as Record<string, unknown>;
  const url = typeof obj.url === "string" ? obj.url : undefined;
  const title = typeof obj.title === "string" ? obj.title : undefined;
  if (!url && !title) return null;
  if (!url && !("w" in obj || "h" in obj || "ph" in obj || "sx" in obj || "sy" in obj)) {
    return null;
  }
  return {
    url,
    title,
    width: asNumber(obj.w),
    height: asNumber(obj.h),
    scrollX: asNumber(obj.sx),
    scrollY: asNumber(obj.sy),
    pageWidth: asNumber(obj.pw),
    pageHeight: asNumber(obj.ph),
  };
}

function decodeEscapes(text: string): string {
  return text
    .replace(/\\u([0-9a-f]{4})/gi, (_, hex: string) =>
      String.fromCharCode(parseInt(hex, 16)),
    )
    .replace(/\\n/g, "\n")
    .replace(/\\r/g, "\r")
    .replace(/\\t/g, "\t")
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, "\\");
}

/** Clipped Python list (`['a', 'b', …`): parse every complete item. */
export function salvageList(
  text: string,
): { items: unknown[]; truncated: boolean } | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("[")) return null;
  const items: unknown[] = [];
  let index = 1;
  while (index < trimmed.length && items.length < 40) {
    while (index < trimmed.length && /[\s,]/.test(trimmed[index])) index += 1;
    if (index >= trimmed.length || trimmed[index] === "]") break;
    const parsed = readLoosePrefix(trimmed.slice(index));
    if (!parsed) break;
    items.push(parsed.value);
    index += parsed.end;
  }
  if (!items.length) return null;
  const closed = /\]\s*…?\s*$/.test(trimmed);
  return { items, truncated: !closed };
}

/** Tool outputs are often `[{"type":"text","text":"…"}]`: show the text only.
 *  The envelope may be clipped: salvage its `text` field in that case. */
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
    // clipped harness envelope: keep the (possibly truncated) text field
    const match = raw.match(/"text"\s*:\s*"([\s\S]*)/);
    if (match) {
      const text = decodeEscapes(match[1].replace(/"\s*\]\s*\}?\s*$/, ""));
      if (text.trim()) return text;
    }
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

function cleanJsSnippet(snippet: string): string {
  return snippet
    .replace(/\\n/g, " ")
    .replace(/\\r/g, " ")
    .replace(/\\t/g, " ")
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, "\\")
    .replace(/["']\s*\)\s*$/, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** A JavaScript snippet, summarized by intent when possible. */
function describeJs(raw: string): string {
  const snippet = cleanJsSnippet(raw);
  if (!snippet) return "Exécuter du JavaScript";
  if (/^(?:return\s+)?document\.title\b/.test(snippet)) {
    return "Lire le titre de la page";
  }
  if (/^(?:return\s+)?(?:location\.href|document\.URL|window\.location\.href)\b/.test(snippet)) {
    return "Lire l'URL de la page";
  }
  if (/^(?:return\s+)?document\.body\.(?:innerText|textContent)\b/.test(snippet)) {
    return "Lire le texte de la page";
  }
  const linkText = snippet.match(/textContent\.trim\(\)\s*===\s*['"]([^'"]+)['"]/);
  if (linkText) return `Trouver l'élément « ${truncate(linkText[1], 60)} »`;
  if (/document\.activeElement\.outerHTML/.test(snippet)) {
    return "Lire le HTML de l'élément actif";
  }
  if (/document\.activeElement/.test(snippet)) {
    return "Lire l'élément actif";
  }
  if (/getBoundingClientRect\(\)/.test(snippet)) {
    return "Mesurer la position d'un élément";
  }
  const byId = snippet.match(/getElementById\(\s*['"]([^'"]+)['"]/);
  if (byId) return `Localiser l'élément « ${byId[1]} »`;
  if (/querySelectorAll\(\s*['"]\[role=option\]/.test(snippet)) {
    return "Lister les options du menu";
  }
  if (/querySelectorAll\(\s*['"][^'"]*input/.test(snippet)) {
    return "Lister les champs de saisie";
  }
  if (/querySelectorAll\(\s*['"]a['"]/.test(snippet)) {
    return "Lister les liens de la page";
  }
  if (/querySelectorAll\(\s*['"]img['"]/.test(snippet)) {
    return "Lister les images de la page";
  }
  const all = snippet.match(/querySelectorAll\(\s*['"]([^'"]+)['"]/);
  if (all) return `Lister les éléments « ${truncate(all[1], 60)} »`;
  const element = snippet.match(
    /querySelector\(\s*['"]([^'"]+)['"]\s*\)(?:\.innerText|\.textContent)/,
  );
  if (element) return `Lire le texte de l'élément « ${element[1]} »`;
  const one = snippet.match(/querySelector\(\s*['"]([^'"]+)['"]/);
  if (one) return `Lire l'élément « ${truncate(one[1], 60)} »`;
  return `Exécuter du JavaScript : ${truncate(snippet, 120)}`;
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

  match = expr.match(/^wait_for_load\(/);
  if (match) return "Attendre la fin du chargement";
  match = expr.match(/^wait_for_element\(\s*["']([^"']+)["']/);
  if (match) return `Attendre l'élément « ${match[1]} »`;
  match = expr.match(/^wait_for_network_idle\(/);
  if (match) return "Attendre que le réseau soit au repos";

  match = expr.match(/^capture_screenshot\(([^)]*)\)/);
  if (match) {
    return /full\s*=\s*True/.test(match[1])
      ? "Prendre une capture d'écran pleine page"
      : "Prendre une capture d'écran";
  }

  match = expr.match(/^fill_input\(\s*["']([^"']+)["']\s*,\s*["']([^"']*)["']/);
  if (match) {
    return `Remplir « ${match[1]} » avec « ${truncate(match[2], 90)} »`;
  }

  match = expr.match(/^type_text\(\s*["']([^"']*)["']/);
  if (match) return `Taper : « ${truncate(match[1], 90)} »`;

  match = expr.match(
    /^scroll\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)(?:\s*,\s*(-?[\d.]+))?/,
  );
  if (match) {
    const vertical = Number(match[3]);
    const horizontal = match[4] ? Number(match[4]) : 0;
    const direction = vertical < 0 ? "vers le haut" : "vers le bas";
    return `Faire défiler ${direction} de ${Math.abs(vertical)} px à (${match[1]}, ${match[2]})${
      horizontal ? ` (horizontal ${horizontal} px)` : ""
    }`;
  }

  match = expr.match(/^for\s+\w+\s+in\s+range\((\d+)\)\s*:/);
  if (match) return `Répéter ${match[1]} fois :`;
  match = expr.match(/^for\s+(\w+)\s+in\s+([^:]+):/);
  if (match) return `Parcourir ${truncate(match[2], 60)} :`;
  match = expr.match(/^while\s+([^:]+):/);
  if (match) return `Tant que ${truncate(match[1], 60)} :`;
  match = expr.match(/^if\s+([^:]+):/);
  if (match) return `Si ${truncate(match[1], 60)} :`;
  match = expr.match(/^elif\s+([^:]+):/);
  if (match) return `Sinon si ${truncate(match[1], 60)} :`;
  if (/^else\s*:/.test(expr)) return "Sinon :";
  if (/^try\s*:/.test(expr)) return "Essayer :";
  if (/^except\b.*:/.test(expr)) return "En cas d'erreur :";
  if (/^finally\s*:/.test(expr)) return "Pour finir :";
  match = expr.match(/^with\s+([^:]+):/);
  if (match) return `Avec ${truncate(match[1], 60)} :`;
  match = expr.match(/^return\s+([\s\S]+)$/);
  if (match) return `Retourner : ${truncate(match[1], 80)}`;

  match = expr.match(/^press_key\(\s*["']([^"']+)["']/);
  if (match) return `Appuyer sur la touche ${match[1]}`;

  match = expr.match(/^dispatch_key\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']/);
  if (match) return `Envoyer la touche ${match[2]} à « ${match[1]} »`;
  if (/^dispatch_key\(/.test(expr)) return "Envoyer une touche au navigateur";

  match = expr.match(/^click_at_xy\(\s*([\d.]+)\s*,\s*([\d.]+)/);
  if (match) return `Cliquer à la position (${match[1]}, ${match[2]})`;

  match = expr.match(/^upload_file\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']/);
  if (match) return `Téléverser ${compactUrl(match[2])} dans « ${match[1]} »`;

  match = expr.match(/^new_tab\(\s*["']([^"']*)["']/);
  if (match) return match[1] ? `Ouvrir un onglet : ${compactUrl(match[1])}` : "Ouvrir un onglet";
  if (/^new_tab\(/.test(expr)) return "Ouvrir un onglet";
  if (/^close_tab\(/.test(expr)) return "Fermer l'onglet";
  match = expr.match(/^activate_tab\(\s*([^)]+)\)/);
  if (match) return `Activer l'onglet ${truncate(match[1], 40)}`;
  match = expr.match(/^switch_tab\(\s*([^)]+)\)/);
  if (match) return `Basculer vers l'onglet ${truncate(match[1], 40)}`;
  if (/^current_tab\(/.test(expr)) return "Identifier l'onglet courant";
  if (/^list_tabs\(/.test(expr)) return "Lister les onglets ouverts";
  if (/^page_title\(\)/.test(expr)) return "Lire le titre de la page";
  if (/^page_info\(\)/.test(expr)) return "Récupérer les informations de la page";
  match = expr.match(/^iframe_target\(\s*["']([^"']+)["']/);
  if (match) return `Cibler l'iframe : ${compactUrl(match[1])}`;

  const fromImport = expr.match(/^from\s+(\S+)\s+import\s+/);
  if (fromImport) return `Importer depuis ${fromImport[1]}`;
  const plainImport = expr.match(/^import\s+(\S+)/);
  if (plainImport) return `Importer ${plainImport[1]}`;

  if (/globals\(\)/.test(expr)) return "Lister les fonctions disponibles";

  match = expr.match(/^js\(\s*["']([\s\S]*)/);
  if (match) return describeJs(match[1]);

  match = expr.match(/^http_get\(\s*["']([^"']+)/);
  if (match) return `Récupérer l'URL : ${compactUrl(match[1])}`;

  match = expr.match(/^remember\(\s*["']([^"']*)["']/);
  if (match) return `Mémoriser : « ${truncate(match[1], 90)} »`;
  match = expr.match(/^ask_operator\(\s*["']([^"']*)["']/);
  if (match) return `Demander à l'opérateur : « ${truncate(match[1], 90)} »`;

  if (/^ensure_real_tab\(/.test(expr)) return "S'assurer qu'un onglet réel est actif";
  if (/^ensure_daemon\(/.test(expr)) return "Vérifier le démon du navigateur";
  if (/^drain_events\(/.test(expr)) return "Lire les événements du navigateur";
  if (/^cdp\(/.test(expr)) return "Envoyer une commande Chrome DevTools";

  match = expr.match(/^([A-Za-z_]\w*)\s*=\s*([\s\S]+)$/);
  if (match) {
    const inner = describeBrowserExpression(match[2]);
    return inner
      ? `Mémoriser dans ${match[1]} : ${inner}`
      : `Mémoriser ${truncate(match[2], 80)} dans ${match[1]}`;
  }

  return null;
}

/** A browser-harness snippet, line by line (nested blocks indented). */
export function describeBrowserCode(code: string): string[] {
  const steps: string[] = [];
  const levels: number[] = [];
  for (const raw of code.split("\n")) {
    const indent = (raw.match(/^[ \t]*/)?.[0] ?? "").length;
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;

    while (levels.length && indent < levels[levels.length - 1]) levels.pop();
    if (!levels.length || indent > levels[levels.length - 1]) levels.push(indent);
    const depth = Math.max(0, levels.length - 1);

    const strict = line.match(/^print\((.*)\)$/);
    const loose = strict ? null : line.match(/^print\(([\s\S]+)$/);
    const printed = Boolean(strict || loose);
    const expression = (strict?.[1] ?? loose?.[1] ?? line).trim();
    const described =
      describeBrowserExpression(expression) ??
      (printed
        ? `Afficher : ${truncate(expression, 110)}`
        : `Exécuter : ${truncate(line, 110)}`);
    if (described) {
      steps.push(`${depth > 0 ? `${"  ".repeat(depth - 1)}↳ ` : ""}${described}`);
    }
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
    if (typeof url === "string") {
      steps.push(
        tool.includes("browser") || tool.includes("goto")
          ? `Ouvrir l'URL : ${compactUrl(url)}`
          : `Récupérer l'URL : ${compactUrl(url)}`,
      );
    }
    if (typeof query === "string") steps.push(`Rechercher : « ${truncate(query, 80)} »`);
  }

  return { steps, code: null };
}

export interface ResultDescription {
  kind: "page" | "error" | "empty" | "json" | "text";
  page?: PageInfo;
  error?: string;
  traceback?: string;
}

/** Summarize a tool output: page metadata, execution error, empty, structured
 *  value (JSON **or Python repr**), plain text. */
export function describeResult(preview: unknown): ResultDescription {
  const text = toolText(preview);
  const trimmed = text.trim();

  if (!trimmed || trimmed === "(no output)") return { kind: "empty" };

  if (/Traceback \(most recent call last\)|\[stderr\]/i.test(text)) {
    const match = text.match(/([A-Za-z_.]*(?:Error|Exception)):\s*(.*)$/m);
    return {
      kind: "error",
      error: match ? `${match[1]}: ${match[2]}` : "Erreur d'exécution",
      traceback: text,
    };
  }

  const found = findValue(trimmed);
  if (found) {
    const page = pageFrom(found.value);
    if (page) {
      return {
        kind: "page",
        page: {
          ...page,
          prefix: found.prefix || undefined,
          extra: found.suffix || undefined,
        },
      };
    }
    return { kind: "json" };
  }
  if (salvageList(trimmed)) return { kind: "json" };

  return { kind: "text" };
}
