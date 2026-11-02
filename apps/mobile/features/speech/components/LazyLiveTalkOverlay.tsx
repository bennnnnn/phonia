/**
 * The Live Talk overlay and its animated orb load the first time Live Talk
 * opens, not with the chat screen. After that the overlay stays mounted, so it
 * plays its own exit and draws nothing while closed, as it always did.
 */
import { lazy, Suspense, useEffect, useState, type ComponentProps } from "react";

import type { LiveTalkOverlay } from "@/features/speech/components/LiveTalkOverlay";

type Props = ComponentProps<typeof LiveTalkOverlay>;

const LiveTalkOverlayLazy = lazy(() =>
  import("@/features/speech/components/LiveTalkOverlay").then((m) => ({ default: m.LiveTalkOverlay })),
);

/**
 * The overlay animates in when `visible` turns true. Mounted already open it
 * would pop in, so the loaded overlay mounts closed for one commit and opens
 * then, the first time as on every later open.
 */
function EnteringOverlay(props: Props) {
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    setEntered(true);
  }, []);
  return <LiveTalkOverlayLazy {...props} visible={entered && props.visible} />;
}

export function LazyLiveTalkOverlay(props: Props) {
  const [opened, setOpened] = useState(props.visible);
  if (props.visible && !opened) setOpened(true);
  if (!opened) return null;
  return (
    <Suspense fallback={null}>
      <EnteringOverlay {...props} />
    </Suspense>
  );
}
