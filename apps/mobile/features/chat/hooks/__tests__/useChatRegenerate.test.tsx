import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useChatRegenerate } from "@/features/chat/hooks/useChatRegenerate";
import type { Message } from "@/lib/api";

jest.mock("@/features/chat/model/resolveClientGeoForQuery", () => ({
  resolveClientGeoForQuery: jest.fn(async () => ({ ok: true, clientGeo: null })),
}));

import { resolveClientGeoForQuery } from "@/features/chat/model/resolveClientGeoForQuery";

const resolveGeo = resolveClientGeoForQuery as jest.Mock;

function msg(role: "user" | "assistant", content: string, id: string, model?: string | null): Message {
  return {
    id,
    role,
    content,
    model: model ?? (role === "assistant" ? "free-chat" : null),
    created_at: "2026-01-01T00:00:00Z",
  } as Message;
}

type Regenerate = (model: string) => Promise<void>;

let currentRegenerate: Regenerate;
let currentRegenerating = false;

function Probe({
  messages,
  regenerateResponse,
  beginRegenerateUi,
  cancelRegenerateUi,
}: {
  messages: Message[];
  regenerateResponse: jest.Mock;
  beginRegenerateUi?: jest.Mock;
  cancelRegenerateUi?: jest.Mock;
}) {
  const result = useChatRegenerate({
    token: "tok",
    messages,
    updateUser: jest.fn(),
    regenerateResponse,
    beginRegenerateUi,
    cancelRegenerateUi,
  });
  React.useLayoutEffect(() => {
    currentRegenerate = result.regenerate;
    currentRegenerating = result.regenerating;
  }, [result]);
  return <Text>{result.regenerating ? "busy" : "idle"}</Text>;
}

describe("useChatRegenerate", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    resolveGeo.mockResolvedValue({ ok: true, clientGeo: null });
  });

  it("does not dispatch a regeneration stopped while location preparation is pending", async () => {
    let finish!: (value: { ok: boolean; clientGeo: null }) => void;
    resolveGeo.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    let active = true;
    const regenerateResponse = jest.fn();
    const cancelRegenerateUi = jest.fn();
    await render(<Probe
      messages={[msg("user", "question", "u1"), msg("assistant", "answer", "a1")]}
      regenerateResponse={regenerateResponse}
      beginRegenerateUi={jest.fn(() => () => active)}
      cancelRegenerateUi={cancelRegenerateUi}
    />);
    let pending!: Promise<void>;
    await act(async () => { pending = currentRegenerate("free-chat"); });
    active = false;
    await act(async () => { finish({ ok: true, clientGeo: null }); await pending; });
    expect(regenerateResponse).not.toHaveBeenCalled();
    expect(cancelRegenerateUi).not.toHaveBeenCalled();
  });

  it("asks for no location and sends nothing when the start was refused mid-reply", async () => {
    const regenerateResponse = jest.fn();
    await render(<Probe
      messages={[msg("user", "question", "u1"), msg("assistant", "answer", "a1")]}
      regenerateResponse={regenerateResponse}
      beginRegenerateUi={jest.fn(() => () => false)}
    />);
    await act(async () => { await currentRegenerate("free-chat"); });
    expect(resolveGeo).not.toHaveBeenCalled();
    expect(regenerateResponse).not.toHaveBeenCalled();
    expect(currentRegenerating).toBe(false);
  });

  it("regenerates a lookup photo through the stream", async () => {
    const messages: Message[] = [
      msg("user", "Show me a car.", "u1"),
      msg("assistant", "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]", "a1", "image-search-model"),
    ];
    const regenerateResponse = jest.fn();

    await act(async () => {
      render(
        <Probe
          messages={messages}
          regenerateResponse={regenerateResponse}
        />,
      );
    });

    await act(async () => {
      await currentRegenerate("free-chat");
    });

    expect(regenerateResponse).toHaveBeenCalled();
  });

  it("falls back to regenerateResponse for normal text replies", async () => {
    const messages: Message[] = [
      msg("user", "Hello", "u1"),
      msg("assistant", "Hi there!", "a1"),
    ];
    const regenerateResponse = jest.fn();

    await act(async () => {
      render(
        <Probe
          messages={messages}
          regenerateResponse={regenerateResponse}
        />,
      );
    });

    await act(async () => {
      await currentRegenerate("free-chat");
    });

    expect(regenerateResponse).toHaveBeenCalled();
  });

  it("retries a user-only failed turn without adding another user message", async () => {
    const messages = [msg("user", "My first question", "u1")];
    const regenerateResponse = jest.fn();

    await act(async () => {
      render(<Probe messages={messages} regenerateResponse={regenerateResponse} />);
    });

    await act(async () => {
      await currentRegenerate("free-chat");
    });

    expect(regenerateResponse).toHaveBeenCalledWith("free-chat", null);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({ role: "user", content: "My first question" });
  });

  it("regenerates an image-only reply through the stream (the server makes the new picture)", async () => {
    const messages: Message[] = [
      msg("user", "Generate image: a cat", "u1"),
      msg("assistant", "[Image: cat.png]", "a1"),
    ];
    const regenerateResponse = jest.fn();

    await act(async () => {
      render(<Probe messages={messages} regenerateResponse={regenerateResponse} />);
    });

    await act(async () => {
      await currentRegenerate("free-chat");
    });

    expect(regenerateResponse).toHaveBeenCalled();
  });

  it("blocks duplicate regeneration while the first request is pending", async () => {
    let finish: (() => void) | undefined;
    const regenerateResponse = jest.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    const messages = [msg("user", "Hello", "u1"), msg("assistant", "Hi", "a1")];
    await act(async () => {
      render(<Probe messages={messages} regenerateResponse={regenerateResponse} />);
    });

    let first: Promise<void> = Promise.resolve();
    await act(async () => {
      first = currentRegenerate("free-chat");
      await Promise.resolve();
      await currentRegenerate("free-chat");
    });

    expect(regenerateResponse).toHaveBeenCalledTimes(1);
    expect(currentRegenerating).toBe(true);

    await act(async () => {
      finish?.();
      await first;
    });
    expect(currentRegenerating).toBe(false);
  });

  it("shows the typing placeholder before geo resolves", async () => {
    let finishGeo: (value: { ok: true; clientGeo: null }) => void = () => undefined;
    resolveGeo.mockReturnValue(
      new Promise((resolve) => {
        finishGeo = resolve;
      }),
    );
    const beginRegenerateUi = jest.fn();
    const regenerateResponse = jest.fn();
    const messages = [msg("user", "Hello", "u1"), msg("assistant", "Hi", "a1")];
    await act(async () => {
      render(
        <Probe
          messages={messages}
          regenerateResponse={regenerateResponse}
          beginRegenerateUi={beginRegenerateUi}
        />,
      );
    });

    let regenPromise: Promise<void> = Promise.resolve();
    await act(async () => {
      regenPromise = currentRegenerate("free-chat");
      await Promise.resolve();
    });

    expect(beginRegenerateUi).toHaveBeenCalledTimes(1);
    expect(regenerateResponse).not.toHaveBeenCalled();

    await act(async () => {
      finishGeo({ ok: true, clientGeo: null });
      await regenPromise;
    });
    expect(regenerateResponse).toHaveBeenCalledWith("free-chat", null);
  });

  it("restores the prior assistant when geo is cancelled", async () => {
    resolveGeo.mockResolvedValue({ ok: false });
    const beginRegenerateUi = jest.fn();
    const cancelRegenerateUi = jest.fn();
    const regenerateResponse = jest.fn();
    const messages = [msg("user", "Hello", "u1"), msg("assistant", "Hi", "a1")];
    await act(async () => {
      render(
        <Probe
          messages={messages}
          regenerateResponse={regenerateResponse}
          beginRegenerateUi={beginRegenerateUi}
          cancelRegenerateUi={cancelRegenerateUi}
        />,
      );
    });

    await act(async () => {
      await currentRegenerate("free-chat");
    });

    expect(beginRegenerateUi).toHaveBeenCalledTimes(1);
    expect(cancelRegenerateUi).toHaveBeenCalledTimes(1);
    expect(regenerateResponse).not.toHaveBeenCalled();
  });
});
