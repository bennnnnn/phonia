import { addedSincePaint, mergeLocalAttachmentUris, mergeOpenedPage, paintCachedThread } from "@/features/chat/model/messageMerge";
import type { Message } from "@/lib/api";

describe("mergeLocalAttachmentUris", () => {
  it("preserves local_image_uri from the prior optimistic bubble", () => {
    const previous: Message[] = [
      {
        id: "m1",
        role: "user",
        content: "[Image: /attachments/abc/file]",
        model: null,
        local_image_uri: "file:///tmp/photo.jpg",
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    const incoming: Message[] = [
      {
        id: "m1",
        role: "user",
        content: "[Image: /attachments/abc/file]",
        model: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    const merged = mergeLocalAttachmentUris(previous, incoming);
    expect(merged[0].local_image_uri).toBe("file:///tmp/photo.jpg");
  });

  it("transfers local_image_uri when optimistic local-* id becomes a server UUID", () => {
    const previous: Message[] = [
      {
        id: "local-1",
        role: "user",
        content: "Solve the math problem in this image step by step.",
        model: null,
        local_image_uri: "file:///tmp/scan.jpg",
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "streamed-1",
        role: "assistant",
        content: "x = 2",
        model: null,
        created_at: "2026-01-01T00:00:01Z",
      },
    ];
    const incoming: Message[] = [
      {
        id: "11111111-1111-1111-1111-111111111111",
        role: "user",
        content:
          "[Image: 22222222-2222-2222-2222-222222222222]\n\nSolve the math problem in this image step by step.",
        model: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "33333333-3333-3333-3333-333333333333",
        role: "assistant",
        content: "x = 2",
        model: null,
        created_at: "2026-01-01T00:00:01Z",
      },
    ];
    const merged = mergeLocalAttachmentUris(previous, incoming);
    expect(merged[0].local_image_uri).toBe("file:///tmp/scan.jpg");
    expect(merged[1].local_image_uri).toBeFalsy();
  });

  it("transfers local file preview when local-* id becomes a server UUID", () => {
    const previous: Message[] = [
      {
        id: "local-file",
        role: "user",
        content: "notes.pdf",
        model: null,
        local_file_uri: "file:///tmp/notes.pdf",
        local_file_name: "notes.pdf",
        local_file_content_type: "application/pdf",
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    const incoming: Message[] = [
      {
        id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        role: "user",
        content: "[File: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb]\n\nSummarize this file.",
        model: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    const merged = mergeLocalAttachmentUris(previous, incoming);
    expect(merged[0].local_file_uri).toBe("file:///tmp/notes.pdf");
    expect(merged[0].local_file_name).toBe("notes.pdf");
    expect(merged[0].local_file_content_type).toBe("application/pdf");
  });

  it("M11: preserves streamed-* assistant when server list has no assistant row", () => {
    const previous: Message[] = [
      {
        id: "u1",
        role: "user",
        content: "hi",
        model: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "streamed-100",
        role: "assistant",
        content: "Hello!",
        model: "free-chat",
        created_at: "2026-01-01T00:00:01Z",
      },
    ];
    const incoming: Message[] = [
      {
        id: "u1",
        role: "user",
        content: "hi",
        model: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    const merged = mergeLocalAttachmentUris(previous, incoming);
    expect(merged).toHaveLength(2);
    expect(merged[1].id).toBe("streamed-100");
    expect(merged[1].content).toBe("Hello!");
  });

  it("M11: drops streamed-* assistant when server list has a persisted assistant", () => {
    const previous: Message[] = [
      {
        id: "u1",
        role: "user",
        content: "hi",
        model: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "streamed-100",
        role: "assistant",
        content: "Hello!",
        model: "free-chat",
        created_at: "2026-01-01T00:00:01Z",
      },
    ];
    const incoming: Message[] = [
      {
        id: "u1",
        role: "user",
        content: "hi",
        model: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        role: "assistant",
        content: "Hello!",
        model: "free-chat",
        created_at: "2026-01-01T00:00:01Z",
      },
    ];
    const merged = mergeLocalAttachmentUris(previous, incoming);
    expect(merged).toHaveLength(2);
    expect(merged[1].id).toBe("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
  });

  it("keeps the second turn's partial reply while only its user row is persisted", () => {
    const make = (id: string, role: "user" | "assistant", content: string): Message => ({
      id, role, content, model: null, created_at: "2026-01-01T00:00:00Z",
    });
    const firstTurn = [make("u1", "user", "First"), make("a1", "assistant", "First answer")];
    const user = make("u2", "user", "Second");
    const partial = make("streamed-200", "assistant", "Second answer so far");
    const previous = [...firstTurn, user, partial];
    const incoming = [...firstTurn, user];

    expect(mergeLocalAttachmentUris(previous, incoming)).toEqual(previous);
    const complete = make("a2", "assistant", "Second answer complete");
    expect(mergeLocalAttachmentUris(previous, [...incoming, complete])).toEqual([...incoming, complete]);
  });

  it("does not carry an earlier partial into a newer unanswered turn", () => {
    const make = (id: string, role: "user" | "assistant"): Message => ({
      id, role, content: id, model: null, created_at: "2026-01-01T00:00:00Z",
    });
    const firstUser = make("u1", "user");
    const latestUser = make("u2", "user");
    const previous = [firstUser, make("streamed-100", "assistant"), latestUser];
    const incoming = [firstUser, latestUser];
    expect(mergeLocalAttachmentUris(previous, incoming)).toEqual(incoming);
  });

});

const uuid = (n: number) => `0190a000-0000-7000-8000-${String(n).padStart(12, "0")}`;
const row = (id: string, role: Message["role"], content = id, extra: Partial<Message> = {}): Message => ({
  id, role, content, model: null, created_at: "2026-01-01T00:00:00Z", ...extra,
});

describe("mergeLocalAttachmentUris keeps what did not change", () => {
  it("keeps each row's object, and the list itself, when the server's copy draws the same", () => {
    const previous = [row(uuid(1), "user", "Hi"), row(uuid(2), "assistant", "Hello", { search_sources: [] })];
    const incoming = previous.map((message) => JSON.parse(JSON.stringify(message)) as Message);
    expect(mergeLocalAttachmentUris(previous, incoming)).toBe(previous);
  });

  it("swaps in only the row that changed, keeping its list key", () => {
    const previous = [row(uuid(1), "user", "Hi"), row(uuid(2), "assistant", "Hel", { renderKey: "stream-1" })];
    const incoming = [{ ...previous[0] }, row(uuid(2), "assistant", "Hello")];
    const merged = mergeLocalAttachmentUris(previous, incoming);
    expect(merged[0]).toBe(previous[0]);
    expect(merged[1]).toEqual({ ...incoming[1], renderKey: "stream-1" });
  });

  it("reads a missing field, null and undefined as the same", () => {
    const previous = [row(uuid(1), "assistant", "Hi", { feedback: null, related_prompts: undefined })];
    expect(mergeLocalAttachmentUris(previous, [row(uuid(1), "assistant", "Hi")])).toBe(previous);
  });

  it("gives a sent picture's preview only to the new row, not to an older picture already shown", () => {
    const older = row(uuid(1), "user", "[Image: /attachments/a/file]");
    const previous = [older, row(uuid(2), "assistant"), row("local-3", "user", "Look", { local_image_uri: "file:///new.jpg" })];
    const saved = row(uuid(3), "user", "[Image: /attachments/b/file]\n\nLook");
    const merged = mergeLocalAttachmentUris(previous, [{ ...older }, row(uuid(2), "assistant"), saved, row(uuid(4), "assistant")]);
    expect(merged[0]).toBe(older);
    expect(merged[2].local_image_uri).toBe("file:///new.jpg");
  });
});

describe("mergeOpenedPage", () => {
  const cached = [row(uuid(1), "user", "Hi"), row(uuid(2), "assistant", "Hello")];
  const painted = new Set(cached.map((message) => message.id));
  const sent = row("local-9", "user", "Next question");
  const streaming = row("streaming", "assistant", "");
  const fresh = (rows: Message[]) => rows.map((message) => ({ ...message }));

  it("keeps a message sent on the painted page after the page, once", () => {
    const merged = mergeOpenedPage([...cached, sent, streaming], fresh(cached), painted);
    expect(merged.map((m) => m.id)).toEqual([uuid(1), uuid(2), "local-9", "streaming"]);
    expect(merged[0]).toBe(cached[0]);
  });

  it("puts turns the cache lacked before the message sent meanwhile", () => {
    const page = [...fresh(cached), row(uuid(3), "user", "From the laptop"), row(uuid(4), "assistant", "Answer")];
    const merged = mergeOpenedPage([...cached, sent, streaming], page, painted);
    expect(merged.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4), "local-9", "streaming"]);
  });

  // The sent turn waits for the page, so the page's rows are never matched to it by their words.
  it("shows a turn the cache lacked even when it has the words of the message sent meanwhile", () => {
    const words = row("local-9", "user", "ok");
    const page = [...fresh(cached), row(uuid(3), "user", "ok"), row(uuid(4), "assistant", "Great, next step")];
    const merged = mergeOpenedPage([...cached, words, streaming], page, painted);
    expect(merged.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4), "local-9", "streaming"]);
  });

  it("shows an unanswered message from another device before the one sent here", () => {
    const page = [...fresh(cached), row(uuid(3), "user", "Typed on the laptop")];
    const merged = mergeOpenedPage([...cached, sent, streaming], page, painted);
    expect(merged.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), "local-9", "streaming"]);
  });

  it("drops a sent bubble the page holds with the reply that already landed", () => {
    const reply = row(uuid(4), "assistant", "Reply");
    const page = [...fresh(cached), row(uuid(3), "user", "Next question"), { ...reply }];
    const merged = mergeOpenedPage([...cached, sent, reply], page, painted);
    expect(merged.map((m) => m.id)).toEqual([uuid(1), uuid(2), uuid(3), uuid(4)]);
    expect(merged[3]).toBe(reply);
  });

  it("keeps a reply being regenerated out of the page", () => {
    const merged = mergeOpenedPage([cached[0], streaming], fresh(cached), painted);
    expect(merged.map((m) => m.id)).toEqual([uuid(1), "streaming"]);
  });

  it("swaps sent bubbles a kept page painted for their saved rows", () => {
    const keptRows = [row("local-1", "user", "Hi"), row(uuid(2), "assistant", "Hello")];
    const page = [row(uuid(1), "user", "Hi"), row(uuid(2), "assistant", "Hello")];
    const merged = mergeOpenedPage(keptRows, page, new Set(keptRows.map((m) => m.id)));
    expect(merged.map((m) => m.id)).toEqual([uuid(1), uuid(2)]);
    expect(merged[1]).toBe(keptRows[1]);
  });

  it("is the page when nothing was painted or sent", () => {
    const page = fresh(cached);
    expect(mergeOpenedPage([], page, new Set())).toEqual(page);
  });

  it("is the shown thread itself when the page left every row as it was", () => {
    const shown = [...cached];
    expect(mergeOpenedPage(shown, fresh(cached), painted)).toBe(shown);
  });
});

describe("addedSincePaint", () => {
  const cached = [row(uuid(1), "user", "Hi"), row(uuid(2), "assistant", "Hello")];
  const painted = new Set(cached.map((message) => message.id));
  const page = [...cached, row(uuid(3), "user", "Asked before leaving"), row(uuid(4), "assistant", "Its reply")];

  it("sees a turn sent since the paint while any of it is on screen", () => {
    expect(addedSincePaint([...cached, row("local-9", "user", "Next")], page, painted)).toBe(true);
    expect(addedSincePaint([...cached, row("streaming", "assistant", "")], page, painted)).toBe(true);
  });

  it("sees nothing once that turn is gone, or when its rows are the page's own", () => {
    expect(addedSincePaint(cached, page, painted)).toBe(false);
    expect(addedSincePaint([cached[0]], page, painted)).toBe(false);
    expect(addedSincePaint([...cached, page[2], page[3]], page, painted)).toBe(false);
  });
});

describe("paintCachedThread", () => {
  it("replaces another chat's thread outright", () => {
    const other = [row("local-1", "user", "x", { local_image_uri: "file:///other.jpg" })];
    const cachedRows = [row(uuid(1), "user", "[Image: /attachments/a/file]")];
    expect(paintCachedThread(other, cachedRows)).toBe(cachedRows);
  });

  it("keeps the same thread's rows when a repaint draws them the same", () => {
    const shown = [row(uuid(1), "user", "Hi")];
    expect(paintCachedThread(shown, [{ ...shown[0] }])).toBe(shown);
  });
});
