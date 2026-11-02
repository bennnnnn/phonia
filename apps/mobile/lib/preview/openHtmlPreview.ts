import {
  cacheDirectory,
  writeAsStringAsync,
  EncodingType,
} from "expo-file-system/legacy";
import * as WebBrowser from "expo-web-browser";
import { Linking, Platform, Share } from "react-native";
import { newAccountFile } from "@/lib/accountFiles";
import { stripScripts } from "@/lib/preview/htmlScriptStrip";
import { HTML_EXPORT_CSP, cspMetaTag, injectAtHeadStart } from "@/lib/preview/previewSandbox";
import type { Theme } from "@/lib/theme";
import { CODE_FONT } from "@/lib/fonts";

/**
 * Wrap bare HTML into a full document.
 *
 * `theme` threads app palette tokens into the document so the in-app Run tab
 * matches the active color scheme (dark mode no longer renders a white sheet).
 * Omit `theme` for the system-browser export path, which keeps light-only
 * defaults and lets the browser chrome control its own scheme. A document that
 * already has its own `<!DOCTYPE>`/`<html>` shell is returned unchanged — its
 * embedded styles are the author's choice, not ours to rewrite.
 */
export function wrapFullDocument(html: string, theme?: Theme): string {
  if (/^\s*<!DOCTYPE/i.test(html) || /^\s*<html/i.test(html)) {
    return html;
  }
  const bg = theme?.bg ?? "#FFFFFF";
  const text = theme?.text ?? "#111827";
  const border = theme?.border ?? "#E5E7EB";
  const thBg = theme?.surface ?? "#F1F5F9";
  const preBg = theme?.codeBg ?? "#F1F5F9";
  const codeFont = `'${CODE_FONT}', monospace`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 16px; line-height: 1.5; color: ${text}; background: ${bg}; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0; }
  td, th { border: 1px solid ${border}; padding: 8px; }
  th { background: ${thBg}; font-weight: 600; }
  pre { background: ${preBg}; padding: 12px; border-radius: 8px; overflow-x: auto; }
  code { font-family: ${codeFont}; font-size: 14px; font-variant-ligatures: none; }
  img { max-width: 100%; }
</style>
</head>
<body>
${html}
</body>
</html>`;
}

export function looksLikeInteractiveHtml(html: string): boolean {
  return /<\s*script\b/i.test(html);
}

/**
 * Starts the file. A file has no transport charset, so without it a browser
 * would decode the page by its own `<meta charset>`: ISO-2022-JP drops "ESC ( B"
 * and joins `http-equ` and `iv` into a pragma that disarming, which reads the
 * JS string, never saw. A byte-order mark settles the encoding before any meta.
 */
const UTF8_BOM = "\uFEFF";

/** First in the export, ahead of its CSP and the page: a second guard on the charset. */
const EXPORT_CHARSET_META = '<meta charset="utf-8">';

async function writeHtmlPreviewFile(html: string): Promise<string | null> {
  const dir = cacheDirectory;
  if (!dir) return null;

  const fileUri = newAccountFile("htmlPreview", "html");
  try {
    await writeAsStringAsync(fileUri, UTF8_BOM + html, {
      encoding: EncodingType.UTF8,
    });
    return fileUri;
  } catch {
    return null;
  }
}

/**
 * The document "Open in browser" and Share hand over: a static view of the
 * reply's HTML. The system browser (or whatever app opens the shared file) runs
 * `<script>` with no sandbox of ours, so model-generated JS is stripped, and the
 * document starts with a utf-8 charset and {@link HTML_EXPORT_CSP}, which
 * refuses every script even where the strip misses one. Interactive previews
 * run in the in-app WebView (CSP-sandboxed) instead.
 */
function htmlExportDocument(html: string): string {
  return injectAtHeadStart(
    wrapFullDocument(stripScripts(html)),
    EXPORT_CHARSET_META + cspMetaTag(HTML_EXPORT_CSP),
  );
}

/** Open rendered HTML in the system browser (works in Expo Go); static view only. */
export async function openHtmlInBrowser(html: string): Promise<boolean> {
  const fullHtml = htmlExportDocument(html);

  if (fullHtml.length < 120_000) {
    const dataUrl = `data:text/html;charset=utf-8,${encodeURIComponent(fullHtml)}`;
    try {
      await Linking.openURL(dataUrl);
      return true;
    } catch {
      try {
        await WebBrowser.openBrowserAsync(dataUrl);
        return true;
      } catch {
        /* fall through */
      }
    }
  }

  const fileUri = await writeHtmlPreviewFile(fullHtml);
  if (!fileUri) return false;

  try {
    await Linking.openURL(fileUri);
    return true;
  } catch {
    /* fall through */
  }

  try {
    await WebBrowser.openBrowserAsync(fileUri);
    return true;
  } catch {
    /* try next */
  }

  if (Platform.OS === "ios" || Platform.OS === "android") {
    try {
      await Share.share(
        Platform.OS === "ios"
          ? { url: fileUri, title: "HTML Preview" }
          : { message: fileUri, title: "HTML Preview" },
      );
      return true;
    } catch {
      return false;
    }
  }

  return false;
}

/** Share rendered HTML via the system share sheet; static view only. */
export async function shareHtmlPreview(html: string): Promise<boolean> {
  const fullHtml = htmlExportDocument(html);
  const fileUri = await writeHtmlPreviewFile(fullHtml);

  if (fileUri) {
    try {
      await Share.share(
        Platform.OS === "ios"
          ? { url: fileUri, title: "HTML Preview" }
          : { message: fileUri, title: "HTML Preview" },
      );
      return true;
    } catch {
      /* fall through */
    }
  }

  if (fullHtml.length < 120_000) {
    try {
      await Share.share({ message: fullHtml, title: "HTML Preview" });
      return true;
    } catch {
      return false;
    }
  }

  return false;
}
