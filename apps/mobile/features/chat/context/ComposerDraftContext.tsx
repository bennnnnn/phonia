import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type ReactNode,
  type SetStateAction,
} from "react";

import { subscribeComposerDraftReset } from "@/features/chat/model/composerDraftReset";
import { isSendEcho, type ClearedText } from "@/features/chat/model/composerSendEcho";
import {
  COMPOSER_NEW_THREAD_KEY,
  adoptNewComposerThread,
  clearAllComposerDrafts,
  stashFailedSendDraft,
  takeThreadDraft,
} from "@/features/chat/model/composerThreadDraft";
import { useLatestRef } from "@/lib/latestRef";

type ComposerDraftApi = {
  setInput: Dispatch<SetStateAction<string>>;
  /** What the user typed; a cleared message autocorrect gives back is dropped. */
  typeInput: (text: string) => void;
  inputRef: MutableRefObject<string>;
  switchThread: (nextKey: string) => void;
  adoptComposerThread: (nextKey: string) => void;
  stashFailedDraftForThread: (key: string, failedText: string) => void;
  resetForNewSession: () => void;
  getThreadKey: () => string;
};

type ComposerDraftValue = {
  input: string;
  /** Changes only when another draft/session becomes active, not on typing. */
  revision: number;
};

const ComposerDraftApiContext = createContext<ComposerDraftApi | null>(null);
const ComposerDraftValueContext = createContext<ComposerDraftValue | null>(null);
const ComposerDraftActivityContext = createContext(false);

/** Owns composer text so keystrokes do not re-render ChatScreen / the message list. */
export function ComposerDraftProvider({ children }: { children: ReactNode }) {
  const [input, setInputState] = useState("");
  const [revision, setRevision] = useState(0);
  const inputRef = useLatestRef(input);
  const clearedRef = useRef<ClearedText | null>(null);
  // A clear remembers what it cleared, so the keyboard's late correction of it is dropped.
  const setInput = useCallback<Dispatch<SetStateAction<string>>>(
    (next) => {
      if (next === "" && inputRef.current) clearedRef.current = { text: inputRef.current, at: Date.now() };
      setInputState(next);
    },
    [inputRef],
  );
  const typeInput = useCallback(
    (text: string) => {
      if (isSendEcho(clearedRef.current, text, Date.now())) return;
      clearedRef.current = null;
      setInputState(text);
    },
    [],
  );
  const draftsRef = useRef(new Map<string, string>());
  const threadKeyRef = useRef(COMPOSER_NEW_THREAD_KEY);

  const resetForNewSession = useCallback(() => {
    clearAllComposerDrafts(draftsRef.current);
    threadKeyRef.current = COMPOSER_NEW_THREAD_KEY;
    // switchThread may run in the same tick (useChatSend on session change).
    // setInput("") does not update this ref until the next render.
    inputRef.current = "";
    setInput("");
    setRevision((value) => value + 1);
  }, [inputRef, setInput]);

  useEffect(() => subscribeComposerDraftReset(resetForNewSession), [resetForNewSession]);

  const api = useMemo<ComposerDraftApi>(
    () => ({
      setInput,
      typeInput,
      inputRef,
      switchThread: (nextKey: string) => {
        const fromKey = threadKeyRef.current;
        const nextText = takeThreadDraft(
          draftsRef.current,
          fromKey,
          nextKey,
          inputRef.current,
        );
        if (fromKey === nextKey) return;
        threadKeyRef.current = nextKey;
        setInput(nextText);
        setRevision((value) => value + 1);
      },
      adoptComposerThread: (nextKey: string) => {
        threadKeyRef.current = adoptNewComposerThread(
          draftsRef.current,
          threadKeyRef.current,
          nextKey,
          inputRef.current,
        );
      },
      stashFailedDraftForThread: (key: string, failedText: string) => {
        if (threadKeyRef.current === key) return;
        stashFailedSendDraft(draftsRef.current, key, failedText);
      },
      resetForNewSession,
      getThreadKey: () => threadKeyRef.current,
    }),
    [resetForNewSession, inputRef, setInput, typeInput],
  );
  const value = useMemo<ComposerDraftValue>(() => ({ input, revision }), [input, revision]);
  const hasContent = input.length > 0;

  return (
    <ComposerDraftApiContext.Provider value={api}>
      <ComposerDraftActivityContext.Provider value={hasContent}>
        <ComposerDraftValueContext.Provider value={value}>{children}</ComposerDraftValueContext.Provider>
      </ComposerDraftActivityContext.Provider>
    </ComposerDraftApiContext.Provider>
  );
}

/** Stable setters/refs — safe in ChatScreen and useChatSend. */
export function useComposerDraftApi(): ComposerDraftApi {
  const ctx = useContext(ComposerDraftApiContext);
  if (!ctx) {
    throw new Error("useComposerDraftApi must be used within ComposerDraftProvider");
  }
  return ctx;
}

export function useComposerDraftApiOptional(): ComposerDraftApi | null {
  return useContext(ComposerDraftApiContext);
}

/** Live draft text — only ChatComposer (or tests) should subscribe. */
export function useComposerDraftValueOptional(): ComposerDraftValue | null {
  return useContext(ComposerDraftValueContext);
}

/** Changes only when the composer moves between empty and non-empty. */
export function useComposerDraftActivity(): boolean {
  return useContext(ComposerDraftActivityContext);
}
