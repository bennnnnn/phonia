/**
 * Fence-language detection and HTML-preview classification — pure, no
 * Prism dependency. Kept separate from lib/codeTokenize.ts (which imports
 * Prism and registers ~47 grammars at module load) so that rendering a
 * message with zero or non-code fences never pays that cost. Prism is
 * dynamically imported by CodeBlock.tsx only when a code fence actually
 * needs to be tokenized.
 */

export type HighlightToken = { text: string; color: string };

export const TOKEN_COLORS = {
  plain: "#2D2D2D",
  comment: "#52525B",
  string: "#047857",
  number: "#1D4ED8",
  keyword: "#B91C1C",
  function: "#6D28D9",
  className: "#0E7490",
  operator: "#3F3F46",
  builtin: "#C2410C",
  variable: "#854D0E",
  tag: "#047857",
} as const;

/**
 * Dark-mode syntax colors. The light palette's saturated mid-tones read on a
 * light panel, but on `codeBg` (#0D0D0D) the near-black `plain` vanishes and
 * the rest feel too dim — so each token is shifted to a brighter Tailwind
 * variant here. `colorFor()` in CodeBlock swaps a tokenized light color for
 * its dark counterpart when `theme.isDark`.
 */
const DARK_TOKEN_COLORS = {
  plain: "#E6E6E6",
  comment: "#9CA3AF",
  string: "#34D399",
  number: "#60A5FA",
  keyword: "#F87171",
  function: "#A78BFA",
  className: "#22D3EE",
  operator: "#94A3B8",
  builtin: "#FB923C",
  variable: "#FACC15",
  tag: "#34D399",
} as const;

const LIGHT_TO_DARK_TOKEN: Record<string, string> = Object.fromEntries(
  Object.entries(TOKEN_COLORS).map(([key, hex]) => [hex, DARK_TOKEN_COLORS[key as keyof typeof TOKEN_COLORS]]),
);

/**
 * Resolve a tokenized color (a light TOKEN_COLORS hex) for the current scheme.
 * Falls back to the input color for unrecognized values (e.g. already-dark or
 * custom colors), so it never mangles a color it didn't assign.
 */
export function resolveTokenColor(color: string, isDark: boolean): string {
  if (!isDark) return color;
  return LIGHT_TO_DARK_TOKEN[color] ?? color;
}

const LANG_TO_PRISM: Record<string, string> = {
  javascript: "javascript",
  js: "javascript",
  jsx: "jsx",
  typescript: "typescript",
  ts: "typescript",
  tsx: "tsx",
  python: "python",
  py: "python",
  bash: "bash",
  sh: "bash",
  shell: "bash",
  zsh: "bash",
  json: "json",
  sql: "sql",
  go: "go",
  golang: "go",
  rust: "rust",
  rs: "rust",
  java: "java",
  css: "css",
  scss: "scss",
  html: "markup",
  xml: "markup",
  markup: "markup",
  svg: "markup",
  yaml: "yaml",
  yml: "yaml",
  markdown: "markdown",
  md: "markdown",
  ruby: "ruby",
  rb: "ruby",
  swift: "swift",
  kotlin: "kotlin",
  kt: "kotlin",
  kts: "kotlin",
  c: "c",
  cpp: "cpp",
  "c++": "cpp",
  csharp: "csharp",
  "c#": "csharp",
  cs: "csharp",
  php: "php",
  docker: "docker",
  dockerfile: "docker",
  graphql: "graphql",
  gql: "graphql",
  diff: "diff",
  patch: "diff",
  lua: "lua",
  dart: "dart",
  r: "r",
  powershell: "powershell",
  ps1: "powershell",
  pwsh: "powershell",
  nginx: "nginx",
  toml: "toml",
  ini: "ini",
  env: "ini",
  makefile: "makefile",
  make: "makefile",
  objc: "objectivec",
  "objective-c": "objectivec",
  objectivec: "objectivec",
  scala: "scala",
  elixir: "elixir",
  ex: "elixir",
  haskell: "haskell",
  hs: "haskell",
  latex: "latex",
  tex: "latex",
  vue: "markup",
  svelte: "markup",
  code: "clike",
  plaintext: "clike",
  react: "jsx",
  "react-native": "jsx",
  rn: "jsx",
  expo: "javascript",
  node: "javascript",
  express: "javascript",
  prisma: "sql",
  proto: "protobuf",
  protobuf: "protobuf",
  tf: "hcl",
  hcl: "hcl",
  terraform: "hcl",
  vim: "vim",
  perl: "perl",
  pl: "perl",
  matlab: "matlab",
  m: "matlab",
  arduino: "cpp",
  arduino_cpp: "cpp",
  terminal: "bash",
  shellsession: "bash",
  console: "bash",
  cmd: "bash",
  prompt: "bash",
  log: "clike",
  logs: "clike",
};

export function parseFenceLang(info: string): string {
  const raw = info.trim();
  if (!raw) return "";
  const first = raw.split(/\s+/)[0] ?? "";
  return first.replace(/[{:[].*$/, "").toLowerCase();
}

/**
 * Fences with no real language. These are teaching snippets (`name = "john"`)
 * and must not grow a corner label or guessed keyword colors.
 */
const TEACHING_FENCE_LANGS = new Set([
  "text",
  "txt",
  "plaintext",
  "plain",
  "code",
  "none",
  "output",
  "example",
]);

/** Corner label for a tagged fence. Acronyms and aliases that title-case gets wrong. */
const LANG_LABELS: Record<string, string> = {
  python: "Python",
  py: "Python",
  javascript: "JavaScript",
  js: "JavaScript",
  jsx: "JavaScript",
  typescript: "TypeScript",
  ts: "TypeScript",
  tsx: "TypeScript",
  react: "JavaScript",
  "react-native": "JavaScript",
  rn: "JavaScript",
  node: "JavaScript",
  expo: "JavaScript",
  express: "JavaScript",
  bash: "Shell",
  sh: "Shell",
  shell: "Shell",
  zsh: "Shell",
  terminal: "Shell",
  shellsession: "Shell",
  console: "Shell",
  cmd: "Shell",
  prompt: "Shell",
  json: "JSON",
  sql: "SQL",
  go: "Go",
  golang: "Go",
  rust: "Rust",
  rs: "Rust",
  java: "Java",
  css: "CSS",
  scss: "SCSS",
  html: "HTML",
  htm: "HTML",
  xml: "XML",
  svg: "SVG",
  yaml: "YAML",
  yml: "YAML",
  markdown: "Markdown",
  md: "Markdown",
  ruby: "Ruby",
  rb: "Ruby",
  swift: "Swift",
  kotlin: "Kotlin",
  kt: "Kotlin",
  kts: "Kotlin",
  c: "C",
  cpp: "C++",
  "c++": "C++",
  csharp: "C#",
  "c#": "C#",
  cs: "C#",
  php: "PHP",
  objectivec: "Objective-C",
  objc: "Objective-C",
  "objective-c": "Objective-C",
  graphql: "GraphQL",
  gql: "GraphQL",
  dockerfile: "Docker",
  docker: "Docker",
  powershell: "PowerShell",
  ps1: "PowerShell",
  pwsh: "PowerShell",
  terraform: "Terraform",
  tf: "Terraform",
  hcl: "Terraform",
  protobuf: "Protobuf",
  proto: "Protobuf",
  latex: "LaTeX",
  tex: "LaTeX",
};

function titleLang(raw: string): string {
  const mapped = LANG_LABELS[raw];
  if (mapped) return mapped;
  if (raw.length <= 2) return raw.toUpperCase();
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

/**
 * Language name for the corner of a code card.
 * Empty and teaching tags (`text`, bare ``` ) return null — those snippets
 * are not a language.
 */
export function codeLanguageLabel(info: string): string | null {
  const raw = parseFenceLang(info);
  if (!raw || TEACHING_FENCE_LANGS.has(raw)) return null;
  return titleLang(raw);
}

/** Syntax colors only for an explicit language we actually highlight. */
export function fenceUsesSyntaxColor(info: string): boolean {
  const raw = parseFenceLang(info);
  if (!raw || TEACHING_FENCE_LANGS.has(raw)) return false;
  return Boolean(LANG_TO_PRISM[raw]);
}

/** True for ```diff / ```patch fences, which color by line instead of by token. */
export function isDiffFence(info: string): boolean {
  return LANG_TO_PRISM[parseFenceLang(info)] === "diff";
}

/** A diff line's role: an added or removed line, a hunk (`@@`), or a file header. */
export type DiffLineKind = "added" | "removed" | "hunk" | "header" | null;

/**
 * Each line's role, read in order: `--- a/file` and `+++ b/file` are file
 * headers only before a hunk starts, so a removed SQL comment (`--- note`)
 * inside a hunk stays a removed line.
 */
export function diffLineKinds(lines: string[]): DiffLineKind[] {
  let inHunk = false;
  return lines.map((line) => {
    if (/^(diff --git|index [0-9a-f])/.test(line)) {
      inHunk = false;
      return "header";
    }
    if (line.startsWith("@@")) {
      inHunk = true;
      return "hunk";
    }
    if (!inHunk && /^(---|\+\+\+)(\s|$)/.test(line)) return "header";
    if (line.startsWith("+")) return "added";
    if (line.startsWith("-")) return "removed";
    return null;
  });
}

export function normalizeLang(lang: string): string {
  const raw = parseFenceLang(lang);
  if (!raw) return "";
  return LANG_TO_PRISM[raw] ?? raw;
}

export function groupTokensByLine(tokens: HighlightToken[]): HighlightToken[][] {
  const lines: HighlightToken[][] = [[]];
  for (const token of tokens) {
    const parts = token.text.split("\n");
    for (let i = 0; i < parts.length; i++) {
      if (i > 0) lines.push([]);
      if (parts[i].length > 0) {
        lines[lines.length - 1].push({ text: parts[i], color: token.color });
      }
    }
  }
  if (lines.length === 1 && lines[0].length === 0) return [[]];
  return lines;
}

/** True for ```html / ```htm / ```markup fences. */
export function isHtmlFenceLang(lang: string): boolean {
  const l = lang.trim().toLowerCase();
  return l === "html" || l === "htm" || l === "markup";
}

/** True when fence content looks like a renderable HTML page or fragment. */
export function looksLikeHtmlPage(code: string): boolean {
  const sample = code.trim().slice(0, 800);
  if (/^\s*<!DOCTYPE\s+html/i.test(sample)) return true;
  if (/^\s*<html[\s>]/i.test(sample)) return true;
  if (/^\s*<head[\s>]/i.test(sample)) return true;
  if (/^\s*<style[\s>]/i.test(sample) && /<\/style>/i.test(code)) return true;
  if (/^\s*<body[\s>]/i.test(sample)) return true;
  if (
    /<(?:html|head|body|div|section|main|form|table|style|script)[\s>]/i.test(
      sample,
    ) &&
    /<\/(?:html|body|div|section|main|form|table|script)>/i.test(code)
  ) {
    return true;
  }
  return false;
}

/** Web preview UI — only for HTML fences, not JS/JSX/Python with angle brackets. */
export function shouldUseHtmlPreview(lang: string, content: string): boolean {
  if (isHtmlFenceLang(lang)) return true;
  const l = lang.trim().toLowerCase();
  if (l && l !== "plain" && l !== "text" && l !== "clike") return false;
  return looksLikeHtmlPage(content);
}
