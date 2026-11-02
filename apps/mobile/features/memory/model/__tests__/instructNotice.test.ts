import { instructNotice } from "@/features/memory/model/instructNotice";

const t = (key: string) => key;

describe("instructNotice", () => {
  it("passes on the reply when an edit landed", () => {
    expect(instructNotice({ reply: "Saved.", applied: 1, dropped: 0 }, t)).toEqual({
      landed: true,
      message: "Saved.",
    });
    expect(instructNotice({ reply: "", applied: 2, dropped: 0 }, t).message).toBe("memory.instruct_done");
  });

  it("never claims a change when nothing landed", () => {
    expect(instructNotice({ reply: "Added your goal.", applied: 0, dropped: 1 }, t)).toEqual({
      landed: false,
      message: "memory.instruct_nothing",
    });
    expect(instructNotice({ reply: "", applied: 0, dropped: 0 }, t).message).toBe("memory.instruct_nothing");
  });

  it("keeps the model's sentence when it proposed nothing, as a warning", () => {
    expect(
      instructNotice({ reply: "That isn't something to remember.", applied: 0, dropped: 0 }, t),
    ).toEqual({ landed: false, message: "That isn't something to remember." });
  });
});
