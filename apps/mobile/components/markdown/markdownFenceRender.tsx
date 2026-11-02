import { isValidElement, type ReactNode } from "react";
import { Text } from "react-native";

import { CodeBlock } from "@/components/CodeBlock";
import { CopyBlock } from "@/components/CopyBlock";
import { AnswerBlock } from "@/components/rich/AnswerBlock";
import {
  LazyCircularClockBlock,
  LazyWebPreviewCodeBlock,
} from "@/components/rich/LazyHeavyRich";
import { MathBlock } from "@/components/rich/MathView";
import {
  mathFenceKey,
  renderCopyStyleBlock,
  renderRichFenceById,
} from "@/components/rich/RichFence";
import { copyBlockLabelKey, draftFenceProseText } from "@/lib/copyBlock";
import i18n from "@/lib/i18n";
import { parseFenceLang } from "@/lib/codeHighlight";
import { fenceIdForLang, isNeverCodeBlockLang } from "@/lib/fenceRegistry";
import {
  classifyFence,
  looksLikeMathMeta,
  shouldHideCopyOnCodeFallback,
} from "@/lib/fenceDispatch";
import { fenceReportName, refusalOf, type FenceReportName } from "@/lib/fenceReports";
import { reportFenceCrash, reportFenceRefused } from "@/lib/sentry";
import { FenceErrorBoundary } from "@/components/markdown/FenceErrorBoundary";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";
import { useReplyStreaming } from "@/components/markdown/ReplyStreaming";
import { useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

// `tokenIndex` (and `index`) come from react-native-markdown-display's AST
// (tokensToAST.js) — unlike `key` (a never-reset getUniqueID counter that
// changes every re-parse), they are stable across re-parses for an
// already-emitted fence. Optional because tests/fakes construct FenceNodes
// directly without them.
export type FenceNode = {
  key: string;
  content: string;
  // react-native-markdown-display's AST (tokensToAST.js) exposes the fence's
  // language tag as `sourceInfo`, not `info` — reading `.info` here silently
  // returned undefined for every fence, dropping the model's explicit
  // ```answer / ```math / ```geometry / code-language tags before any of the
  // lang-based routing below ever saw them.
  sourceInfo?: string;
  tokenIndex?: number;
  index?: number;
};

/** Prose from a draft fence, drawn like a reply paragraph (it had no color, so black in dark mode). */
function NeverCodeBlockFallback({ content }: { content: string }) {
  const t = useTheme();
  return (
    <Text selectable style={[Type.body, { color: t.assistantText, marginBottom: PARAGRAPH_GAP }]}>
      {content}
    </Text>
  );
}

function neverCodeBlockFallback(key: string, content: string) {
  return <NeverCodeBlockFallback key={key} content={content} />;
}

/** A streaming reply is not yet the server's final text: its answer has no check until it settles. */
function FenceAnswerBlock({ content }: { content: string }) {
  const streaming = useReplyStreaming();
  return <AnswerBlock content={content} settled={!streaming} />;
}

function renderFenceInner(
  key: string,
  lang: string,
  content: string,
  decision: ReturnType<typeof classifyFence>,
  tokenIndex?: number,
) {
  if (decision.kind === "hide") return null;

  if (decision.kind === "html") {
    return <LazyWebPreviewCodeBlock key={key} code={content} lang={lang || "html"} />;
  }

  if (decision.kind === "answer") {
    return <FenceAnswerBlock key={key} content={content} />;
  }

  if (decision.kind === "math") {
    return <MathBlock key={mathFenceKey(content, tokenIndex)} latex={content} />;
  }

  if (decision.kind === "clock") {
    return <LazyCircularClockBlock key={key} content={content} />;
  }

  if (decision.kind === "prose") {
    const prose = draftFenceProseText(content);
    return prose ? neverCodeBlockFallback(key, prose) : null;
  }

  if (decision.kind === "rich" && decision.id) {
    const rich = renderRichFenceById(decision.id, lang, content, key, tokenIndex);
    if (rich) return rich;
    // Its body did not read (an empty list, no quote): the text shows instead.
    reportFenceRefused(decision.id, refusalOf(content));
    if (isNeverCodeBlockLang(lang)) return neverCodeBlockFallback(key, content);
  }

  const copyStyle = renderCopyStyleBlock(lang, content, key, tokenIndex);
  if (copyStyle) return copyStyle;

  if (decision.kind === "copy") {
    const styled = renderCopyStyleBlock("copy", content, key, tokenIndex);
    if (styled) return styled;
    return <CopyBlock key={key} text={content} labelKey={copyBlockLabelKey(lang)} />;
  }

  if (isNeverCodeBlockLang(lang)) return neverCodeBlockFallback(key, content);

  return (
    <CodeBlock
      key={key}
      code={content}
      lang={lang}
      showCopy={!shouldHideCopyOnCodeFallback(lang, content)}
    />
  );
}

/** What a fence was last drawn from, and what it drew. */
type DrawnFence = {
  info: string | undefined;
  content: string;
  tokenIndex: number | undefined;
  language: string;
  element: ReactNode;
};

/**
 * The fence render rule for one reply (the markdown library passes more
 * arguments). A streaming reply's live piece parses again on every flush, so a
 * closed fence in it (a graph, a code card, an answer, while the text after it
 * streams) went through its block again each time. A fence whose node, info,
 * body and token are as they were last time hands back the element it drew
 * then, and React leaves that block as it is; what the block reads from
 * context (the reply settling, its preview files) still reaches it.
 */
export function makeFenceRule(): (node: FenceNode) => ReactNode {
  const drawn = new Map<string, DrawnFence>();
  return (node) => {
    const last = drawn.get(node.key);
    if (
      last &&
      last.info === node.sourceInfo &&
      last.content === node.content &&
      last.tokenIndex === node.tokenIndex &&
      last.language === i18n.language
    ) {
      return last.element;
    }
    const element = renderFence(node);
    drawn.set(node.key, {
      info: node.sourceInfo,
      content: node.content,
      tokenIndex: node.tokenIndex,
      language: i18n.language,
      element,
    });
    return element;
  };
}

export function renderFence(node: FenceNode) {
  const lang = parseFenceLang(node.sourceInfo?.trim() || "");
  const content = node.content.replace(/\n$/, "").trim();
  if (!content) return null;

  // Named by its registry id, or the block dispatch drew it as: never the tag the reply wrote.
  let fence: FenceReportName = fenceIdForLang(lang) ?? "code";
  let element: ReactNode;
  try {
    const decision = classifyFence(lang, content);
    fence = fenceReportName(decision);
    element = renderFenceInner(node.key, lang, content, decision, node.tokenIndex);
  } catch (error) {
    if (__DEV__) {
      console.warn("[MarkdownContent] fence render failed", error);
    }
    reportFenceCrash(fence, error);
    if (isNeverCodeBlockLang(lang)) {
      return neverCodeBlockFallback(node.key, content);
    }
    return (
      <CodeBlock
        key={node.key}
        code={content}
        lang={lang}
        showCopy={!shouldHideCopyOnCodeFallback(lang, content) && !looksLikeMathMeta(content)}
      />
    );
  }
  if (!isValidElement(element)) return element;
  // A block that throws while it draws falls back alone; the reply around it
  // still renders. The boundary takes the block's key, so it mounts when the
  // block did (a maths block under its source, an email card under its token).
  return (
    <FenceErrorBoundary key={element.key ?? node.key} lang={lang} content={content} fence={fence}>
      {element}
    </FenceErrorBoundary>
  );
}
