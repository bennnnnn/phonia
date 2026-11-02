import { firstReplyTitlePlan, shouldInsertDrawerRowOnLeave } from "@/features/chat/model/titleRefresh";
import type { Chat } from "@/lib/api";

function chat(id: string, title: string | null): Chat {
  return {
    id,
    title,
    model: "free-chat",
    pinned: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("shouldInsertDrawerRowOnLeave", () => {
  it("inserts when the user already sent a message", () => {
    expect(
      shouldInsertDrawerRowOnLeave([
        { role: "user" },
        { role: "assistant" },
      ]),
    ).toBe(true);
  });

  it("skips unused empty drafts", () => {
    expect(shouldInsertDrawerRowOnLeave([])).toBe(false);
    expect(shouldInsertDrawerRowOnLeave([{ role: "assistant" }])).toBe(false);
  });
});

describe("firstReplyTitlePlan", () => {
  it("uses the POST /chats body so Home send skips GET /chats/{id} for insert", () => {
    const created = chat("new", null);
    expect(firstReplyTitlePlan(created, undefined)).toEqual({
      insert: created,
      fetch: false,
      poll: true,
    });
  });

  it("uses Image when the first user turn is an attachment-only photo", () => {
    const created = chat("new", null);
    expect(
      firstReplyTitlePlan(
        created,
        undefined,
        "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]",
      ),
    ).toEqual({
      insert: { ...created, title: "Image" },
      fetch: false,
      poll: true,
    });
  });

  it("does not stamp the first user line as the title (poll for the topic job)", () => {
    const created = chat("new", null);
    const prompt = "What's still open for me to finish tonight?";
    expect(firstReplyTitlePlan(created, undefined, prompt)).toEqual({
      insert: created,
      fetch: false,
      poll: true,
    });
  });

  it("does not use a greeting as the title", () => {
    const created = chat("new", null);
    expect(firstReplyTitlePlan(created, undefined, "hi")).toEqual({
      insert: created,
      fetch: false,
      poll: true,
    });
    expect(firstReplyTitlePlan(created, undefined, "good morning")).toEqual({
      insert: created,
      fetch: false,
      poll: true,
    });
  });

  it("skips fetch and poll when the drawer row already has a title", () => {
    const listed = chat("old", "Homework");
    expect(firstReplyTitlePlan(undefined, listed)).toEqual({
      insert: listed,
      fetch: false,
      poll: false,
    });
  });

  it("prefers a manual rename over the original untitled POST response", () => {
    const listed = chat("new", "Chat");
    expect(firstReplyTitlePlan(chat("new", null), listed)).toEqual({
      insert: listed, fetch: false, poll: false,
    });
  });

  it("still polls when the stored title is Untitled", () => {
    const created = chat("new", "Untitled");
    expect(firstReplyTitlePlan(created, undefined)).toEqual({
      insert: created,
      fetch: false,
      poll: true,
    });
  });

  it("falls back to GET only when nothing is cached", () => {
    expect(firstReplyTitlePlan(undefined, undefined)).toEqual({
      insert: null,
      fetch: true,
      poll: true,
    });
  });
});
