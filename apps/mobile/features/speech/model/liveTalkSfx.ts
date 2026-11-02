import { EncodingType, cacheDirectory, writeAsStringAsync } from "expo-file-system/legacy";

import { encodePcm16Wav } from "@/lib/audio/wav";
import { notifySuccess, tap } from "@/lib/haptics";
import { loadExpoAudio } from "@/lib/speech/voiceAudio";

type LiveTalkCue = "start" | "end";

/** Rising open / falling close. Open must finish and release before WebRTC. */
export const LIVE_TALK_CUE_TONES: Record<LiveTalkCue, readonly { hz: number; ms: number }[]> = {
  start: [
    { hz: 659, ms: 90 },
    { hz: 880, ms: 170 },
  ],
  end: [
    { hz: 784, ms: 90 },
    { hz: 523, ms: 190 },
  ],
};

const SAMPLE_RATE = 22_050;
const AMPLITUDE = 0.22;
const GAP_MS = 24;
const CUE_RELEASE_PAD_MS = 80;

function liveTalkCueDurationMs(kind: LiveTalkCue): number {
  const tones = LIVE_TALK_CUE_TONES[kind];
  return tones.reduce((sum, tone) => sum + tone.ms, 0) + GAP_MS * Math.max(0, tones.length - 1);
}

let cueEpoch = 0;

type CuePlayer = {
  play: () => void;
  remove: () => void;
};

let cuePlayer: CuePlayer | null = null;
const cueUriByKind: Partial<Record<LiveTalkCue, string>> = {};
const cueWrite: Partial<Record<LiveTalkCue, Promise<string | null>>> = {};

/** 16-bit mono WAV. Envelope avoids clicks. */
export function buildLiveTalkCueWavBase64(kind: LiveTalkCue): string {
  const tones = LIVE_TALK_CUE_TONES[kind];
  const totalMs = tones.reduce((sum, tone) => sum + tone.ms, 0) + GAP_MS * (tones.length - 1);
  const sampleCount = Math.max(1, Math.round((totalMs / 1000) * SAMPLE_RATE));
  const samples = new Int16Array(sampleCount);
  let sampleIndex = 0;
  const attack = Math.round(SAMPLE_RATE * 0.008);
  const release = Math.round(SAMPLE_RATE * 0.04);
  for (let t = 0; t < tones.length; t += 1) {
    const tone = tones[t];
    if (!tone) continue;
    const n = Math.round((tone.ms / 1000) * SAMPLE_RATE);
    for (let i = 0; i < n && sampleIndex < sampleCount; i += 1) {
      const env =
        i < attack ? i / attack : i > n - release ? Math.max(0, (n - i) / release) : 1;
      const sample = Math.sin((2 * Math.PI * tone.hz * i) / SAMPLE_RATE) * AMPLITUDE * env;
      samples[sampleIndex] = Math.max(-32767, Math.min(32767, sample * 32767));
      sampleIndex += 1;
    }
    if (t < tones.length - 1) {
      const gap = Math.round((GAP_MS / 1000) * SAMPLE_RATE);
      sampleIndex = Math.min(sampleCount, sampleIndex + gap);
    }
  }
  return encodePcm16Wav(samples, SAMPLE_RATE);
}

async function cueFileUri(kind: LiveTalkCue): Promise<string | null> {
  const cached = cueUriByKind[kind];
  if (cached) return cached;
  const inflight = cueWrite[kind];
  if (inflight) return inflight;
  const write = (async () => {
    if (!cacheDirectory) return null;
    const path = `${cacheDirectory}recall-live-talk-${kind}.wav`;
    await writeAsStringAsync(path, buildLiveTalkCueWavBase64(kind), {
      encoding: EncodingType.Base64,
    });
    cueUriByKind[kind] = path;
    return path;
  })();
  cueWrite[kind] = write;
  try {
    return await write;
  } finally {
    delete cueWrite[kind];
  }
}

function releaseCuePlayer(): void {
  const current = cuePlayer;
  cuePlayer = null;
  if (!current) return;
  try {
    current.remove();
  } catch {
    /* best-effort */
  }
}

/**
 * ChatGPT-style open/close chime + haptic.
 * Never leave an expo-audio player alive into WebRTC: a leftover player
 * keeps the session in playback and the assistant has no speaker.
 * Do not call setAudioModeAsync.
 */
export async function playLiveTalkCue(kind: LiveTalkCue): Promise<void> {
  if (kind === "start") notifySuccess();
  else tap();

  const Audio = loadExpoAudio();
  if (!Audio) return;
  const epoch = ++cueEpoch;
  try {
    const uri = await cueFileUri(kind);
    if (!uri || epoch !== cueEpoch) return;
    releaseCuePlayer();
    const player = Audio.createAudioPlayer(uri) as CuePlayer;
    cuePlayer = player;
    player.play();
    await new Promise<void>((resolve) => {
      setTimeout(resolve, liveTalkCueDurationMs(kind) + CUE_RELEASE_PAD_MS);
    });
  } catch {
    /* UI cue is best-effort; Live Talk must still connect. */
  } finally {
    if (epoch === cueEpoch) releaseCuePlayer();
  }
}
