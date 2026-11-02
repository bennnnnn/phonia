import { getApiUrl } from "@/lib/config";

/** Only the configured API origin and base path may receive Recall credentials. */
export function recallAttachmentPath(uri: string): string | null {
  try {
    const base = new URL(`${getApiUrl().replace(/\/+$/, "")}/`);
    const url = new URL(uri);
    const basePath = base.pathname.replace(/\/$/, "");
    if (url.origin !== base.origin || url.username || url.password ||
      !url.pathname.startsWith(`${basePath}/attachments/`)) return null;
    return `${url.pathname.slice(basePath.length)}${url.search}`;
  } catch {
    return null;
  }
}

export function attachmentRequestHeaders(uri: string, token: string | null): Record<string, string> {
  return token && recallAttachmentPath(uri) ? { Authorization: `Bearer ${token}` } : {};
}

/** The API serves thumbnails up to this width (`?w=`); a larger value is rejected with 422. */
export const MAX_ATTACHMENT_THUMB_WIDTH = 512;

/** A thumbnail width the API accepts: whole pixels from 1 to MAX_ATTACHMENT_THUMB_WIDTH. */
export function attachmentThumbWidth(width: number): number {
  return Math.min(MAX_ATTACHMENT_THUMB_WIDTH, Math.max(1, Math.round(width)));
}

export function resolveAttachmentUri(options: {
  attachmentId?: string | null;
  localUri?: string | null;
  path?: string | null;
  width?: number | null;
}): string | null {
  if (options.localUri) return options.localUri;
  let uri: string | null = null;
  if (options.attachmentId) {
    uri = `${getApiUrl().replace(/\/+$/, "")}/attachments/${options.attachmentId}/file`;
  } else {
    const path = options.path?.trim();
    if (!path) return null;
    // Plain http only for the API itself (a dev server); never a third party.
    if (path.startsWith("https://") || (path.startsWith("http://") && recallAttachmentPath(path))) {
      uri = path;
    } else if (path.startsWith("/attachments/")) {
      uri = `${getApiUrl().replace(/\/+$/, "")}${path}`;
    }
  }
  if (!uri) return null;
  const width = options.width;
  if (width && Number.isFinite(width) && width > 0 && recallAttachmentPath(uri)) {
    const url = new URL(uri);
    url.searchParams.set("w", String(attachmentThumbWidth(width)));
    return url.toString();
  }
  return uri;
}
