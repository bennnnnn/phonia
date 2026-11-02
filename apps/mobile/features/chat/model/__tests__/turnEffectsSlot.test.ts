import type { Message } from "@/lib/api";
import type { ChatTurnCommand } from "@/features/chat/model/chatTurnCore";
import { createTurnEffectsSlot } from "@/features/chat/model/turnEffectsSlot";

/** Commands of a step taken before the chat's effects arrive wait for them, in order. */
const add = (id: string): ChatTurnCommand => ({ type: "messages", update: (rows) => [...rows, { id } as Message] });

type List = { rows: Message[] };
function run(commands: readonly ChatTurnCommand[], list: List) {
  for (const command of commands) if (command.type === "messages") list.rows = command.update(list.rows);
}

describe("the chat turn's effects slot", () => {
  it("keeps commands until the effects arrive, then runs them in order", () => {
    const slot = createTurnEffectsSlot<List>(run);
    const list: List = { rows: [] };
    slot.run([add("a")]);
    slot.run([add("b"), add("c")]);
    expect(slot.current).toBeNull();
    slot.attach(list);
    expect(list.rows.map((row) => row.id)).toEqual(["a", "b", "c"]);
  });

  it("runs at once once the effects are there, and never runs a kept command twice", () => {
    const slot = createTurnEffectsSlot<List>(run);
    const list: List = { rows: [] };
    slot.run([add("a")]);
    slot.attach(list);
    slot.run([add("b")]);
    slot.attach(list);
    expect(list.rows.map((row) => row.id)).toEqual(["a", "b"]);
  });
});
