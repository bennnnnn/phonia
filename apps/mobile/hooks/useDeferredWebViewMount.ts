import { useCallback, useEffect, useRef, useState } from "react";

import {
  isMountGranted,
  releaseMountTicket,
  requestMountTicket,
  subscribeMountQueue,
  type MountTicket,
} from "@/lib/webViewMountQueue";

// Safety net: if a granted WebView never reports load completion (e.g. a
// CDN request hangs on a bad connection), release its slot anyway after
// this long so one stuck block can't stall every other queued block
// app-wide. Comfortably longer than any real chart/mermaid/math load.
const SAFETY_RELEASE_MS = 6000;

type DeferredWebViewMount = {
  /** Render the WebView once true; render the existing fallback/placeholder until then. */
  canMount: boolean;
  /**
   * Call from the WebView's onLoad/onLoadEnd handler once content has
   * finished loading. Frees this block's queue slot for the next waiting
   * block *without* unmounting the already-loaded WebView — `canMount`
   * stays true for the remainder of this component's lifetime. Idempotent.
   */
  onLoaded: () => void;
};

/**
 * React wiring for lib/webViewMountQueue.ts: gates WebView mounts for a
 * single rich block (chart, mermaid diagram, heavy math) so that several
 * such blocks within one message don't all mount — and start fetching
 * CDN JS — in the same frame.
 *
 * Pass `active=false` when this block isn't going to mount a WebView at all
 * (e.g. the native module isn't linked) so it never occupies a slot.
 */
export function useDeferredWebViewMount(active: boolean): DeferredWebViewMount {
  const ticketRef = useRef<MountTicket | null>(null);
  const releasedRef = useRef(false);
  const [canMount, setCanMount] = useState(false);

  useEffect(() => {
    releasedRef.current = false;

    if (!active) {
      ticketRef.current = null;
      setCanMount(false);
      return;
    }

    const ticket = requestMountTicket();
    ticketRef.current = ticket;
    setCanMount(isMountGranted(ticket));

    const unsubscribe = subscribeMountQueue(() => {
      // Once loaded we intentionally stop tracking queue churn — the slot
      // was already released and this WebView must stay mounted.
      if (releasedRef.current) return;
      setCanMount(isMountGranted(ticket));
    });

    return () => {
      unsubscribe();
      if (!releasedRef.current) {
        releaseMountTicket(ticket);
      }
      ticketRef.current = null;
    };
  }, [active]);

  const onLoaded = useCallback(() => {
    if (releasedRef.current || ticketRef.current == null) return;
    releasedRef.current = true;
    releaseMountTicket(ticketRef.current);
  }, []);

  // Safety net so a WebView that never fires onLoad/onLoadEnd (e.g. a CDN
  // request that hangs) can't permanently occupy a slot and starve every
  // other queued rich block.
  useEffect(() => {
    if (!canMount) return;
    const id = setTimeout(onLoaded, SAFETY_RELEASE_MS);
    return () => clearTimeout(id);
  }, [canMount, onLoaded]);

  return { canMount, onLoaded };
}
