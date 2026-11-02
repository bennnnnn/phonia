import { useCallback, useMemo, useState } from "react";

import {
  computeChatHeaderMinimumHeight,
  computeChatLayoutMetrics,
} from "@/features/chat/model/composerLogic";

type Options = {
  insetsTop: number;
  insetsBottom: number;
  windowHeight: number;
  fontScale: number;
  keyboardHeight: number;
  composerHeight: number;
  attachmentExtra: number;
  mathBarExtra?: number;
  messagesLength: number;
  streaming: boolean;
  lastMessageId?: string;
};

export function useChatLayoutMetrics(options: Options) {
  const [measuredHeaderHeight, setMeasuredHeaderHeight] = useState<number>();
  const minimumHeaderHeight = computeChatHeaderMinimumHeight(
    options.insetsTop,
    options.fontScale,
  );
  const onHeaderHeightChange = useCallback(
    (height: number) => {
      const next = Math.max(minimumHeaderHeight, Math.ceil(height));
      setMeasuredHeaderHeight((previous) => {
        const current = Math.max(minimumHeaderHeight, previous ?? 0);
        return current === next ? previous : next;
      });
    },
    [minimumHeaderHeight],
  );
  const metrics = useMemo(
    () => computeChatLayoutMetrics({ ...options, measuredHeaderHeight }),
    [
      options.insetsTop,
      options.insetsBottom,
      options.windowHeight,
      options.fontScale,
      options.keyboardHeight,
      options.composerHeight,
      options.attachmentExtra,
      options.mathBarExtra,
      options.messagesLength,
      options.streaming,
      options.lastMessageId,
      measuredHeaderHeight,
    ],
  );
  return useMemo(
    () => ({ ...metrics, onHeaderHeightChange }),
    [metrics, onHeaderHeightChange],
  );
}
