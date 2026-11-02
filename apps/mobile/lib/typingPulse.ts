type TypingPulseKind = "calm" | "active" | "busy";

type PulseProfile = {
  minScale: number;
  maxScale: number;
  minOpacity: number;
  maxOpacity: number;
  /** Half-cycle duration in ms (matches Motion.duration.*). */
  halfMs: number;
};

export const PULSE_PROFILES: Record<TypingPulseKind, PulseProfile> = {
  // preparing / remembering / reading — idle wait (Motion.duration.soft)
  calm: {
    minScale: 0.92,
    maxScale: 1.04,
    minOpacity: 0.45,
    maxOpacity: 0.85,
    halfMs: 700,
  },
  // thinking / composing — model working (Motion.duration.breathe)
  active: {
    minScale: 0.9,
    maxScale: 1.1,
    minOpacity: 0.5,
    maxOpacity: 1,
    halfMs: 600,
  },
  // searching / calculating / tools — heavier work (Motion.duration.pulse)
  busy: {
    minScale: 0.88,
    maxScale: 1.16,
    minOpacity: 0.55,
    maxOpacity: 1,
    halfMs: 450,
  },
};

/** Map server stream status phase → pulse intensity. */
export function typingPulseKindForPhase(phase?: string | null): TypingPulseKind {
  switch ((phase ?? "").trim().toLowerCase()) {
    case "searching":
    case "calculating":
    case "physics":
    case "finding_photo":
      return "busy";
    case "thinking":
    case "composing":
    case "planning":
      return "active";
    default:
      // preparing, remembering, reading_files, unknown
      return "calm";
  }
}
