/** Collapse timed animations when Reduce Motion is on. */
export function motionMs(ms: number, reduceMotion: boolean): number {
  return reduceMotion ? 0 : ms;
}
