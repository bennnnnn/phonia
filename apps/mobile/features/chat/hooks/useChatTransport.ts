import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { AppState } from "react-native";
import NetInfo, { type NetInfoState } from "@react-native-community/netinfo";

import { useAccountSession } from "@/contexts/accountSession";
import { chatWebSocketUrl } from "@/lib/api";
import { accessTokenNeedsRefresh, freshAccessToken } from "@/lib/api/client";
import type { ClientGeo } from "@/features/chat/model/clientGeo";
import { getDeviceTimezone } from "@/lib/deviceTimezone";
import { isNetworkOffline, isNetworkPathChange } from "@/lib/networkStatus";
import { shouldAbortPriorSse, streamChatMessageSse, streamChatRegenerateSse, type ChatSsePayload } from "@/features/chat/model/sse";
import { createWsBackoff } from "@/features/chat/model/wsBackoff";
import { EAGER_CONNECT_DEBOUNCE_MS } from "@/features/chat/model/wsConnect";
import { ChatWsTransport, type ChatWsFallbackSignal } from "@/features/chat/model/wsTransport";
import { useLatestRef } from "@/lib/latestRef";

type SendSseOptions = {
  attachmentIds?: string[];
  model?: string | null;
  clientGeo?: ClientGeo | null;
  ttftTurnId?: string | null;
  /** The message's name from its socket send, so a replay of it runs once. */
  clientMessageId?: string;
};

/** Nothing more is coming on this socket: no turn, and no follow-up questions due. */
function isQuiet(transport: ChatWsTransport): boolean {
  return !transport.isTurnActive() && !transport.expectsFollowUps();
}

type Options = {
  chatId: string | null;
  isCurrentView: () => boolean;
  ttftTurnId: () => string | null;
  onPayload: (boundChatId: string | null, payload: ChatSsePayload, ttftTurnId?: string | null) => void;
  onFallback: (transport: ChatWsTransport, signal: ChatWsFallbackSignal) => void;
  onSendFailure: (error: unknown, ttftTurnId: string | null) => void;
  onRegenerateFailure: (error: unknown) => void;
};

/**
 * WebSocket and SSE pipes for one chat view. Message state stays in useChat;
 * this hook only opens, sends, and tears down the connection.
 */
export function useChatTransport({
  chatId,
  isCurrentView,
  ttftTurnId,
  onPayload,
  onFallback,
  onSendFailure,
  onRegenerateFailure,
}: Options) {
  // Keyed on the account, not the bearer token: the token rotates hourly, and the
  // socket reads the newest one when it connects (code-health audit NET-11, NET-12).
  const { account, getToken } = useAccountSession();
  const wsTransportRef = useRef<ChatWsTransport | null>(null);
  /** The token the current transport authenticates with. */
  const transportTokenRef = useRef<string | null>(null);
  // A view's sockets share it, so a socket rebuilt after Stop or a token
  // refresh keeps the wait; opening a chat starts with none (`detach`).
  const backoffRef = useRef(createWsBackoff());
  const connectRef = useRef<() => Promise<void>>(() => Promise.resolve());
  const sseAbortRef = useRef<AbortController | null>(null);
  const sseAbortChatIdRef = useRef<string | null>(null);
  const backgroundedRef = useRef(false);
  const releasedInBackgroundRef = useRef(false);
  const isCurrentViewRef = useLatestRef(isCurrentView);
  const ttftTurnIdRef = useLatestRef(ttftTurnId);
  const onPayloadRef = useLatestRef(onPayload);
  const onFallbackRef = useLatestRef(onFallback);
  const onSendFailureRef = useLatestRef(onSendFailure);
  const onRegenerateFailureRef = useLatestRef(onRegenerateFailure);

  const beginSseStream = useCallback(() => {
    if (shouldAbortPriorSse(sseAbortChatIdRef.current, chatId)) {
      sseAbortRef.current?.abort();
    }
    const controller = new AbortController();
    sseAbortRef.current = controller;
    sseAbortChatIdRef.current = chatId;
    return controller.signal;
  }, [chatId]);

  /** In the background an idle socket only answers the server's keepalive
   * pings, which wakes the radio every 20 seconds. A turn in flight keeps it
   * until its done or error; the next send or foreground opens a new one. */
  const releaseIdleInBackground = useCallback(() => {
    const transport = wsTransportRef.current;
    if (!backgroundedRef.current || !transport || transport.isTurnActive()) return;
    wsTransportRef.current = null;
    releasedInBackgroundRef.current = true;
    transport.close();
  }, []);

  /** A token refreshed during a turn takes over once that turn, and the
   * follow-up questions sent after its reply, are done. */
  const renewStaleToken = useCallback(() => {
    const transport = wsTransportRef.current;
    if (backgroundedRef.current || !transport || !isQuiet(transport)) return;
    if (transportTokenRef.current !== getToken()) void connectRef.current();
  }, [getToken]);

  const openSocket = useCallback((): Promise<void> => {
    const token = getToken();
    if (!account || !token || !chatId || !isCurrentViewRef.current()) return Promise.resolve();
    let transport = wsTransportRef.current;
    if (transport && transportTokenRef.current !== token && isQuiet(transport)) {
      // The server checks a socket's own token on every send: after a refresh
      // the old one is refused and the send goes over SSE. A new socket instead.
      wsTransportRef.current = null;
      transport.close();
      transport = null;
    }
    if (!transport) {
      transport = new ChatWsTransport({
        url: chatWebSocketUrl(chatId),
        getToken,
        clientTimezone: getDeviceTimezone,
        backoff: backoffRef.current,
        onPayload: (payload) => {
          if (wsTransportRef.current !== transport) return;
          onPayloadRef.current(chatId, payload, ttftTurnIdRef.current());
          releaseIdleInBackground();
          renewStaleToken();
        },
        onFallback: (signal) => onFallbackRef.current(transport!, signal),
      });
      wsTransportRef.current = transport;
      transportTokenRef.current = token;
    }
    return transport.connect();
  }, [
    account, chatId, getToken, releaseIdleInBackground, renewStaleToken, isCurrentViewRef, onFallbackRef,
    onPayloadRef, ttftTurnIdRef,
  ]);

  const connect = useCallback((): Promise<void> => {
    const token = getToken();
    if (!account || !token) return Promise.resolve();
    // An expired token is refreshed before the handshake, not refused after it.
    if (!accessTokenNeedsRefresh(token)) return openSocket();
    return freshAccessToken(token).then((fresh) => (fresh ? openSocket() : undefined));
  }, [account, getToken, openSocket]);
  useLayoutEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Handshake overlaps reading. Debounced so flicking the chat list does not
  // open a socket per glance (each handshake counts against the connect limit).
  useEffect(() => {
    if (!account || !chatId) return;
    const timer = setTimeout(() => {
      void connect();
    }, EAGER_CONNECT_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [account, chatId, connect]);

  useEffect(() => {
    return () => {
      const transport = wsTransportRef.current;
      wsTransportRef.current = null;
      transport?.close();
    };
  }, []);

  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "background") {
        backgroundedRef.current = true;
        releaseIdleInBackground();
        return;
      }
      if (state !== "active") return;
      backgroundedRef.current = false;
      // A turn kept its socket in the background, where the radio may have dropped it.
      const kept = wsTransportRef.current;
      if (kept?.isTurnActive()) kept.probe();
      if (!releasedInBackgroundRef.current) return;
      releasedInBackgroundRef.current = false;
      // Same head start as opening the chat: the handshake overlaps reading.
      void connect();
    });
    return () => sub.remove();
  }, [connect, releaseIdleInBackground]);

  // Wi-Fi ⇄ cellular, or back online: a socket opened on the old path can be
  // half-open. A turn's socket is probed (dropped if it does not answer); an
  // idle one is replaced, once online, while the chat is open. A socket the
  // server already closed for idling stays closed. Failures on the old path
  // do not hold the new one back.
  useEffect(() => {
    let previous: NetInfoState | null = null;
    let reopen = false;
    return NetInfo.addEventListener((state) => {
      const changed = isNetworkPathChange(previous, state);
      previous = state;
      if (!changed || backgroundedRef.current) return;
      backoffRef.current = createWsBackoff();
      const transport = wsTransportRef.current;
      if (transport?.isTurnActive()) {
        transport.probe();
        return;
      }
      if (transport?.holdsSocket()) reopen = true;
      wsTransportRef.current = null;
      transport?.close();
      if (!reopen || isNetworkOffline(state)) return;
      reopen = false;
      void connectRef.current();
    });
  }, []);

  const sendViaSse = useCallback(
    async (content: string, options?: SendSseOptions) => {
      const token = getToken();
      if (!token || !chatId) return;
      const signal = beginSseStream();
      const turnId = options?.ttftTurnId ?? null;
      try {
        await streamChatMessageSse({
          token,
          chatId,
          content,
          attachmentIds: options?.attachmentIds,
          model: options?.model,
          clientGeo: options?.clientGeo,
          ttftTurnId: turnId,
          clientMessageId: options?.clientMessageId,
          signal,
          onEvent: (payload) => {
            if (!signal.aborted && sseAbortRef.current?.signal === signal) {
              onPayloadRef.current(chatId, payload, turnId);
            }
          },
        });
      } catch (err) {
        if (!isCurrentViewRef.current() || signal.aborted || sseAbortRef.current?.signal !== signal) return;
        sseAbortRef.current = null;
        sseAbortChatIdRef.current = null;
        onSendFailureRef.current(err, turnId);
      }
    },
    [getToken, chatId, beginSseStream, isCurrentViewRef, onPayloadRef, onSendFailureRef],
  );

  const regenerateViaSse = useCallback(
    async (model?: string | null, clientGeo?: ClientGeo | null) => {
      const token = getToken();
      if (!token || !chatId) return;
      const signal = beginSseStream();
      try {
        await streamChatRegenerateSse({
          token,
          chatId,
          model,
          clientGeo,
          signal,
          onEvent: (payload) => {
            if (!signal.aborted && sseAbortRef.current?.signal === signal) {
              onPayloadRef.current(chatId, payload);
            }
          },
        });
      } catch (err) {
        if (!isCurrentViewRef.current() || signal.aborted || sseAbortRef.current?.signal !== signal) return;
        sseAbortRef.current = null;
        sseAbortChatIdRef.current = null;
        onRegenerateFailureRef.current(err);
      }
    },
    [getToken, chatId, beginSseStream, isCurrentViewRef, onPayloadRef, onRegenerateFailureRef],
  );

  const currentSocket = useCallback(() => wsTransportRef.current, []);

  const dropSocket = useCallback(() => {
    const transport = wsTransportRef.current;
    wsTransportRef.current = null;
    transport?.close();
  }, []);

  /** Close the socket and forget an in-flight SSE without aborting it.
   * Stop is the only hard cancel; leaving a chat must let finalize drain.
   * The next view tries the socket at once, whatever failed in this one. */
  const detach = useCallback(() => {
    dropSocket();
    backoffRef.current = createWsBackoff();
    sseAbortRef.current = null;
    sseAbortChatIdRef.current = null;
  }, [dropSocket]);

  const abortSse = useCallback(() => {
    sseAbortRef.current?.abort();
    sseAbortRef.current = null;
  }, []);

  /** `shownChars`: how much of the reply the phone kept on screen (see ChatWsTransport.cancel). */
  const cancelSocket = useCallback((shownChars?: number) => {
    wsTransportRef.current?.cancel(shownChars);
  }, []);

  return {
    connect,
    sendViaSse,
    regenerateViaSse,
    currentSocket,
    dropSocket,
    detach,
    abortSse,
    cancelSocket,
  };
}
