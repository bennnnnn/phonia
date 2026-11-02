import { fenceIdForLang, fenceSpecForLang, isNeverCodeBlockLang } from "@/lib/fenceRegistry";
import { markdownToCopyText } from "@/lib/markdown/plain";
import { looksLikeMathFenceBody, stripEmbeddedDollarWraps } from "@/lib/math/fenceRetag";

const COPY_LANGS = new Set([
  "copy",
  "text",
  "message",
  "email",
  "sms",
  "reply",
]);

export function isCopyLang(lang: string): boolean {
  return COPY_LANGS.has(lang.trim().toLowerCase());
}

/** Fences with no real language tag — usually plain text from the model. */
function isProseLang(lang: string): boolean {
  const l = lang.trim().toLowerCase();
  return !l || l === "clike" || l === "text" || l === "plain";
}

/** Heuristic: content is source code, not copy-ready prose. */
export function looksLikeCode(content: string): boolean {
  if (looksLikeExplanatoryProse(content)) return false;
  if (looksLikeMathFenceBody(content)) return false;
  const sample = content.slice(0, 2000);
  // Keywords as code spells them: "Class starts at 9" or "Update the wiki" opens
  // a sentence in a message, and read as code it lost the draft its card.
  if (
    /^\s*(def |class |function |import |export |const |var |public |private |protected |#include |package |func |fn |interface |type |enum |struct |impl |module |namespace |using |SELECT |CREATE |INSERT |UPDATE |DELETE )/m.test(
      sample,
    ) ||
    /^\s*(<!DOCTYPE|<\/?[a-z][\w-]*[\s/>])/im.test(sample)
  ) {
    return true;
  }
  // `Let me know...` is one of the most common message openings. Treat
  // lowercase `let` as code only when it has declaration syntax.
  if (/^\s*let\s+[A-Za-z_$][\w$]*\s*(?::[^=\n;]+)?=/m.test(sample)) {
    return true;
  }
  if (/^\s{4}\S/m.test(sample) || /^\t+\S/m.test(sample)) return true;
  if (/^\s*[\[{]/.test(sample) && /[;\}\],]/.test(sample)) return true;
  if (/^\s*(\/\/|\/\*|#(?!!)|\*)\s/m.test(sample)) return true;
  const mentionsLangPlusPlus = /\bC\+\+/m.test(sample);
  if (
    !mentionsLangPlusPlus &&
    /(\+\+|::|!==|===|!=|=>|\)\s*\{|\)\s*=>|;\s*$)/m.test(sample)
  ) {
    return true;
  }
  if (/^\s*@\w+|^\s*<\w+[\s/>]/.test(sample)) return true;
  if (/^\s*(if|for|while|switch|return|await|async)\s*[\(\{]/m.test(sample))
    return true;
  if (
    /\b(console\.(log|error|warn|debug)|print\(|fmt\.Print|System\.out|useState\(|useEffect\()/m.test(
      sample,
    )
  ) {
    return true;
  }
  // A call touches its parenthesis; prose puts a space before an aside
  // ("Friday (Oct 24)").
  if (
    /\w\([^)]*\)\s*[;{]?/m.test(sample) &&
    /[{}();]/.test(sample) &&
    sample.split("\n").length >= 2
  ) {
    return true;
  }
  return false;
}

/** Route to syntax-highlighted CodeBlock instead of copy/plain prose. */
export function shouldRenderAsCodeBlock(
  lang: string,
  content: string,
): boolean {
  if (looksLikeAssistantMeta(content)) return false;
  if (looksLikeExplanatoryProse(content)) return false;
  const l = lang.trim().toLowerCase();
  if (
    (l === "copy" ||
      l === "message" ||
      l === "email" ||
      l === "sms" ||
      l === "reply") &&
    !looksLikeCode(content)
  ) {
    return false;
  }
  if (isExplicitCodeLang(lang)) return true;
  return looksLikeCode(content);
}

/** Educational / explanatory prose — not a copy-and-send deliverable. */
function looksLikeExplanatoryProse(content: string): boolean {
  const sample = content.slice(0, 1600).trim();
  if (/^\s*>/m.test(sample)) return true;
  if (/^#{1,6}\s/m.test(sample)) return true;
  if (looksLikeAdvisoryNote(content)) return true;
  if (
    /\*\*[^*]+\*\*/.test(sample) &&
    /(?:in Python|in JavaScript|in TypeScript|these methods|this method|does not modify|do not modify|creates? a new|returns? a new|the following|for example|Note that|Remember that|Keep in mind|are immutable|is immutable)/i.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    /^[-*•]\s/m.test(sample) &&
    sample.split("\n").filter((l) => /^[-*•]\s/.test(l.trim())).length >= 2
  ) {
    return true;
  }
  return false;
}

/** Recommendations, comparisons, career/stack advice — not paste-and-send text. */
function hasDefiniteAdvisorySignals(content: string): boolean {
  const sample = content.slice(0, 1600).trim();
  if (
    /^(As a|If you('| a)re|For most|In general|When (choosing|building|learning)|I('| would) (recommend|suggest)|A solid|Good choices|Consider|You might|You('ll| will) (want|find)|Overall,|In practice,)/i.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    /\b(is|are) a (solid|good|great|strong|reasonable|sensible|practical) (choice|combo|option|stack|pick|approach|fit|set)\b/i.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    /\bfor (prototyping|production|enterprise|performance|learning|beginners|most (cases|projects|teams)|day-to-day)\b/i.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    /\b(Python|JavaScript|Java|C\+\+|Rust|Go|TypeScript|Kotlin|Ruby|Swift)\b[\s\S]{0,200}\b(Python|JavaScript|Java|C\+\+|Rust|Go|TypeScript|Kotlin|Ruby|Swift)\b/i.test(
      sample,
    )
  ) {
    return true;
  }
  return false;
}

/** Recommendations, comparisons, career/stack advice — not paste-and-send text. */
function looksLikeAdvisoryNote(content: string): boolean {
  const sample = content.slice(0, 1600).trim();
  if (hasDefiniteAdvisorySignals(sample)) return true;
  if (
    sample.length > 100 &&
    !emailDraftSignals(content) &&
    !directMessageSignals(content)
  ) {
    return true;
  }
  return false;
}

/** Regex-only — safe to call from advisory/deliverable checks (no mutual recursion). */
function emailDraftSignals(content: string): boolean {
  const sample = content.trim();
  if (/^(To:|Subject:)/im.test(sample)) return true;
  if (
    /^(Hi|Hello|Dear|Hey)\b/im.test(sample) &&
    /\b(Best|Thanks|Regards|Sincerely|Cheers),/im.test(sample)
  ) {
    return true;
  }
  if (
    /^(Hi|Hello|Dear)\b/im.test(sample) &&
    sample.split("\n").filter((l) => l.trim()).length >= 3
  ) {
    return true;
  }
  return false;
}

function looksLikeEmailDraft(content: string): boolean {
  return emailDraftSignals(content);
}

/** Regex-only — must not call looksLikeAdvisoryNote (was causing stack overflow). */
function directMessageSignals(content: string): boolean {
  const sample = content.trim();
  const words = sample.split(/\s+/).length;
  if (words > 90) return false;
  if (
    /^(please |reminder:|don'?t forget|running late|see you|thanks for|hey |hi )/i.test(
      sample,
    )
  ) {
    return true;
  }
  if (
    words <= 70 &&
    /\b(I'll|I'm|we're|you're|your|let me know)\b/i.test(sample) &&
    !/\b(is a solid|for prototyping|software engineer)\b/i.test(sample)
  ) {
    return true;
  }
  return false;
}

function looksLikeDirectMessage(content: string): boolean {
  return directMessageSignals(content);
}

/** Paste-and-send wording only — not code, notes, or assistant commentary. */
export function looksLikeSendDeliverable(content: string): boolean {
  if (looksLikeCode(content)) return false;
  if (looksLikeAssistantMeta(content)) return false;
  if (looksLikeExplanatoryProse(content)) return false;
  const sample = content.trim();
  if (/^\s*[>#]/.test(sample)) return false;
  if (/^#{1,6}\s/m.test(sample)) return false;
  return looksLikeEmailDraft(content) || looksLikeDirectMessage(content);
}

/** True when content reads like plain prose (not code). */
function looksLikeProse(content: string): boolean {
  if (looksLikeCode(content)) return false;
  const sample = content.slice(0, 600);
  if (
    /^\s*(def |function |class |import |const |let |var |SELECT |#include |package )/im.test(
      sample,
    )
  ) {
    return false;
  }
  if (/^\s*[\[{<]/m.test(sample) && /[;\}]/.test(sample)) return false;
  return true;
}

/** Assistant follow-up / disclaimer — not something the user would copy and send. */
function looksLikeAssistantMeta(content: string): boolean {
  const sample = content.slice(0, 800).trim();
  if (
    /^(I (used|assumed|went with|inferred|based|picked|chose|included)|Based on your (answer|response|input|reply)|If you('d| would) prefer|just tell me (and )?I('ll| will)|let me know if|double-check|feel free to (ask|tell)|happy to (revise|update|adjust)|I can (revise|update|adjust)|Note:|Also, (double-check|if ))/i.test(
      sample,
    )
  ) {
    return true;
  }
  if (/\bI assumed\b/i.test(sample) && /\blet me know\b/i.test(sample))
    return true;
  // Math fence validation failures — never a paste-and-send Copy template.
  if (/^(Could not render that diagram\.?|Invalid (graph|geometry) block)/i.test(sample)) {
    return true;
  }
  return false;
}

/** Definite drafting instructions/questions that must never become a draft card. */
export function looksLikeDraftInstruction(content: string): boolean {
  const sample = content.slice(0, 1200).trim();
  const compact = sample.replace(/\s+/g, " ");
  if (!compact) return true;
  if (/^fence!?\b/i.test(compact)) return true;
  if (
    /\b(?:who is this for|what(?:'s| is) the purpose|what would you like (?:it|the (?:message|email|post)) to say|paste (?:their|the) (?:phone )?number|formatted for texting)\b/i.test(
      compact,
    )
  ) {
    return true;
  }
  if (
    /^(?:i(?:'ll| will) (?:craft|draft|format)|i need (?:the |your |a )?(?:recipient|purpose|tone|details|name|email address|phone number))\b/i.test(
      compact,
    )
  ) {
    return true;
  }
  if (/\bdrop (?:those|these|that) in\b/i.test(compact) && /\bdraft\b/i.test(compact)) {
    return true;
  }
  return false;
}

/**
 * Explicit model-owned draft tags are authoritative across languages, except
 * for definite code, assistant commentary, or leaked drafting instructions.
 * Requiring English greetings/contractions made Amharic and Spanish copy fall
 * through to a syntax-highlighted CodeBlock.
 */
export function looksLikeExplicitDraftContent(content: string): boolean {
  const trimmed = content.trim();
  if (!trimmed) return false;
  if (looksLikeDraftInstruction(trimmed)) return false;
  // Explicit email/message/social tags are authoritative. Only reject meta
  // text that unmistakably refers to revising the assistant's own draft;
  // broad checks such as a leading "Let me know if..." would throw away a
  // perfectly valid message the user intends to send.
  if (
    /^(?:happy to|i can) (?:revise|update|adjust) (?:the |this |it )?(?:tone|length|draft|message|email|post)\b/i.test(
      trimmed,
    ) ||
    (/\bi assumed\b/i.test(trimmed) && /\blet me know\b/i.test(trimmed))
  ) {
    return false;
  }
  // Nested ```email / ```sms or ATX headings mean the model used a draft
  // fence as a capability example and swallowed the rest of the reply.
  if (trimmed.includes("```")) return false;
  if (/^#{1,6}\s/m.test(trimmed)) return false;
  return !looksLikeCode(trimmed);
}

export function isStructuredDraftLang(lang: string): boolean {
  return fenceSpecForLang(lang)?.draft ?? false;
}

/** Remove the literal developer term shown in the reported malformed card. */
export function draftFenceProseText(content: string): string {
  return content
    .split("\n")
    .filter((line) => !/^\s*fence!?\s*$/i.test(line))
    .join("\n")
    .trim();
}

/** Fences that should render as normal body text — not CopyBlock or CodeBlock. */
export function shouldRenderAsPlainProseFence(
  lang: string,
  content: string,
): boolean {
  const l = lang.trim().toLowerCase();
  // An explicit copy tag can contain any language. Keep genuine copy fenced;
  // unwrap only obvious assistant/meta text so it reads as normal prose.
  if (l === "copy") {
    return (
      !looksLikeExplicitDraftContent(content) || hasDefiniteAdvisorySignals(content)
    );
  }
  if (looksLikeExplanatoryProse(content)) return true;
  if (looksLikeAssistantMeta(content)) return true;
  if (looksLikeCode(content)) return false;
  if (isExplicitCodeLang(lang)) return false;
  if (isCopyLang(l) || isProseLang(lang)) {
    return looksLikeProse(content) && !looksLikeSendDeliverable(content);
  }
  return false;
}

// Characters a bare simplified algebraic expression is built from — no
// English words can survive this class alongside a digit/operator, so it's
// safe to allow letters here without a prose false-positive.
const MATH_ANSWER_CHARS_RE = /^[0-9a-zA-Z+\-*/^±√!(){}\\_.,\s]+$/;
// Two real (3+ letter) words in a row means prose, not a bare expression —
// "the answer" would otherwise slip through MATH_ANSWER_CHARS_RE above.
const TWO_WORDS_RE = /\b[a-zA-Z]{3,}\b\s+\b[a-zA-Z]{3,}\b/;

/** Short numeric / boxed math final — AnswerBlock only; not every equation. */
export function looksLikeMathAnswer(content: string): boolean {
  const sample = content.trim();
  if (!sample || sample.length > 80) return false;
  if (/\n/.test(sample)) return false;
  // A lone variable or "2 + Y" mentioned in prose is not a final-answer card.
  if (/^[A-Za-z]$/.test(sample)) return false;
  if (/^\d+\s*[+\-*/]\s*[A-Za-z]\s*$/.test(sample)) return false;
  if (/^[A-Za-z]\s*[+\-*/]\s*\d+\s*$/.test(sample)) return false;
  // Bare number, optional % / factorial: 120, 5!, -3.5
  if (/^[±+\-]?\d+(?:[.,]\d+)?(?:\s*[%])?!?$/.test(sample)) return true;
  if (/^\$[^$\n]+\$$/.test(sample)) {
    return looksLikeMathAnswer(sample.slice(1, -1));
  }
  if (/^\\boxed\{[^}]+\}$/.test(sample)) return true;
  // Short scalar assignment final: x = 2, n = 120 (not multi-step / worded).
  if (/^[a-zA-Z]\s*=\s*[±+\-]?\d+(?:[.,]\d+)?$/.test(sample)) return true;
  // Multi-value final — both roots of a quadratic, etc. The model routinely
  // emits "x = 2 or x = -2" (often with each term wrapped in $...$) as the
  // final answer. Without this it falls through every other detector (the
  // bare-expression charset below excludes `=`, and the `$` chars fail the
  // algebra-line charset) and lands on the fallback CodeBlock "copy box"
  // with raw $ signs and a Copy button — which is not how a final answer
  // should render. Strip embedded $...$ wraps first, then match 2+ solutions
  // joined by "or" / "and" / ",".
  const stripped = stripEmbeddedDollarWraps(sample);
  if (
    /^[a-zA-Z]\s*=\s*[±+\-]?\d+(?:[.,]\d+)?(?:\s*(?:or|and|,)\s*[a-zA-Z]\s*=\s*[±+\-]?\d+(?:[.,]\d+)?)+$/.test(
      stripped,
    )
  ) {
    return true;
  }
  // Bare simplified expression, no "=" — a final result like "2c^2",
  // "x^2 - 4", "\frac{1}{2}", "√2" rather than a full equation/step.
  if (
    MATH_ANSWER_CHARS_RE.test(sample) &&
    /[\d^√±\\]/.test(sample) &&
    !TWO_WORDS_RE.test(sample)
  ) {
    return true;
  }
  return false;
}

/** Explicit ```answer / ```result fences for a final numeric / math answer. */
export function isAnswerLang(lang: string): boolean {
  return fenceIdForLang(lang) === "answer";
}

/** Any non-prose fence language tag (python, js, …) → always a code block. */
export function isExplicitCodeLang(lang: string): boolean {
  const l = lang.trim().toLowerCase();
  if (!l) return false;
  // The exclusion list lives in lib/fenceRegistry.ts (`neverCodeBlock`) so it
  // cannot drift from the structured-fence list again.
  if (isNeverCodeBlockLang(l)) return false;
  return !isProseLang(l);
}

export function shouldRenderAsCopyBlock(
  lang: string,
  content: string,
): boolean {
  const l = lang.trim().toLowerCase();
  if (looksLikeCode(content)) return false;
  if (looksLikeDraftInstruction(content)) return false;
  if (looksLikeMathAnswer(content)) return false;
  if (isAnswerLang(lang)) return false;
  if (isExplicitCodeLang(lang)) return false;
  if (l === "copy") {
    return (
      looksLikeExplicitDraftContent(content) &&
      !hasDefiniteAdvisorySignals(content)
    );
  }
  if (looksLikeAssistantMeta(content)) return false;
  if (looksLikeExplanatoryProse(content)) return false;
  if (
    l === "copy" ||
    l === "text" ||
    l === "message" ||
    l === "email" ||
    l === "sms" ||
    l === "reply"
  ) {
    return looksLikeSendDeliverable(content);
  }
  return (
    isProseLang(lang) &&
    looksLikeProse(content) &&
    looksLikeSendDeliverable(content)
  );
}

/** The i18n key of a copy card's label: an email, a message, or a plain draft. */
export function copyBlockLabelKey(lang: string): string {
  switch (lang.trim().toLowerCase()) {
    case "email":
      return "rich.email_draft";
    case "sms":
    case "message":
      return "rich.message_draft";
    default:
      return "rich.copy_draft";
  }
}

/** Cleaned full message for copy. EmailCard has its own copy control. */
export function extractPrimaryCopyText(content: string): string {
  return markdownToCopyText(content);
}
