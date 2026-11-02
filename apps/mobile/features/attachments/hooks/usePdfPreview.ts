import { useEffect, useMemo, useState } from "react";
import { EncodingType, getInfoAsync, readAsStringAsync } from "expo-file-system/legacy";

import { useAccountSession } from "@/contexts/accountSession";
import { MAX_ATTACHMENT_BYTES } from "@/features/attachments/model/attachmentLimits";
import { ensureLocalAttachmentFile } from "@/features/attachments/model/downloadChatAttachment";
import {
  buildPdfPreviewHtml,
  PDF_LIBRARIES,
  pdfPreviewColors,
  type PdfSources,
} from "@/features/attachments/model/pdfPreviewHtml";
import { useTheme } from "@/lib/theme";
import { readVendorLibraries } from "@/lib/vendorAssets";
import { allowPdfPageNavigation, PDF_PAGE_ORIGIN_WHITELIST } from "@/lib/webView";

type Loaded = { uri: string; base64: string; sources: PdfSources };

type PdfPreview =
  | { status: "idle" | "loading" | "failed" }
  | { status: "ready"; webViewKey: string; webViewProps: Record<string, unknown> };

/**
 * One PDF preview for the card (page 1) and the viewer (every page). The PDF
 * is downloaded natively into the attachment cache, shared with Share and with
 * other previews of the same file, and the download stops when the preview
 * closes. The WebView gets one page holding pdf.js and the PDF itself
 * (`source: { html }`): a PDF is untrusted content, so its page reads no file
 * and has no file access on either platform.
 */
export function usePdfPreview(options: {
  uri: string | null;
  fileName: string;
  enabled: boolean;
  allPages: boolean;
}): PdfPreview {
  const { uri, fileName, enabled, allPages } = options;
  const { account, getToken } = useAccountSession();
  const theme = useTheme();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failedUri, setFailedUri] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !uri) return;
    const controller = new AbortController();
    setFailedUri(null);
    void (async () => {
      try {
        const pdf = await ensureLocalAttachmentFile({ uri, token: getToken(), fileName, signal: controller.signal });
        // The page holds the whole file, as base64, in memory: no preview past the upload cap.
        const info = await getInfoAsync(pdf);
        if (info.exists && info.size > MAX_ATTACHMENT_BYTES) throw new Error("PDF too large to preview");
        const [base64, sources] = await Promise.all([
          readAsStringAsync(pdf, { encoding: EncodingType.Base64 }),
          readVendorLibraries(PDF_LIBRARIES),
        ]);
        if (!controller.signal.aborted) setLoaded({ uri, base64, sources });
      } catch {
        if (!controller.signal.aborted) setFailedUri(uri);
      }
    })();
    return () => {
      controller.abort();
      // A closed preview lets go of its copy of the PDF.
      setLoaded(null);
    };
  }, [enabled, uri, account, getToken, fileName]);

  const current = loaded?.uri === uri ? loaded : null;
  const colors = pdfPreviewColors(theme);
  const colorKey = `${colors.bg}|${colors.text}|${colors.danger}`;
  const html = useMemo(() => {
    if (!current) return null;
    try {
      return buildPdfPreviewHtml(current.base64, theme, allPages, current.sources);
    } catch {
      return null;
    }
  }, [current, allPages, theme]);

  if (!enabled || !uri) return { status: "idle" };
  if (failedUri === uri && !current) return { status: "failed" };
  if (!current) return { status: "loading" };
  if (html === null) return { status: "failed" };
  return {
    status: "ready",
    webViewKey: `${uri}|${colorKey}`,
    webViewProps: {
      // No allowFileAccess (react-native-webview leaves it off on Android), no
      // allowingReadAccessToURL (iOS loads the string with no file read access).
      source: { html },
      // Every navigation asks the guard, which keeps the page where it is and opens nothing.
      originWhitelist: PDF_PAGE_ORIGIN_WHITELIST,
      onShouldStartLoadWithRequest: allowPdfPageNavigation,
      // Android: window.open would load in a window the guard never sees.
      setSupportMultipleWindows: false,
      // iOS: a long press would preview, so load, a link.
      allowsLinkPreview: false,
    },
  };
}
