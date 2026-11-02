/**
 * Prism-backed syntax tokenizing — see FEATURES.md §4. Deliberately kept
 * out of lib/codeHighlight.ts (which every message render touches for
 * fence-language parsing) so that registering ~47 Prism grammars only
 * happens the first time a code fence is actually tokenized, via
 * CodeBlock.tsx's dynamic import() of this module.
 */
import Prism from "prismjs";

import { normalizeLang, type HighlightToken, TOKEN_COLORS } from "@/lib/codeHighlight";

type GlobalWithPrism = typeof globalThis & { Prism: typeof Prism };

const g = globalThis as GlobalWithPrism;
if (!g.Prism) {
  g.Prism = Prism;
}

// Static requires — Metro must see literal paths.
require("prismjs/components/prism-clike");
require("prismjs/components/prism-markup");
require("prismjs/components/prism-javascript");
require("prismjs/components/prism-typescript");
require("prismjs/components/prism-jsx");
require("prismjs/components/prism-tsx");
require("prismjs/components/prism-python");
require("prismjs/components/prism-bash");
require("prismjs/components/prism-json");
require("prismjs/components/prism-sql");
require("prismjs/components/prism-go");
require("prismjs/components/prism-rust");
require("prismjs/components/prism-java");
require("prismjs/components/prism-css");
require("prismjs/components/prism-scss");
require("prismjs/components/prism-yaml");
require("prismjs/components/prism-markdown");
require("prismjs/components/prism-ruby");
require("prismjs/components/prism-swift");
require("prismjs/components/prism-kotlin");
require("prismjs/components/prism-c");
require("prismjs/components/prism-cpp");
require("prismjs/components/prism-csharp");
require("prismjs/components/prism-php");
require("prismjs/components/prism-docker");
require("prismjs/components/prism-graphql");
require("prismjs/components/prism-diff");
require("prismjs/components/prism-lua");
require("prismjs/components/prism-dart");
require("prismjs/components/prism-r");
require("prismjs/components/prism-powershell");
require("prismjs/components/prism-nginx");
require("prismjs/components/prism-toml");
require("prismjs/components/prism-ini");
require("prismjs/components/prism-makefile");
require("prismjs/components/prism-objectivec");
require("prismjs/components/prism-scala");
require("prismjs/components/prism-elixir");
require("prismjs/components/prism-haskell");
require("prismjs/components/prism-latex");
require("prismjs/components/prism-protobuf");
require("prismjs/components/prism-hcl");
require("prismjs/components/prism-vim");
require("prismjs/components/prism-perl");
require("prismjs/components/prism-matlab");
require("prismjs/components/prism-properties");

/** Colorful light-theme palette — green strings, blue numbers, purple functions, etc. */
const PRISM_THEME: Record<string, string> = {
  plain: TOKEN_COLORS.plain,
  comment: TOKEN_COLORS.comment,
  prolog: TOKEN_COLORS.comment,
  doctype: TOKEN_COLORS.comment,
  cdata: TOKEN_COLORS.comment,
  // Punctuation and names stay the body color. A second gray/gold on
  // every symbol reads as a random wash over the keywords that matter.
  punctuation: TOKEN_COLORS.plain,
  operator: TOKEN_COLORS.plain,
  property: TOKEN_COLORS.plain,
  tag: TOKEN_COLORS.tag,
  boolean: TOKEN_COLORS.number,
  number: TOKEN_COLORS.number,
  constant: TOKEN_COLORS.number,
  symbol: TOKEN_COLORS.number,
  deleted: TOKEN_COLORS.keyword,
  selector: TOKEN_COLORS.string,
  "attr-name": TOKEN_COLORS.number,
  string: TOKEN_COLORS.string,
  char: TOKEN_COLORS.string,
  builtin: TOKEN_COLORS.builtin,
  inserted: TOKEN_COLORS.className,
  entity: TOKEN_COLORS.plain,
  url: TOKEN_COLORS.number,
  variable: TOKEN_COLORS.plain,
  atrule: TOKEN_COLORS.keyword,
  "attr-value": TOKEN_COLORS.string,
  function: TOKEN_COLORS.function,
  "function-variable": TOKEN_COLORS.function,
  "class-name": TOKEN_COLORS.className,
  keyword: TOKEN_COLORS.keyword,
  regex: TOKEN_COLORS.builtin,
  important: TOKEN_COLORS.builtin,
  bold: TOKEN_COLORS.plain,
  italic: TOKEN_COLORS.plain,
  namespace: TOKEN_COLORS.className,
  "maybe-class-name": TOKEN_COLORS.className,
  parameter: TOKEN_COLORS.plain,
  decorator: TOKEN_COLORS.className,
  "template-string": TOKEN_COLORS.string,
  "template-punctuation": TOKEN_COLORS.operator,
  interpolation: TOKEN_COLORS.builtin,
  "literal-property": TOKEN_COLORS.plain,
  "constant-variable": TOKEN_COLORS.number,
  module: TOKEN_COLORS.className,
  scalar: TOKEN_COLORS.number,
  directive: TOKEN_COLORS.keyword,
  "storage-type": TOKEN_COLORS.keyword,
  "storage-modifier": TOKEN_COLORS.keyword,
};

export function looksLikeJava(code: string): boolean {
  const sample = code.slice(0, 1500);
  if (/\bSystem\.(out|in|err)\./.test(sample)) return true;
  if (
    /public\s+static\s+void\s+main\s*\(\s*String\s*(\[\]|\.\.\.)/.test(sample)
  )
    return true;
  if (/^\s*package\s+[\w.]+\s*;/m.test(sample)) return true;
  if (
    /^\s*import\s+(?:static\s+)?(?:java|javax|jakarta|org|com|net)\./m.test(
      sample,
    )
  )
    return true;
  if (
    /^\s*(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:class|interface|enum|record)\s+/m.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    /\b(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:void|int|long|double|float|boolean|char|String)\s+\w+\s*\(/m.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    /@(?:Override|Deprecated|SuppressWarnings|Autowired|Service|Component|SpringBootApplication)\b/.test(
      sample,
    )
  ) {
    return true;
  }
  return false;
}

function looksLikeJavaScript(code: string): boolean {
  if (looksLikeJava(code) || looksLikeC(code)) return false;
  const sample = code.slice(0, 1500);
  if (
    /\b(console\.(log|error|warn|debug)|useState|useEffect|require\(|module\.exports|=>\s*[\({])/.test(
      sample,
    )
  ) {
    return true;
  }
  if (/^\s*(export|const|let|var|function)\s/m.test(sample)) return true;
  if (
    /^\s*import\s+[\w*{'"@/]/.test(sample) &&
    !/^\s*import\s+(?:static\s+)?[\w.]+\s*;/m.test(sample)
  ) {
    return true;
  }
  return false;
}

export function looksLikeC(code: string): boolean {
  const sample = code.slice(0, 1500);
  if (/^\s*#\s*(?:include|define|ifdef|ifndef|endif|pragma)\b/m.test(sample))
    return true;
  if (
    /\b(?:stdio\.h|stdlib\.h|string\.h|stdint\.h|unistd\.h|stddef\.h)\b/.test(
      sample,
    )
  )
    return true;
  if (
    /\b(?:printf|scanf|fprintf|sprintf|malloc|calloc|realloc|free|sizeof|typedef)\s*\(/.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    /^\s*(?:int|void|char|long|short|unsigned|signed|float|double|bool|size_t|uint\d_t|int\d_t)\s+\w+/m.test(
      sample,
    )
  ) {
    return true;
  }
  if (/^\s*int\s+main\s*\(/m.test(sample)) return true;
  return false;
}

function looksLikeCpp(code: string): boolean {
  const sample = code.slice(0, 1500);
  if (
    looksLikeC(sample) &&
    /\b(?:std::|namespace|template|typename|cout|cin|vector|string|class|new|delete|nullptr)\b/.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    /^\s*#include\s*<(?:iostream|vector|string|memory|algorithm)/m.test(sample)
  )
    return true;
  return false;
}

function looksLikePython(code: string): boolean {
  if (looksLikeC(code) || looksLikeJava(code)) return false;
  const sample = code.slice(0, 1500);
  if (/^\s*(?:def|class)\s+\w+/m.test(sample)) return true;
  if (/^\s*from\s+\w+\s+import\b/m.test(sample)) return true;
  if (/^\s*import\s+(?!java|javax|jakarta|org\.|com\.|static\s)/m.test(sample))
    return true;
  if (
    /\b(?:self|elif|pass|lambda|None|True|False|async def|await|nonlocal|global)\b/.test(
      sample,
    )
  )
    return true;
  return false;
}

/** Resolve language: explicit fence tag wins; guess only when untagged. */
export function resolveHighlightLang(fenceLang: string, code: string): string {
  const normalized = normalizeLang(fenceLang);
  if (normalized && Prism.languages[normalized]) return normalized;
  return guessLang(code);
}

export function guessLang(code: string): string {
  const sample = code.slice(0, 1500);
  if (/^\s*<\/?[a-z]/im.test(sample)) return "markup";
  if (/^\s*\{[\s\S]*"[\w-]+"\s*:/m.test(sample)) return "json";
  if (/^\s*(\{|\[)/.test(sample) && /"\w+"\s*:/.test(sample)) return "json";
  if (looksLikeCpp(sample)) return "cpp";
  if (looksLikeC(sample)) return "c";
  if (
    /^\s*package\s+\w+\s*$/m.test(sample) &&
    /\b(fun|val|var|println)\b/.test(sample)
  )
    return "kotlin";
  if (/^\s*package\s+\w+\s*;/m.test(sample) && looksLikeJava(sample))
    return "java";
  if (/^\s*func\s+\w+/m.test(sample)) return "go";
  if (/^\s*package\s+\w+\s*$/m.test(sample) && !looksLikeJava(sample))
    return "go";
  if (looksLikePython(sample)) return "python";
  if (looksLikeJava(sample)) return "java";
  if (
    /^\s*@(?:Composable|Preview)/m.test(sample) &&
    /\bfun\b|\bval\b/.test(sample)
  )
    return "kotlin";
  if (/^\s*using\s+System/m.test(sample)) return "csharp";
  if (/^\s*(fn|let|mut|impl|pub)\s/m.test(sample)) return "rust";
  if (/^\s*SELECT\s+/im.test(sample)) return "sql";
  if (looksLikeJavaScript(sample)) return "javascript";
  if (/^\s*(class|interface)\s/m.test(sample)) {
    return /\b(public|private|protected|extends|implements)\b/.test(sample)
      ? "java"
      : "javascript";
  }
  if (/^\s*---\s*$/m.test(sample) && /^\s*\w+\s*:/m.test(sample)) return "yaml";
  if (/^\s*\[\w+\]/m.test(sample) && /^\s*\w+\s*=/m.test(sample)) return "ini";
  if (/^\s*diff --git/m.test(sample)) return "diff";
  if (/^\s*#!\/.*\b(bash|sh|zsh)\b/m.test(sample)) return "bash";
  if (/^\s*<\?php/m.test(sample)) return "php";
  if (/^\s*<\?xml/m.test(sample)) return "markup";
  if (/^\s*resource\s+"/m.test(sample)) return "hcl";
  if (/^\s*syntax\s*=\s*"/m.test(sample)) return "protobuf";
  return "clike";
}

function grammarKeyForEnrich(key: string): string {
  if (LANGUAGE_KEYWORDS[key]) return key;
  if (key === "jsx" || key === "tsx") return "javascript";
  if (key === "typescript") return "typescript";
  if (key === "cpp") return "cpp";
  if (key === "c") return "c";
  if (key === "csharp") return "csharp";
  if (key === "kotlin" || key === "swift" || key === "scala") return "java";
  return key;
}

function tokenizeWithGrammar(
  code: string,
  grammar: Prism.Grammar,
): HighlightToken[] {
  const prismTokens = Prism.tokenize(code, grammar);
  return flattenPrismTokens(prismTokens);
}

function colorForTokenType(type: string | string[]): string {
  const types = Array.isArray(type) ? type : [type];
  for (const key of types) {
    const themed = PRISM_THEME[key];
    if (themed && themed !== TOKEN_COLORS.plain) return themed;
  }
  for (const key of types) {
    if (PRISM_THEME[key]) return PRISM_THEME[key];
  }
  return TOKEN_COLORS.plain;
}

function flattenPrismTokens(
  tokens: string | Prism.Token | Array<string | Prism.Token>,
): HighlightToken[] {
  if (typeof tokens === "string") {
    return tokens.length > 0
      ? [{ text: tokens, color: TOKEN_COLORS.plain }]
      : [];
  }

  if (!Array.isArray(tokens)) {
    const color = colorForTokenType(tokens.type);
    const { content } = tokens;
    if (typeof content === "string") {
      return content.length > 0 ? [{ text: content, color }] : [];
    }
    return flattenPrismTokens(content);
  }

  const out: HighlightToken[] = [];
  for (const token of tokens) {
    out.push(...flattenPrismTokens(token));
  }
  return out;
}

const LANGUAGE_KEYWORDS: Record<string, RegExp> = {
  // `g` required so lastIndex advances in highlightPlainChunk.
  c: /\b(?:if|else|for|while|do|switch|case|default|break|continue|return|goto|sizeof|typedef|struct|enum|union|const|static|extern|volatile|register|inline|restrict|void|int|char|long|short|float|double|signed|unsigned|bool|true|false|NULL|include|define|undef|ifdef|ifndef|elif|endif|pragma)\b/g,
  cpp: /\b(?:if|else|for|while|do|switch|case|default|break|continue|return|class|struct|enum|union|namespace|template|typename|public|private|protected|virtual|override|const|static|constexpr|noexcept|new|delete|nullptr|using|try|catch|throw|this|true|false|include|define|std)\b/g,
  csharp:
    /\b(?:class|interface|enum|struct|namespace|using|public|private|protected|internal|static|readonly|void|int|long|double|float|bool|string|var|if|else|for|foreach|while|do|switch|case|default|return|try|catch|finally|throw|new|this|base|true|false|null|async|await|get|set|value|record|override|virtual|abstract|sealed|partial|const|typeof|is|as|in|out|ref|params|where)\b/g,
  python:
    /\b(?:def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|yield|lambda|pass|break|continue|raise|True|False|None|and|or|not|in|is|async|await|global|nonlocal|del|assert|match|case)\b/g,
  javascript:
    /\b(?:const|let|var|function|class|import|export|from|return|if|else|for|while|do|try|catch|finally|throw|async|await|new|typeof|instanceof|of|in|true|false|null|undefined|this|super|extends|static|get|set|default|switch|case|break|continue|void|delete|yield|interface|type|enum|implements|readonly|declare|namespace|module)\b/g,
  typescript:
    /\b(?:const|let|var|function|class|import|export|from|return|if|else|for|while|do|try|catch|finally|throw|async|await|new|typeof|instanceof|of|in|true|false|null|undefined|this|super|extends|static|get|set|default|switch|case|break|continue|void|delete|yield|interface|type|enum|implements|readonly|declare|namespace|module|keyof|never|unknown|any|string|number|boolean)\b/g,
  rust: /\b(?:fn|let|mut|const|if|else|match|for|while|loop|return|struct|enum|impl|trait|pub|use|mod|self|Self|true|false|Some|None|Ok|Err|async|await|move|where|type|dyn|ref|static|unsafe|extern|crate|super|in|as|break|continue|macro)\b/g,
  go: /\b(?:func|var|const|type|struct|interface|map|chan|if|else|for|range|switch|case|default|return|go|defer|package|import|true|false|nil|break|continue|fallthrough|select|goto)\b/g,
  java: /\b(?:class|interface|enum|extends|implements|import|package|public|private|protected|static|final|void|int|long|double|float|boolean|char|byte|short|if|else|for|while|do|switch|case|default|return|try|catch|finally|throw|new|this|super|true|false|null|break|continue|instanceof|synchronized|volatile|transient|native|assert|yield|record|sealed|permits|var)\b/g,
  sql: /\b(?:SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|INDEX|DROP|ALTER|ADD|NOT|NULL|AND|OR|AS|DISTINCT|COUNT|SUM|AVG|MAX|MIN|LIKE|IN|IS|BETWEEN|EXISTS|CASE|WHEN|THEN|ELSE|END|UNION|ALL|PRIMARY|KEY|FOREIGN|REFERENCES|TRUE|FALSE)\b/gi,
  bash: /\b(?:if|then|else|elif|fi|for|while|do|done|case|esac|function|return|in|export|local|readonly|declare|unset|exit|echo|cd|pwd|source|true|false)\b/g,
};

function commentRulesFor(
  grammarKey: string,
): Array<{ re: RegExp; color: string }> {
  const rules: Array<{ re: RegExp; color: string }> = [];
  const hashCommentLangs = new Set([
    "python",
    "bash",
    "yaml",
    "ruby",
    "powershell",
    "docker",
    "nginx",
    "perl",
  ]);
  if (hashCommentLangs.has(grammarKey)) {
    rules.push({ re: /#.*$/gm, color: TOKEN_COLORS.comment });
  }
  if (
    grammarKey === "c" ||
    grammarKey === "cpp" ||
    grammarKey === "csharp" ||
    grammarKey === "java" ||
    grammarKey === "go" ||
    grammarKey === "rust" ||
    grammarKey === "javascript" ||
    grammarKey === "typescript" ||
    grammarKey === "kotlin" ||
    grammarKey === "swift"
  ) {
    rules.push({ re: /\/\/.*$/gm, color: TOKEN_COLORS.comment });
    rules.push({ re: /\/\*[\s\S]*?\*\//g, color: TOKEN_COLORS.comment });
  }
  if (grammarKey === "c" || grammarKey === "cpp") {
    rules.push({
      re: /^\s*#\s*(?:include|define|ifdef|ifndef|endif|elif|else|undef|pragma|error|warning)\b[^\n]*/gm,
      color: TOKEN_COLORS.keyword,
    });
  }
  return rules;
}

/** Cap for second-pass regex enrichment — oversized plain chunks stay plain. */
export const MAX_PLAIN_HIGHLIGHT_CHARS = 32768;

/** Second pass: color keywords, numbers, calls, etc. that Prism left as plain text. */
export function highlightPlainChunk(
  text: string,
  grammarKey: string,
): HighlightToken[] {
  if (!text) return [];
  if (text.length > MAX_PLAIN_HIGHLIGHT_CHARS) {
    return [{ text, color: TOKEN_COLORS.plain }];
  }

  const kwKey = grammarKeyForEnrich(grammarKey);
  const keywordRe = LANGUAGE_KEYWORDS[kwKey];

  type Rule = { re: RegExp; color: string };
  // Keywords before the call heuristic, so `True` / `return` stay keywords
  // and a capitalized word is not painted as a class by accident.
  const rules: Rule[] = [
    ...commentRulesFor(kwKey),
    {
      re: /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`/g,
      color: TOKEN_COLORS.string,
    },
  ];
  if (keywordRe) rules.push({ re: keywordRe, color: TOKEN_COLORS.keyword });
  rules.push(
    { re: /\b0x[\da-fA-F]+\b|\b\d+\.?\d*\b/g, color: TOKEN_COLORS.number },
    { re: /\b[a-zA-Z_]\w*(?=\s*\()/g, color: TOKEN_COLORS.function },
  );

  const out: HighlightToken[] = [];
  let i = 0;
  while (i < text.length) {
    let best: { start: number; end: number; color: string } | null = null;
    for (const rule of rules) {
      rule.re.lastIndex = i;
      const match = rule.re.exec(text);
      if (!match || match.index < i) continue;
      if (match.index === i) {
        best = {
          start: match.index,
          end: match.index + match[0].length,
          color: rule.color,
        };
        break;
      }
      if (!best || match.index < best.start) {
        best = {
          start: match.index,
          end: match.index + match[0].length,
          color: rule.color,
        };
      }
    }

    if (!best || best.start > i) {
      const end = best?.start ?? text.length;
      out.push({ text: text.slice(i, end), color: TOKEN_COLORS.plain });
      i = end;
      continue;
    }

    out.push({ text: text.slice(best.start, best.end), color: best.color });
    i = best.end;
  }

  return out.length > 0 ? out : [{ text, color: TOKEN_COLORS.plain }];
}

function mergeAdjacentTokens(tokens: HighlightToken[]): HighlightToken[] {
  if (tokens.length === 0) return tokens;
  const out: HighlightToken[] = [{ ...tokens[0] }];
  for (let i = 1; i < tokens.length; i++) {
    const prev = out[out.length - 1];
    const cur = tokens[i];
    if (prev.color === cur.color) prev.text += cur.text;
    else out.push({ ...cur });
  }
  return out;
}

function enrichPlainTokens(
  tokens: HighlightToken[],
  grammarKey: string,
): HighlightToken[] {
  const out: HighlightToken[] = [];
  for (const token of tokens) {
    if (token.color !== TOKEN_COLORS.plain) out.push(token);
    else out.push(...highlightPlainChunk(token.text, grammarKey));
  }
  return mergeAdjacentTokens(out);
}

export function tokenize(code: string, lang: string): HighlightToken[] {
  if (!code) return [];

  const key = resolveHighlightLang(lang, code);
  const grammar = Prism.languages[key];
  if (!grammar) {
    return [{ text: code, color: TOKEN_COLORS.plain }];
  }

  try {
    const flat = tokenizeWithGrammar(code, grammar);
    if (flat.length === 0) return [{ text: code, color: TOKEN_COLORS.plain }];
    return enrichPlainTokens(flat, key);
  } catch {
    return [{ text: code, color: TOKEN_COLORS.plain }];
  }
}
