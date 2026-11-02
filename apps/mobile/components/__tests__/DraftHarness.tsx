import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

import {
  ComposerDraftProvider,
  useComposerDraftApi,
  useComposerDraftValueOptional,
} from "@/features/chat/context/ComposerDraftContext";

/** Puts the starting draft in place before the composer mounts; a new `input` replaces it. */
function Seed({ input, children }: { input: string; children: ReactNode }) {
  const { setInput } = useComposerDraftApi();
  const [ready, setReady] = useState(false);
  useLayoutEffect(() => {
    setInput(input);
    setReady(true);
  }, [input, setInput]);
  return ready ? children : null;
}

function Watch({ onInput }: { onInput: (text: string) => void }) {
  const input = useComposerDraftValueOptional()?.input ?? "";
  const last = useRef(input);
  useLayoutEffect(() => {
    if (input === last.current) return;
    last.current = input;
    onInput(input);
  }, [input, onInput]);
  return null;
}

/**
 * The composer's draft as the chat screen owns it: a ComposerDraftProvider that
 * starts from `input` and reports every change the composer makes to it.
 */
export function DraftHarness({
  input = "",
  onInput,
  children,
}: {
  input?: string;
  onInput?: (text: string) => void;
  children: ReactNode;
}) {
  return (
    <ComposerDraftProvider>
      <Seed input={input}>
        {onInput ? <Watch onInput={onInput} /> : null}
        {children}
      </Seed>
    </ComposerDraftProvider>
  );
}
