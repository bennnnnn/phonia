/** What the memory box says after an edit the server answered, and whether it clears. */

type InstructResult = { reply: string; applied: number; dropped: number };

type InstructNotice = { landed: boolean; message: string };

/**
 * An edit that changed nothing is a warning, and the words stay in the box to try again.
 * The model writes its sentence before the edits are checked, so when edits were dropped
 * ("Added your goal." with nothing saved) the phone says what really happened.
 */
export function instructNotice(result: InstructResult, t: (key: string) => string): InstructNotice {
  if (result.applied > 0) {
    return { landed: true, message: result.reply || t("memory.instruct_done") };
  }
  const honest = result.dropped > 0 || !result.reply;
  return { landed: false, message: honest ? t("memory.instruct_nothing") : result.reply };
}
