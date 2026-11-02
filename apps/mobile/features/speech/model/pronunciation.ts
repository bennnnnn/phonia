/** Device TTS via expo-speech; optional cloud TTS via /speech/tts. */

import { isAbortError } from "@/lib/api/abort";
import { cacheDirectory, deleteAsync, writeAsStringAsync, EncodingType } from "expo-file-system/legacy";
import { AppState } from "react-native";

import { newAccountFile } from "@/lib/accountFiles";
import { requestRaw } from "@/lib/api/client";
import {
  applySpeechRate,
  PLAYBACK_POLL_MS,
  PLAYBACK_STATUS_MS,
  playbackStatusFinished,
} from "@/features/speech/model/cloudPlayback";
import { markdownToSpeechText } from "@/lib/markdown/plain";
import { readAloudPart } from "@/features/speech/model/readAloudLength";
import { splitTtsChunks } from "@/features/speech/model/ttsLead";
import { currentSpeechRate, getSpeechRate } from "@/features/speech/model/speechRate";
import { getTtsModel, TTS_DEVICE_MODEL, TTS_FAST_MODEL } from "@/features/speech/model/ttsPreference";
import { loadExpoAudio, preparePlaybackAudioMode } from "@/lib/speech/voiceAudio";

export { readAloudIsCut } from "@/features/speech/model/readAloudLength";

type SpeechModule = typeof import("expo-speech");

/** undefined = not loaded yet; null = unavailable or failed to load. */
let speechModule: SpeechModule | null | undefined;
let cloudPlayerCleanup: (() => void) | null = null;
let ttsAbort: AbortController | null = null;
/** Bumped on every stop / new speak so in-flight work cannot start device TTS. */
let speakGeneration = 0;
let ttsTapAt = 0;
let ttsStartLoggedFor = -1;

function markTtsTap(): void {
  ttsTapAt = Date.now();
  ttsStartLoggedFor = -1;
}

function ttsElapsedMs(): number {
  return ttsTapAt > 0 ? Date.now() - ttsTapAt : 0;
}

function logTtsLatency(stage: string, extra?: Record<string, string | number | boolean>): void {
  console.info("[tts-latency]", { ms: ttsElapsedMs(), stage, ...extra });
}

function logTtsSpeechStarted(): void {
  if (ttsStartLoggedFor === speakGeneration) return;
  ttsStartLoggedFor = speakGeneration;
  logTtsLatency("speech_started");
}

/** Sync require keeps expo-speech in the main bundle (async import() breaks Metro module IDs).
 * Mic permission is not required — read-aloud is independent of voice input. */
function loadSpeech(): SpeechModule | null {
  if (speechModule === null) return null;
  if (speechModule) return speechModule;
  try {
    speechModule = require("expo-speech") as SpeechModule;
    return speechModule;
  } catch {
    speechModule = null;
    return null;
  }
}

type SpeakResult = { ok: true } | { ok: false; reason: "unavailable" | "error" };

function isCurrentSpeak(generation: number): boolean {
  return generation === speakGeneration;
}

let backgroundStop: { remove: () => void } | null = null;

/**
 * Read-aloud ends when the app goes to the background. expo-audio pauses
 * players there (no `shouldPlayInBackground`), and the clip queue read that
 * pause as the end of a clip: it fetched and started the next clip in the
 * background. One listener for the app's lifetime, added on first use.
 */
function stopReadingInBackground(): void {
  if (backgroundStop) return;
  backgroundStop = AppState.addEventListener("change", (state) => {
    if (state === "background") stopSpeaking();
  });
}

function stopCloudPlayer(): void {
  const cleanup = cloudPlayerCleanup;
  cloudPlayerCleanup = null;
  if (cloudPlaybackFinish) {
    cloudPlaybackFinish();
    cloudPlaybackFinish = null;
  }
  try {
    cleanup?.();
  } catch {
    /* ignore */
  }
}

function stopDeviceSpeech(): void {
  const Speech = loadSpeech();
  if (!Speech) return;
  try {
    Speech.stop();
  } catch {
    speechModule = null;
  }
}

const TTS_JSON_TIMEOUT_MS = 60_000;

type TtsClip = { audio_base64: string; content_type: string; lead_hash?: string | null };

type PrefetchState = {
  key: string;
  model: string;
  chunks: string[];
  abort: AbortController;
  clips: Array<TtsClip | null>;
  inflight: Array<Promise<TtsClip | null> | null>;
  leadHash: string | null;
};

let prefetch: PrefetchState | null = null;

function prefetchCacheKey(text: string, model: string): string {
  return `${model}\0${text}`;
}

async function fetchCloudTtsClip(
  token: string,
  text: string,
  language: string,
  model: string,
  part: "full" | "lead" | "rest",
  signal: AbortSignal,
  leadHash?: string | null,
): Promise<TtsClip | null> {
  const plain = readAloudPart(text);
  if (!plain) return null;
  const body: Record<string, string> = {
    text: plain,
    language,
    model,
    part,
  };
  if (part === "rest" && leadHash) {
    body.lead_hash = leadHash;
  }
  const response = await requestRaw(
    "/speech/tts",
    token,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    },
    true,
    TTS_JSON_TIMEOUT_MS,
  );
  if (!response.ok) return null;
  const data = (await response.json()) as {
    audio_base64?: string;
    content_type?: string;
    lead_hash?: string | null;
  };
  if (!data.audio_base64) return null;
  return {
    audio_base64: data.audio_base64,
    content_type: data.content_type ?? "audio/mpeg",
    lead_hash: data.lead_hash ?? null,
  };
}

type PlaybackStatus = {
  didJustFinish?: boolean;
  currentTime?: number;
  duration?: number;
  playing?: boolean;
};

/** Cloud TTS clip playback (expo-audio). Never mix with expo-speech. */
type PlaybackHandle = {
  play: () => void;
  setPlaybackRate?: (rate: number, pitchCorrectionQuality?: "low" | "medium" | "high") => void;
  shouldCorrectPitch?: boolean;
  pause: () => void;
  remove: () => void;
  currentTime?: number;
  duration?: number;
  playing?: boolean;
  addListener: (
    event: "playbackStatusUpdate",
    listener: (status: PlaybackStatus) => void,
  ) => { remove: () => void };
};

const CLOUD_PLAYBACK_MAX_MS = 300_000;
/** expo-speech at 1× sounded rushed; this is "normal" before the user's speed. */
const DEVICE_SPEECH_RATE = 0.92;
let cloudPlaybackFinish: (() => void) | null = null;

function waitUntilPlaybackEnds(player: PlaybackHandle, maxMs = CLOUD_PLAYBACK_MAX_MS): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    let sawPlaying = false;
    let sub: { remove: () => void } | null = null;
    const finish = () => {
      if (settled) return;
      settled = true;
      if (cloudPlaybackFinish === finish) cloudPlaybackFinish = null;
      clearTimeout(timer);
      clearInterval(poll);
      try {
        sub?.remove();
      } catch {
        /* ignore */
      }
      resolve();
    };
    cloudPlaybackFinish = finish;
    sub = player.addListener("playbackStatusUpdate", (status) => {
      if (status.playing) sawPlaying = true;
      if (playbackStatusFinished({ ...status, sawPlaying })) finish();
    });
    const poll = setInterval(() => {
      if (player.playing) sawPlaying = true;
      if (
        playbackStatusFinished({
          currentTime: player.currentTime,
          duration: player.duration,
          playing: player.playing,
          sawPlaying,
        })
      ) {
        finish();
      }
    }, PLAYBACK_POLL_MS);
    const timer = setTimeout(finish, maxMs);
  });
}

async function playCloudBase64(
  audioBase64: string,
  contentType: string,
  generation: number,
  maxWaitMs?: number,
): Promise<SpeakResult> {
  const Audio = loadExpoAudio();
  if (!Audio || !cacheDirectory) return { ok: false, reason: "unavailable" };
  if (!isCurrentSpeak(generation)) return { ok: true };
  let written: string | null = null;
  try {
    // Only stop the previous clip — never abort this utterance's fetches.
    stopCloudPlayer();
    stopDeviceSpeech();
    const path = newAccountFile("speech", contentType.includes("wav") ? "wav" : "mp3");
    written = path;
    await writeAsStringAsync(path, audioBase64, { encoding: EncodingType.Base64 });
    if (!isCurrentSpeak(generation)) {
      discardClip(path);
      return { ok: true };
    }
    const player = Audio.createAudioPlayer(path, {
      updateInterval: PLAYBACK_STATUS_MS,
    }) as PlaybackHandle;
    applySpeechRate(player, currentSpeechRate());
    const release = () => {
      try {
        player.pause();
      } catch {
        /* ignore */
      }
      try {
        player.remove();
      } catch {
        /* ignore */
      }
      // Each clip is written fresh; nothing reads this file again.
      void deleteAsync(path, { idempotent: true }).catch(() => undefined);
    };
    cloudPlayerCleanup = release;
    player.play();
    logTtsSpeechStarted();
    await waitUntilPlaybackEnds(player, maxWaitMs ?? CLOUD_PLAYBACK_MAX_MS);
    // Release on finish, not on the next tap: a finished player keeps the
    // audio session in playback and holds the decoder.
    if (cloudPlayerCleanup === release) {
      cloudPlayerCleanup = null;
      release();
    }
    return { ok: true };
  } catch {
    if (written) discardClip(written);
    return { ok: false, reason: "error" };
  }
}

function discardClip(path: string): void {
  void deleteAsync(path, { idempotent: true }).catch(() => undefined);
}

async function beginDeviceSpeech(
  text: string,
  language: string,
  generation: number,
): Promise<SpeakResult> {
  if (!isCurrentSpeak(generation)) return { ok: true };
  await preparePlaybackAudioMode();
  if (!isCurrentSpeak(generation)) return { ok: true };
  const Speech = loadSpeech();
  if (!Speech) return { ok: false, reason: "unavailable" };
  const plain = text.slice(0, 8000).trim();
  if (!plain) return { ok: false, reason: "error" };
  return new Promise((resolve) => {
    try {
      Speech.speak(plain, {
        language,
        rate: DEVICE_SPEECH_RATE * currentSpeechRate(),
        onStart: () => logTtsSpeechStarted(),
        onDone: () => resolve({ ok: true }),
        onStopped: () => resolve({ ok: true }),
        onError: () => resolve({ ok: false, reason: "error" }),
      });
    } catch {
      speechModule = null;
      resolve({ ok: false, reason: "unavailable" });
    }
  });
}

function ttsPartForChunk(index: number, total: number): "full" | "lead" | "rest" {
  if (total <= 1) return "full";
  return index === 0 ? "lead" : "rest";
}

function ensurePrefetchState(text: string, model: string): PrefetchState {
  const key = prefetchCacheKey(text, model);
  if (prefetch?.key === key) return prefetch;
  prefetch?.abort.abort();
  const chunks = splitTtsChunks(text);
  const next: PrefetchState = {
    key,
    model,
    chunks,
    abort: new AbortController(),
    clips: chunks.map(() => null),
    inflight: chunks.map(() => null),
    leadHash: null,
  };
  prefetch = next;
  return next;
}

function ensureChunk(
  state: PrefetchState,
  index: number,
  token: string,
  language: string,
  signal: AbortSignal,
): Promise<TtsClip | null> {
  const cached = state.clips[index];
  if (cached) {
    if (cached.lead_hash) state.leadHash = cached.lead_hash;
    return Promise.resolve(cached);
  }
  const pending = state.inflight[index];
  if (pending) return pending;
  const chunk = state.chunks[index];
  if (!chunk) return Promise.resolve(null);
  const request = fetchCloudTtsClip(
    token,
    chunk,
    language,
    state.model,
    ttsPartForChunk(index, state.chunks.length),
    signal,
    state.leadHash,
  )
    .then((clip) => {
      if (clip?.lead_hash) state.leadHash = clip.lead_hash;
      if (state.clips[index] == null) state.clips[index] = clip;
      if (state.inflight[index] === request) state.inflight[index] = null;
      return state.clips[index];
    })
    .catch((error: unknown) => {
      if (state.inflight[index] === request) state.inflight[index] = null;
      if (isAbortError(error)) return state.clips[index];
      throw error;
    });
  state.inflight[index] = request;
  return request;
}

async function playChunkPipeline(
  token: string,
  text: string,
  language: string,
  model: string,
  generation: number,
  signal: AbortSignal,
): Promise<SpeakResult> {
  const state = ensurePrefetchState(text, model);
  const first = state.chunks[0];
  if (!first) return { ok: false, reason: "error" };
  const cached = Boolean(state.clips[0]);
  logTtsLatency("lead_request", {
    leadChars: first.length,
    chunks: state.chunks.length,
    cached,
  });
  const leadClip = await ensureChunk(state, 0, token, language, signal);
  if (!isCurrentSpeak(generation)) return { ok: true };
  if (!leadClip) {
    logTtsLatency("lead_failed");
    return { ok: false, reason: "error" };
  }
  logTtsLatency("lead_ready", { leadChars: first.length, cached });

  for (let index = 0; index < state.chunks.length; index += 1) {
    if (!isCurrentSpeak(generation)) return { ok: true };
    const clip =
      index === 0 ? leadClip : await ensureChunk(state, index, token, language, signal);
    if (!clip) return index === 0 ? { ok: false, reason: "error" } : { ok: true };
    if (index + 1 < state.chunks.length) {
      void ensureChunk(state, index + 1, token, language, signal);
    }
    const played = await playCloudBase64(clip.audio_base64, clip.content_type, generation);
    if (!played.ok) return played;
  }
  return { ok: true };
}

/**
 * Cloud TTS plays a finished WAV/MP3 for the first sentence, then the rest.
 * Raw PCM streaming caused static and waited for the full body on device.
 */
export async function speakPlainText(
  text: string,
  language = "en-US",
  options?: { token?: string | null; preferCloud?: boolean; preferFast?: boolean },
): Promise<SpeakResult> {
  markTtsTap();
  logTtsLatency("tap");
  stopSpeaking();
  stopReadingInBackground();
  const generation = speakGeneration;
  const plain = readAloudPart(markdownToSpeechText(text));
  if (!plain) return { ok: false, reason: "error" };

  const [ttsModel] = await Promise.all([getTtsModel(), getSpeechRate()]);
  if (!isCurrentSpeak(generation)) return { ok: true };

  const token = options?.token ?? null;
  await preparePlaybackAudioMode();
  if (!isCurrentSpeak(generation)) return { ok: true };
  // "Use on-device voice" wins for every plan; `preferCloud` only falls back to the phone.
  const cloudModel = ttsModel === TTS_DEVICE_MODEL ? ttsModel : options?.preferFast ? TTS_FAST_MODEL : ttsModel;
  const useCloud = Boolean(token) && cloudModel !== TTS_DEVICE_MODEL;
  if (!useCloud || !token) {
    return beginDeviceSpeech(plain, language, generation);
  }

  const ac = new AbortController();
  ttsAbort = ac;
  try {
    const played = await playChunkPipeline(
      token,
      plain,
      language,
      cloudModel,
      generation,
      ac.signal,
    );
    if (played.ok || !isCurrentSpeak(generation) || !options?.preferCloud) return played;
    return beginDeviceSpeech(plain, language, generation);
  } catch (error) {
    if (isAbortError(error) || !isCurrentSpeak(generation)) {
      return { ok: true };
    }
    if (options?.preferCloud) {
      return beginDeviceSpeech(plain, language, generation);
    }
    return { ok: false, reason: "error" };
  } finally {
    if (ttsAbort === ac) ttsAbort = null;
  }
}

export function stopSpeaking(): void {
  speakGeneration += 1;
  ttsAbort?.abort();
  ttsAbort = null;
  stopCloudPlayer();
  stopDeviceSpeech();
}
