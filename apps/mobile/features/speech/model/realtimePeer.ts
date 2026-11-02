import { NativeModules, Platform, TurboModuleRegistry } from "react-native";

import { liveTalkDataChannelText } from "@/features/speech/model/liveTalkLogic";
import { exchangeRealtimeSdp } from "@/features/speech/model/realtimeSdp";
import { yieldMicToWebRtc } from "@/lib/speech/voiceAudio";

/*
 * react-native-webrtc loads optionally at runtime (dev builds only), so these
 * describe just the members this file touches instead of importing its types.
 */
type WebRtcTrack = {
  id?: string;
  kind?: string;
  enabled: boolean;
  muted?: boolean;
  readyState?: string;
  stop: () => void;
  /** react-native-webrtc's remote playback volume; not on every build. */
  _setVolume?: (volume: number) => void;
};

type WebRtcStream = {
  getTracks: () => WebRtcTrack[];
  getAudioTracks: () => WebRtcTrack[];
  /** Frees the native stream and its tracks (react-native-webrtc). */
  release?: () => void;
};

/**
 * A track's `stop()` only flags it: the native stream, track and source stay in
 * WebRTCModule until `release()`, one more per session and per failed connect
 * (code-health audit LEAK-06).
 */
function releaseStream(stream: WebRtcStream): void {
  try {
    stream.release?.();
  } catch {
    /* already released */
  }
}

type WebRtcSessionDescription = { sdp?: string };

type WebRtcDataChannel = {
  readyState?: string;
  send: (data: string) => void;
  close: () => void;
  onopen?: () => void;
  onclose?: () => void;
  onerror?: () => void;
  onmessage?: (message: { data?: unknown }) => void;
};

type WebRtcTrackEvent = { track?: WebRtcTrack; streams?: WebRtcStream[] };

type WebRtcPeerConnection = {
  connectionState?: string;
  iceConnectionState?: string;
  iceGatheringState?: string;
  localDescription?: WebRtcSessionDescription | null;
  ontrack?: (event: WebRtcTrackEvent) => void;
  onconnectionstatechange?: () => void;
  oniceconnectionstatechange?: () => void;
  addEventListener?: (type: string, listener: () => void) => void;
  removeEventListener?: (type: string, listener: () => void) => void;
  addTrack: (track: WebRtcTrack, stream: WebRtcStream) => void;
  createDataChannel: (label: string) => WebRtcDataChannel;
  createOffer: () => Promise<WebRtcSessionDescription>;
  setLocalDescription: (description: WebRtcSessionDescription) => Promise<void>;
  setRemoteDescription: (description: WebRtcSessionDescription) => Promise<void>;
  getReceivers?: () => { track?: WebRtcTrack | null }[];
  close: () => void;
};

type NativeWebRtc = {
  __WEBRTC_STUB__?: boolean;
  mediaDevices: {
    getUserMedia: (constraints: object) => Promise<WebRtcStream>;
  };
  RTCPeerConnection: new (config?: object) => WebRtcPeerConnection;
  RTCSessionDescription: new (init: { type: string; sdp: string }) => WebRtcSessionDescription;
};

type RealtimePeerHandlers = {
  onOpen: () => void;
  onMessage: (event: Record<string, unknown>) => void;
  onPeerFailed: (message: string) => void;
  onChannelFailed: (message: string) => void;
};

type RealtimePeer = {
  send: (payload: Record<string, unknown>) => void;
  /** The local offer, after ICE gathering off iOS. */
  createOffer: () => Promise<string>;
  /** Exchanges SDP with the ephemeral secret and waits for the data channel. */
  connect: (clientSecret: string, offerSdp: string) => Promise<void>;
  closeChannel: () => void;
  /** Silences remote audio, stops the mic and closes the peer. */
  close: () => void;
};

const ICE_GATHER_TIMEOUT_MS = 2_500;
const CONNECTION_TIMEOUT_MS = 10_000;
const DEBUG_PREFIX = "[LiveTalk/WebRTC]";

export function debugRealtime(stage: string, detail?: unknown): void {
  if (!__DEV__) return;
  if (detail === undefined) {
    console.info(`${DEBUG_PREFIX} ${stage}`);
  } else {
    console.info(`${DEBUG_PREFIX} ${stage}`, detail);
  }
}

function isWebRtcLinked(): boolean {
  try {
    if (TurboModuleRegistry.get("WebRTCModule") != null) return true;
  } catch {
    /* Expo Go / incomplete RN mock */
  }
  return Boolean((NativeModules as Record<string, unknown> | undefined)?.WebRTCModule);
}

export function loadWebRtc(): NativeWebRtc | null {
  // Expo Go fatals on require("react-native-webrtc") even inside try/catch.
  // Probe the native registry first — same pattern as getPreviewWebView.
  if (!isWebRtcLinked()) return null;
  try {
    // Native module: Live Talk requires a rebuilt dev client, not Expo Go.
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- loaded after the native probe; an import crashes Expo Go
    const webrtc = require("react-native-webrtc") as NativeWebRtc;
    if (webrtc.__WEBRTC_STUB__) return null;
    return webrtc;
  } catch {
    return null;
  }
}

function sendRealtimePayload(channel: WebRtcDataChannel, payload: Record<string, unknown>) {
  if (channel.readyState !== "open" || typeof channel.send !== "function") return;
  try {
    channel.send(JSON.stringify(payload));
  } catch {
    /* best-effort */
  }
}

async function waitForIceGathering(pc: WebRtcPeerConnection): Promise<void> {
  if (pc.iceGatheringState === "complete") return;
  await new Promise<void>((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        pc.removeEventListener?.("icegatheringstatechange", onStateChange);
      } catch {
        /* best-effort */
      }
      resolve();
    };
    const onStateChange = () => {
      debugRealtime("ice-gathering", pc.iceGatheringState);
      if (pc.iceGatheringState === "complete") finish();
    };
    const timer = setTimeout(finish, ICE_GATHER_TIMEOUT_MS);
    pc.addEventListener?.("icegatheringstatechange", onStateChange);
  });
}

function enableRemoteAudioTrack(track: WebRtcTrack | null | undefined): void {
  if (!track || track.kind !== "audio") return;
  try {
    track.enabled = true;
  } catch {
    /* remote audio is still auto-rendered by react-native-webrtc */
  }
  try {
    if (typeof track._setVolume === "function") track._setVolume(1);
  } catch {
    /* best-effort */
  }
}

/**
 * Hands the mic from expo-audio to WebRTC; throws microphone_unavailable without an audio
 * track. That is the device (the mic in use or missing), not an app without WebRTC.
 */
export async function openRealtimeMicrophone(
  webrtc: NativeWebRtc,
  audio: object,
): Promise<{ stream: WebRtcStream; audioTracks: WebRtcTrack[] }> {
  await yieldMicToWebRtc();
  debugRealtime("requesting-microphone", { platform: Platform.OS });
  const stream = await webrtc.mediaDevices.getUserMedia({ audio, video: false });
  const audioTracks = stream.getAudioTracks();
  if (audioTracks.length === 0) {
    for (const track of stream.getTracks()) track.stop();
    releaseStream(stream);
    throw new Error("microphone_unavailable");
  }
  debugRealtime("microphone-ready", {
    tracks: audioTracks.length,
    enabled: audioTracks.map((track) => track.enabled),
    readyState: audioTracks.map((track) => track.readyState),
  });
  return { stream, audioTracks };
}

async function createLocalOffer(pc: WebRtcPeerConnection): Promise<string> {
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  // iOS Simulator SIGABRTs in AURemoteIO when setRemoteDescription is
  // applied after ICE gathering (candidates in the offer). Trickle from
  // the answer is enough; ICE still reaches connected without them.
  if (Platform.OS !== "ios") {
    await waitForIceGathering(pc);
  }
  const offerSdp = String(offer.sdp || "");
  const localSdp = String(pc.localDescription?.sdp || "");
  const sdp = offerSdp || localSdp;
  if (!sdp) throw new Error("Could not create realtime audio offer");
  debugRealtime("sending-sdp", {
    transport: "direct-ephemeral",
    hasAudio: sdp.includes("m=audio"),
    hasData: sdp.includes("m=application"),
    hasCandidate: sdp.includes("a=candidate"),
    gathering: pc.iceGatheringState,
  });
  return sdp;
}

/**
 * Resolves when the data channel opens and rejects on the first peer, ICE or
 * channel failure, whichever comes first; later ones still reach handlers.
 */
function watchConnection(
  pc: WebRtcPeerConnection,
  dataChannel: WebRtcDataChannel,
  handlers: RealtimePeerHandlers,
): Promise<void> {
  let connectionSettled = false;
  let resolveConnected: (() => void) | null = null;
  let rejectConnected: ((error: Error) => void) | null = null;
  const connectedPromise = new Promise<void>((resolve, reject) => {
    resolveConnected = resolve;
    rejectConnected = reject;
  });
  const failConnection = (message: string) => {
    if (connectionSettled) return;
    connectionSettled = true;
    debugRealtime("connection-failed", message);
    rejectConnected?.(new Error(message));
  };
  const failPeer = (message: string) => {
    failConnection(message);
    handlers.onPeerFailed(message);
  };
  pc.onconnectionstatechange = () => {
    debugRealtime("peer-state", pc.connectionState);
    if (pc.connectionState === "failed" || pc.connectionState === "closed") {
      failPeer("Realtime voice connection failed");
    }
  };
  pc.oniceconnectionstatechange = () => {
    debugRealtime("ice-state", pc.iceConnectionState);
    if (pc.iceConnectionState === "failed") failPeer("Realtime voice ICE connection failed");
  };
  dataChannel.onopen = () => {
    if (connectionSettled) return;
    connectionSettled = true;
    debugRealtime("data-channel-open", {
      ice: String(pc.iceConnectionState),
      peer: String(pc.connectionState),
    });
    resolveConnected?.();
    handlers.onOpen();
  };
  dataChannel.onerror = () => {
    failConnection("Realtime voice data channel failed");
    handlers.onChannelFailed("Realtime voice data channel failed");
  };
  return connectedPromise;
}

async function waitForConnection(connected: Promise<void>): Promise<void> {
  let connectDeadline: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      connected,
      new Promise<never>((_, reject) => {
        connectDeadline = setTimeout(
          () => reject(new Error("Realtime voice connection timed out")),
          CONNECTION_TIMEOUT_MS,
        );
      }),
    ]);
  } finally {
    clearTimeout(connectDeadline);
  }
}

export function createRealtimePeer(
  webrtc: NativeWebRtc,
  localStream: WebRtcStream,
  handlers: RealtimePeerHandlers,
): RealtimePeer {
  const pc = new webrtc.RTCPeerConnection({});
  for (const track of localStream.getTracks()) {
    pc.addTrack(track, localStream);
  }
  const dataChannel = pc.createDataChannel("oai-events");
  const remoteAudioTracks = new Set<WebRtcTrack>();
  const addRemoteAudio = (track: WebRtcTrack) => {
    remoteAudioTracks.add(track);
    enableRemoteAudioTrack(track);
  };
  const connected = watchConnection(pc, dataChannel, handlers);

  pc.ontrack = (event: WebRtcTrackEvent) => {
    if (event.track?.kind === "audio") {
      addRemoteAudio(event.track);
      debugRealtime("remote-audio-track", {
        id: event.track.id,
        enabled: event.track.enabled,
        muted: event.track.muted,
        readyState: event.track.readyState,
      });
    }
    for (const stream of event.streams ?? []) {
      for (const track of stream.getAudioTracks?.() ?? []) addRemoteAudio(track);
    }
  };
  dataChannel.onclose = () => debugRealtime("data-channel-close");
  dataChannel.onmessage = (message: { data?: unknown }) => {
    const raw = liveTalkDataChannelText(message.data);
    if (raw == null) return;
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }
    handlers.onMessage(event);
  };

  return {
    send: (payload) => sendRealtimePayload(dataChannel, payload),
    createOffer: () => createLocalOffer(pc),
    connect: async (clientSecret, offerSdp) => {
      const answerSdp = await exchangeRealtimeSdp(clientSecret, offerSdp);
      debugRealtime("received-sdp-answer", {
        transport: "direct-ephemeral",
        hasAudio: answerSdp.includes("m=audio"),
        hasData: answerSdp.includes("m=application"),
      });
      await pc.setRemoteDescription(new webrtc.RTCSessionDescription({ type: "answer", sdp: answerSdp }));
      for (const receiver of pc.getReceivers?.() ?? []) {
        if (receiver.track?.kind === "audio") addRemoteAudio(receiver.track);
      }
      await waitForConnection(connected);
    },
    closeChannel: () => {
      try {
        dataChannel.close();
      } catch {
        /* best-effort */
      }
    },
    close: () => {
      for (const track of remoteAudioTracks) {
        try {
          track.enabled = false;
        } catch {
          /* best-effort */
        }
      }
      remoteAudioTracks.clear();
      for (const track of localStream.getTracks()) track.stop();
      pc.close();
      releaseStream(localStream);
    },
  };
}
