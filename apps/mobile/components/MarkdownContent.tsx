/** Markdown renderer — v2 (no nested Markdown / plainFence), theme-aware. */
import { useEffect, useMemo, useRef } from "react";
import { StyleSheet, View, type StyleProp, type TextStyle } from "react-native";

import { StreamingCursor } from "@/components/StreamingCursor";
import { compactMdStyles } from "@/components/markdown/markdownContentStyles";
import { MarkdownPiece, type MarkdownProps } from "@/components/markdown/MarkdownPiece";
import { makeRenderRules } from "@/components/markdown/markdownRenderRules";
import { ReplyStreaming } from "@/components/markdown/ReplyStreaming";
import { streamingEnd, type StreamingEnd } from "@/components/markdown/streamingEnd";
import { markdownItInstance } from "@/lib/markdown/parser";
import {
  preprocessMarkdownForStream,
  preprocessSettledMarkdown,
  type StreamingPreprocessCache,
} from "@/lib/markdown/preprocessStream";
import {
  advanceStreamBlocks,
  settleStreamBlocks,
  type StreamBlocksState,
} from "@/lib/markdown/streamBlocks";
import {
  advancePreviewFilesScan,
  type PreviewScanState,
} from "@/lib/preview/htmlPreviewBundle";
import { HtmlPreviewFilesProvider } from "@/lib/preview/htmlPreviewFiles";
import { useTheme } from "@/lib/theme";

type Props = {
  content: string;
  streaming?: boolean;
  mathFormat?: (expr: string) => string;
  /** A sent bubble: no space under the last block, so the padding is even. */
  compact?: boolean;
  /** The server presented `content` before saving it (isServerPresentedRow). */
  presented?: boolean;
};

const LEADING_HEADING = /^\s*(#{1,6})[ \t]/;

/**
 * A reply that opens with a heading should not open with that heading's top
 * margin. Read from the source, so the streaming and settled renders agree and
 * nothing jumps when the reply finishes.
 */
function leadingHeadingMargin(
  text: string,
  styles: Readonly<Record<string, StyleProp<TextStyle>>>,
): number {
  const match = LEADING_HEADING.exec(text);
  if (!match) return 0;
  const style = StyleSheet.flatten(styles[`heading${match[1].length}`]);
  return typeof style?.marginTop === "number" ? style.marginTop : 0;
}

export function MarkdownContent({
  content,
  streaming = false,
  mathFormat,
  compact = false,
  presented = false,
}: Props) {
  const t = useTheme();
  const { rules, continuedRules, mdStyles: replyStyles } = useMemo(() => makeRenderRules(t), [t]);
  const mdStyles = useMemo(
    () => (compact ? compactMdStyles(replyStyles) : replyStyles),
    [compact, replyStyles],
  );
  const md = useMemo<MarkdownProps>(
    () => ({ style: mdStyles, rules, markdownit: markdownItInstance }),
    [mdStyles, rules],
  );
  const mdContinued = useMemo<MarkdownProps>(
    () => ({ style: mdStyles, rules: continuedRules, markdownit: markdownItInstance }),
    [mdStyles, continuedRules],
  );
  // Streaming input arrives already throttled at the draft→UI boundary
  // (useStreamingDraft, ~30fps), so parse immediately — a second throttle here
  // only added latency. Settled chunks parse once ever; per flush, only the
  // live piece is re-tokenized.
  const streamPreprocessRef = useRef<StreamingPreprocessCache | null>(null);
  const streamBlocksRef = useRef<StreamBlocksState | null>(null);
  useEffect(() => {
    if (!streaming) streamPreprocessRef.current = null;
  }, [streaming]);
  const renderContent = content;
  // Incremental: streaming content grows append-only, so rescan just the new
  // suffix per flush instead of splitting/scanning the whole message.
  const previewScanRef = useRef<PreviewScanState | null>(null);
  const previewScan = advancePreviewFilesScan(previewScanRef.current, renderContent);
  previewScanRef.current = previewScan;
  const previewFiles = previewScan.files;
  const prepared = useMemo(() => {
    try {
      if (streaming) {
        const { prepared: streamed, cache } = preprocessMarkdownForStream(
          renderContent,
          streamPreprocessRef.current,
          mathFormat,
          { presented },
        );
        streamPreprocessRef.current = cache;
        return streamed;
      }
      // A reply that just finished streaming keeps the parts its stream preprocessed.
      return preprocessSettledMarkdown(renderContent, streamPreprocessRef.current, mathFormat, {
        presented,
      });
    } catch {
      return renderContent;
    }
  }, [renderContent, streaming, mathFormat, presented]);

  const leadingTop = leadingHeadingMargin(prepared, mdStyles);
  const leadingOffset = leadingTop > 0 ? { marginTop: -leadingTop } : null;

  // While the reply streams, its closed text is cut into chunks. Once it
  // settles the chunks it still starts with stay, and the rest is one piece:
  // the same pieces under the same keys, so what was drawn is not drawn again.
  const cache = streaming ? streamPreprocessRef.current : null;
  const blocks = streaming
    ? advanceStreamBlocks(streamBlocksRef.current, prepared, cache?.preparedStable.length ?? 0)
    : settleStreamBlocks(streamBlocksRef.current, prepared);
  streamBlocksRef.current = blocks;
  const settledEnd = blocks.settledText.length;
  const end: StreamingEnd = streaming
    ? streamingEnd(prepared, settledEnd, cache, md)
    : { live: prepared.slice(settledEnd), tail: null, caretAfter: false };
  const pieces: { start: number; content: string; continued: boolean }[] = [];
  let start = 0;
  blocks.chunks.forEach((chunk, index) => {
    pieces.push({ start, content: chunk, continued: blocks.continued[index] === true });
    start += chunk.length;
  });
  if (end.live) pieces.push({ start: settledEnd, content: end.live, continued: false });

  return (
    <ReplyStreaming value={streaming}>
      <HtmlPreviewFilesProvider files={previewFiles}>
        <View style={leadingOffset}>
          {pieces.map((piece) => (
            <MarkdownPiece
              key={`piece-${piece.start}`}
              content={piece.content}
              md={piece.continued ? mdContinued : md}
            />
          ))}
          {end.tail}
          {end.caretAfter ? <StreamingCursor /> : null}
        </View>
      </HtmlPreviewFilesProvider>
    </ReplyStreaming>
  );
}
