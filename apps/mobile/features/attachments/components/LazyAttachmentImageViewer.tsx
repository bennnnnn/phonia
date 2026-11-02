/**
 * The full-screen photo viewer (pager, zoom, Download and Share, and the media
 * library behind them) loads the first time a photo in a chat is opened, not
 * with the chat screen. Once open it stays mounted, as the eager viewer always
 * was, so closing still fades it out.
 */
import type { ComponentProps } from "react";

import type { AttachmentImageViewer } from "@/features/attachments/components/AttachmentImageViewer";
import { lazyOverlay } from "@/ui/overlay/lazyOverlay";

export const LazyAttachmentImageViewer = lazyOverlay<ComponentProps<typeof AttachmentImageViewer>>(
  () =>
    import("@/features/attachments/components/AttachmentImageViewer").then((m) => ({
      default: m.AttachmentImageViewer,
    })),
);
