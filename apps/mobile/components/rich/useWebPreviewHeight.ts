/**
 * The height and error state of a WebView preview card (a chart, a Mermaid
 * diagram). The page posts `{ kind: "<page>-size", height }` once drawn and
 * `{ kind: "<page>-error", message }` when it cannot draw; the card follows
 * `rules` (grow-only, capped, expandable). A page that cannot draw is a refused
 * fence: Sentry hears its id and `draw_failed`, never the page's message.
 */
import { useCallback, useRef, useState } from "react";

import type { PreviewHeightRules } from "@/lib/preview/webPreviewHeight";
import { reportFenceRefused } from "@/lib/sentry";

type PreviewMessage = { kind?: string; message?: string; height?: number };

function isPreviewMessage(data: unknown, kind: string): data is PreviewMessage {
  return typeof data === "object" && data !== null && (data as { kind?: string }).kind === kind;
}

export function useWebPreviewHeight({
  rules,
  page,
  errorText,
}: {
  /** A module-level policy (`CHART_PREVIEW_HEIGHT`), so the handlers stay stable. */
  rules: PreviewHeightRules;
  /** The page's message prefix, its fence's id: `chart` reads `chart-size` and `chart-error`. */
  page: "chart" | "mermaid";
  /** Shown when the page reports an error without a message, or posts unreadable data. */
  errorText: string;
}) {
  const { policy } = rules;
  const [expanded, setExpanded] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [previewHeight, setPreviewHeight] = useState(policy.min);
  const [reportedHeight, setReportedHeight] = useState(0);
  const heightRef = useRef(policy.min);
  const expandedRef = useRef(expanded);
  expandedRef.current = expanded;

  const maxHeight = expanded ? policy.maxExpanded : policy.max;
  const height = Math.min(previewHeight, maxHeight);
  const clipped = rules.isClipped(reportedHeight, height);

  const onMessage = useCallback((event: { nativeEvent: { data?: string } }) => {
    try {
      const data: unknown = JSON.parse(event.nativeEvent.data ?? "{}");
      if (isPreviewMessage(data, `${page}-error`)) {
        setRenderError(data.message ?? errorText);
        reportFenceRefused(page, "draw_failed");
        return;
      }
      if (isPreviewMessage(data, `${page}-size`)) {
        const reported = Number(data.height);
        if (!Number.isFinite(reported) || reported <= 0) return;
        setReportedHeight(reported);
        const maxH = expandedRef.current ? policy.maxExpanded : policy.max;
        const next = rules.next(reported, heightRef.current, maxH);
        if (next == null) return;
        heightRef.current = next;
        setPreviewHeight(next);
      }
    } catch {
      setRenderError(errorText);
      reportFenceRefused(page, "draw_failed");
    }
  }, [errorText, page, policy, rules]);

  const toggleExpanded = useCallback(() => {
    setExpanded((was) => {
      const next = !was;
      const clamped = rules.toggled(reportedHeight || heightRef.current, next);
      heightRef.current = clamped;
      setPreviewHeight(clamped);
      return next;
    });
  }, [reportedHeight, rules]);

  return { expanded, height, clipped, renderError, onMessage, toggleExpanded };
}
