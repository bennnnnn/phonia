/**
 * Which chat turns report `chat_ttft` and `chat_turn_outcome`: one in five. Both
 * measure shares and spreads, which a sample keeps; every turn sending both was two
 * requests and two rows per turn (code-health audit NET-15). Each event carries its
 * rate as `sample_rate`, so a count can be scaled back up.
 */
export const CHAT_EVENT_SAMPLE_RATE = 0.2;

/** Production only (plain Jest/Node has no __DEV__), and there one turn in five. */
export function sampleChatEvent(): boolean {
  if (typeof __DEV__ !== "undefined" && __DEV__) return false;
  return Math.random() < CHAT_EVENT_SAMPLE_RATE;
}
