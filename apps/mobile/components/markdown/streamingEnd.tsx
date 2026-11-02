import React, { type ReactNode } from "react";
import { View } from "react-native";

import { CodeBlock } from "@/components/CodeBlock";
import { MarkdownPiece, type MarkdownProps } from "@/components/markdown/MarkdownPiece";
import { AnswerBlock } from "@/components/rich/AnswerBlock";
import { MathText } from "@/components/rich/MathText";
import { StreamingCursor, withStreamCaret } from "@/components/StreamingCursor";
import { draftFenceProseText } from "@/lib/copyBlock";
import { classifyOpenFencePreview, type OpenFencePreviewKind } from "@/lib/fenceDispatch";
import type { StreamingPreprocessCache } from "@/lib/markdown/preprocessStream";
import { completeStreamingLatex, prepareStreamingMathText } from "@/lib/math/streaming";
import { classifyOpenStreamTail } from "@/lib/streamingOpenFence";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";

type OpenStreamRegion = ReturnType<typeof classifyOpenStreamTail>;

/** Open $$ / \[ body — native MathText until the closer arrives (no KaTeX WebView).
 * An unfinished command stays blank. A closed prefix still draws. */
const StreamingMathPreview = React.memo(function StreamingMathPreview({
  body,
}: {
  body: string;
}) {
  const theme = useTheme();
  const drawable = completeStreamingLatex(body);
  if (!drawable) return null;
  return (
    <View style={{ marginVertical: Space.xxs }}>
      <MathText latex={drawable} textColor={theme.text} />
    </View>
  );
});

const mathTailRow = {
  flexDirection: "row" as const,
  flexWrap: "wrap" as const,
  alignItems: "flex-end" as const,
};

function acceptsStreamCaret(markdown: string): boolean {
  const body = markdown.replace(/\s+$/, "");
  return Boolean(body) && !/(?:```|~~~)\s*$/.test(body);
}

function tailPaintsBlock(kind: "fence" | "math" | "other", preview: OpenFencePreviewKind | null): boolean {
  if (kind === "math") return true;
  if (kind !== "fence" || preview == null) return false;
  return preview === "answer" || preview === "math" || preview === "code";
}

/** Open display maths, the caret after it while it is the last thing drawn. */
function mathTail(body: string, caret: boolean): ReactNode {
  return (
    <View style={mathTailRow}>
      <StreamingMathPreview body={body} />
      {caret ? <StreamingCursor /> : null}
    </View>
  );
}

/**
 * What an open fence or open display maths at the end of a streaming reply
 * shows: the fence as its preview (`classifyOpenFencePreview`), the maths
 * typeset.
 */
function openTail(
  region: OpenStreamRegion,
  preview: OpenFencePreviewKind | null,
  prose: string,
  caretOnMath: boolean,
  md: MarkdownProps,
): ReactNode {
  const proseBlock = prose.trim() ? <MarkdownPiece key="tail" content={prose} md={md} /> : null;
  if (region.kind === "math") return mathTail(region.body, caretOnMath);
  if (region.kind !== "fence") return null;
  switch (preview) {
    case "answer":
      return region.body.trim() ? <AnswerBlock content={region.body} settled={false} /> : null;
    case "math":
      return mathTail(region.body, caretOnMath);
    case "prose":
      return proseBlock;
    case "hide":
    case "placeholder":
      return null;
    default:
      return <CodeBlock code={region.body} lang={region.lang} streaming />;
  }
}

export type StreamingEnd = {
  /** The live piece: the closed text after the chunks, and prose still typing. */
  live: string;
  /** An open fence or display maths after it, as its preview. */
  tail: ReactNode;
  /** The caret is drawn on its own after everything. */
  caretAfter: boolean;
};

/**
 * The end of a streaming reply after its settled chunks. Prose still typing
 * joins the closed text before it in one piece, so it lays out as it will
 * once the reply settles: a line that closes stays where it was drawn. An open
 * fence or display maths is drawn after it, as its preview.
 */
export function streamingEnd(
  prepared: string,
  settledEnd: number,
  cache: StreamingPreprocessCache | null,
  md: MarkdownProps,
): StreamingEnd {
  // Settling only happens inside the prepared-stable prefix, whose
  // preprocessing is final; the raw remainder stays live.
  const safeLen = cache?.preparedStable.length ?? 0;
  const unsettled = prepared.slice(settledEnd, safeLen);
  const openRegion = classifyOpenStreamTail(prepared.slice(safeLen), cache?.scanState);
  if (openRegion.kind === "other") {
    const typing = prepareStreamingMathText(openRegion.text).text;
    if (typing.trim() && acceptsStreamCaret(typing)) {
      return { live: unsettled + withStreamCaret(typing), tail: null, caretAfter: false };
    }
    if (acceptsStreamCaret(unsettled)) {
      return { live: withStreamCaret(unsettled) + typing, tail: null, caretAfter: false };
    }
    return { live: unsettled + typing, tail: null, caretAfter: true };
  }
  const fencePreview =
    openRegion.kind === "fence" ? classifyOpenFencePreview(openRegion.lang, openRegion.body) : null;
  const proseTail =
    openRegion.kind === "fence" && fencePreview === "prose" ? draftFenceProseText(openRegion.body) : "";
  let caretHost: "prose" | "unsettled" | "after" = "after";
  if (proseTail.trim() && acceptsStreamCaret(proseTail)) caretHost = "prose";
  else if (!tailPaintsBlock(openRegion.kind, fencePreview) && acceptsStreamCaret(unsettled)) {
    caretHost = "unsettled";
  }
  const caretOnMath =
    caretHost === "after" && (openRegion.kind === "math" || fencePreview === "math");
  const proseShown = caretHost === "prose" ? withStreamCaret(proseTail) : proseTail;
  return {
    live: caretHost === "unsettled" ? withStreamCaret(unsettled) : unsettled,
    tail: openTail(openRegion, fencePreview, proseShown, caretOnMath, md),
    caretAfter: caretHost === "after" && !caretOnMath,
  };
}
