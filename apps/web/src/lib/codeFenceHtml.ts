/** Corner label for a tagged fence. Teaching tags stay unlabeled. */
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

const LANG_LABELS: Record<string, string> = {
  python: "Python",
  py: "Python",
  javascript: "JavaScript",
  js: "JavaScript",
  jsx: "JavaScript",
  typescript: "TypeScript",
  ts: "TypeScript",
  tsx: "TypeScript",
  bash: "Shell",
  sh: "Shell",
  shell: "Shell",
  json: "JSON",
  sql: "SQL",
  html: "HTML",
  css: "CSS",
  cpp: "C++",
  "c++": "C++",
  csharp: "C#",
  "c#": "C#",
  yaml: "YAML",
  yml: "YAML",
  go: "Go",
  rust: "Rust",
  java: "Java",
  php: "PHP",
  ruby: "Ruby",
  kotlin: "Kotlin",
  swift: "Swift",
  md: "Markdown",
  markdown: "Markdown",
};

export function codeLanguageLabel(info: string | undefined | null): string | null {
  const first = (info ?? "").trim().split(/\s+/)[0] ?? "";
  const raw = first.replace(/[{:[].*$/, "").toLowerCase();
  if (!raw || TEACHING_FENCE_LANGS.has(raw)) return null;
  const mapped = LANG_LABELS[raw];
  if (mapped) return mapped;
  if (raw.length <= 2) return raw.toUpperCase();
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Fenced code HTML: language span only when the fence names a language. */
export function renderFencedCodeHtml(text: string, lang?: string): string {
  const label = codeLanguageLabel(lang);
  const badge = label ? `<span>${escapeHtml(label)}</span>` : "";
  return `<pre>${badge}<code>${escapeHtml(text)}</code></pre>\n`;
}
