import { createContext, useContext, useMemo, type ReactNode } from "react";

import { linkPreviewKey, previewableUrls } from "@/lib/linkPreviewTrust";

const NO_PREVIEWS: ReadonlySet<string> = new Set();
const PreviewableUrls = createContext<ReadonlySet<string>>(NO_PREVIEWS);

type Props = {
  /** The user's own words: the user message itself, or the one a reply answers. */
  userText: string | null | undefined;
  /** The server's search sources for a reply. */
  sources?: readonly { url: string }[];
  children: ReactNode;
};

/**
 * Lets link cards under it fetch a preview for the links the user wrote or the
 * server's search returned (`lib/linkPreviewTrust.ts`). Outside it, none fetch.
 */
export function LinkPreviewTrust({ userText, sources, children }: Props) {
  const urls = useMemo(() => previewableUrls([userText], sources), [userText, sources]);
  return <PreviewableUrls.Provider value={urls}>{children}</PreviewableUrls.Provider>;
}

/** True when the card may ask the server to fetch this link's preview. */
export function useLinkPreviewAllowed(url: string): boolean {
  const urls = useContext(PreviewableUrls);
  const key = linkPreviewKey(url);
  return key !== null && urls.has(key);
}
