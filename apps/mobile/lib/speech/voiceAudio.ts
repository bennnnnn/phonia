/** Guarded loader for expo-audio — probe the native registry before requiring JS. */

import type { PermissionResponse } from "expo-audio";
import { requireOptionalNativeModule } from "expo-modules-core";
import { deleteAsync, getInfoAsync, readAsStringAsync } from "expo-file-system/legacy";


type ExpoAudioModule = typeof import("expo-audio");

/** undefined = not loaded yet; null = unavailable or failed to load. */
let audioModule: ExpoAudioModule | null | undefined;

const MIN_RECORDING_BYTES = 800;

const MIME_BY_EXT: Record<string, string> = {
  m4a: "audio/m4a",
  mp4: "audio/mp4",
  caf: "audio/x-caf",
  "3gp": "audio/3gpp",
  webm: "audio/webm",
  wav: "audio/wav",
};

/** Sync require keeps expo-audio in the main bundle (async import() breaks Metro module IDs).
 * Dictation works in Expo Go too; Live Talk's WebRTC is gated separately. */
export function loadExpoAudio(): ExpoAudioModule | null {
  if (audioModule === null) return null;
  if (audioModule) return audioModule;
  try {
    if (!requireOptionalNativeModule("ExpoAudio")) {
      audioModule = null;
      return null;
    }
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- sync, only once its native module is in this build
    audioModule = require("expo-audio") as ExpoAudioModule;
    return audioModule;
  } catch {
    audioModule = null;
    return null;
  }
}

export function isVoiceInputAvailable(): boolean {
  return loadExpoAudio() !== null;
}

type MeterListener = (level: number) => void;

export type VoiceRecorder = {
  stop: () => Promise<string | null>;
  subscribeMetering: (listener: MeterListener) => () => void;
};

/** Map expo-audio dB metering (-160…0) to a 0–1 visual level. */
function normalizeMetering(db?: number): number {
  if (db == null || db <= -160) return 0.12;
  const clamped = Math.max(-60, Math.min(0, db));
  return 0.1 + ((clamped + 60) / 60) * 0.9;
}

export function normalizeRecordingUri(uri: string): string {
  if (uri.startsWith("file://")) return uri;
  return `file://${uri}`;
}

export function speechUploadFromUri(uri: string): { uri: string; name: string; type: string } {
  const normalized = normalizeRecordingUri(uri);
  const fileName = normalized.split("/").pop() ?? "speech.m4a";
  const ext = fileName.includes(".") ? (fileName.split(".").pop()?.toLowerCase() ?? "m4a") : "m4a";
  const name = fileName.includes(".") ? fileName : `speech.${ext}`;
  return {
    uri: normalized,
    name,
    type: MIME_BY_EXT[ext] ?? "audio/m4a",
  };
}

async function waitForRecordingFile(uri: string, attempts = 5): Promise<number | null> {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const info = await getInfoAsync(uri);
      const size = info.exists ? (info.size ?? 0) : 0;
      if (size >= MIN_RECORDING_BYTES) return size;
    } catch {
      /* retry */
    }
    await new Promise((resolve) => setTimeout(resolve, 120));
  }
  return null;
}

export async function readRecordingBase64(uri: string): Promise<string | null> {
  const upload = speechUploadFromUri(uri);
  const size = await waitForRecordingFile(upload.uri);
  if (!size) return null;
  try {
    return await readAsStringAsync(upload.uri, { encoding: "base64" });
  } catch {
    return null;
  }
}

export async function requestVoicePermission(
  mod: ExpoAudioModule,
): Promise<PermissionResponse> {
  return mod.requestRecordingPermissionsAsync();
}

/** Switch the session to playback so TTS works after the mic (incl. silent switch). */
export async function preparePlaybackAudioMode(): Promise<void> {
  const mod = loadExpoAudio();
  if (!mod) return;
  try {
    await mod.setAudioModeAsync({
      allowsRecording: false,
      playsInSilentMode: true,
    });
  } catch {
    /* native module can throw if audio is already tearing down */
  }
}

/** Composer and live talk both stop the mic before the 5MB upload cap. */
export const VOICE_MAX_RECORDING_MS = 45_000;

type RecordingPreset = {
  extension?: string;
  sampleRate?: number;
  numberOfChannels?: number;
  bitRate?: number;
  isMeteringEnabled?: boolean;
  ios?: Record<string, unknown>;
  android?: Record<string, unknown>;
  web?: Record<string, unknown>;
};

/** Expo's high-quality preset with metering on, so the mic level drives the waveform. */
export function meteredRecordingOptions(highQuality: RecordingPreset): RecordingPreset {
  return { ...highQuality, isMeteringEnabled: true };
}

let exclusiveMicStop: (() => Promise<void>) | null = null;

/** Stop dictation so WebRTC can take the mic. Do not call expo-audio
 *  setAudioModeAsync here — after read-aloud that leaves the session in
 *  playback and WebRTC capture stays silent. */
export async function yieldMicToWebRtc(): Promise<void> {
  const stop = exclusiveMicStop;
  exclusiveMicStop = null;
  if (!stop) return;
  try {
    await stop();
  } catch {
    /* WebRTC still needs the session */
  }
}

function releaseRecorder(recorder: { release?: () => void }): void {
  try {
    recorder.release?.();
  } catch {
    /* already released */
  }
}

/** Delete a recording once it has been sent or dropped: the app keeps no voice on disk. */
export async function deleteVoiceRecording(uri: string | null | undefined): Promise<void> {
  if (!uri) return;
  await deleteAsync(uri, { idempotent: true }).catch(() => undefined);
}

export async function startVoiceRecording(): Promise<VoiceRecorder | null> {
  const mod = loadExpoAudio();
  if (!mod) return null;

  await mod.setAudioModeAsync({
    allowsRecording: true,
    playsInSilentMode: true,
  });

  const recorder = new mod.AudioModule.AudioRecorder({});
  const preset = meteredRecordingOptions(mod.RecordingPresets.HIGH_QUALITY);
  await recorder.prepareToRecordAsync(
    preset as Parameters<typeof recorder.prepareToRecordAsync>[0],
  );
  recorder.record();

  const listeners = new Set<MeterListener>();
  const tick = setInterval(() => {
    if (!recorder.isRecording) return;
    try {
      const level = normalizeMetering(recorder.getStatus().metering);
      listeners.forEach((listener) => listener(level));
    } catch {
      /* best-effort metering */
    }
  }, 60);

  exclusiveMicStop = async () => {
    clearInterval(tick);
    if (recorder.isRecording) {
      await recorder.stop();
    }
  };

  return {
    stop: async () => {
      clearInterval(tick);
      if (exclusiveMicStop) exclusiveMicStop = null;
      try {
        if (recorder.isRecording) {
          await recorder.stop();
        }
      } finally {
        try {
          await preparePlaybackAudioMode();
        } catch {
          /* best-effort: TTS should not stay in record mode */
        }
      }
      const rawUri = recorder.uri;
      // The native recorder is done with; its file is the caller's to delete
      // (deleteVoiceRecording): expo-audio keeps every one (code-health audit LEAK-04).
      releaseRecorder(recorder);
      if (!rawUri) return null;
      const uri = normalizeRecordingUri(rawUri);
      const size = await waitForRecordingFile(uri);
      if (!size) {
        await deleteVoiceRecording(uri);
        return null;
      }
      return uri;
    },
    subscribeMetering: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
