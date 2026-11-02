import type { ChatTurnCommand } from "@/features/chat/model/chatTurnCore";

/**
 * Where a turn's commands go. The effects arrive in useChat's first layout effect; a step
 * taken before then (a writer's layout effect runs before its parent's) keeps its commands
 * until they arrive, then runs them in order, instead of dropping them.
 */
type TurnEffectsSlot<Effects> = {
  readonly current: Effects | null;
  run: (commands: readonly ChatTurnCommand[]) => void;
  attach: (effects: Effects) => void;
};

export function createTurnEffectsSlot<Effects>(
  runCommands: (commands: readonly ChatTurnCommand[], effects: Effects) => void,
): TurnEffectsSlot<Effects> {
  let current: Effects | null = null;
  let waiting: ChatTurnCommand[] = [];
  return {
    get current() {
      return current;
    },
    run(commands) {
      if (current) runCommands(commands, current);
      else waiting.push(...commands);
    },
    attach(effects) {
      current = effects;
      if (waiting.length === 0) return;
      const queued = waiting;
      waiting = [];
      runCommands(queued, effects);
    },
  };
}
