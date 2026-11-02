/**
 * A reply streams into a row and the same row draws it once the turn ends:
 * nothing in it is created again at `done` (the bubble, its markdown, its
 * formulas), its action row and follow-up questions land in that same update,
 * and nothing waits for a settle timer.
 */
import { Fragment } from "react";
import { act, render } from "@testing-library/react-native";

import { useChatMessageList } from "@/features/chat/hooks/useChatMessageList";
import type { Message } from "@/lib/api";
import { messageListKey } from "@/lib/messageListLayout";
import { publishStreamingDraft } from "@/features/chat/model/streamingDraftStore";

const mockMounts = new Map<string, number>();

jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: "LinkPreviewCard" }));
// The emoji setting is read from the signed-in user; these rows have none.
jest.mock("@/contexts/AuthContext", () => ({ useAuthOptional: () => null }));
jest.mock("@/features/chat/components/MessageActions", () => {
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    AssistantActions: () => <View testID="assistant-actions" />,
    UserActions: () => null,
    MESSAGE_ACTION_ROW_HEIGHT: 44,
  };
});
jest.mock("@/features/suggestions/components/RelatedPromptLines", () => {
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  return { RelatedPromptLines: () => <View testID="related-prompts" /> };
});
jest.mock("@/features/chat/components/SettingsProposalCard", () => ({ SettingsProposalCard: () => null }));
jest.mock("@/features/todos/components/ReminderProposalCard", () => ({ ReminderProposalCard: () => null }));
jest.mock("@/components/rich/PlacesListBlock", () => ({ PlacesListBlock: () => null }));
jest.mock("@/features/attachments/components/ChatMessageImageStrip", () => ({ ChatMessageImageStrip: () => null }));
jest.mock("@/features/images/components/ImageGenPlaceholder", () => ({ ImageGenPlaceholder: () => null }));
jest.mock("@/ui/feedback/ActionShimmer", () => ({ ActionShimmer: () => null }));
jest.mock("@/features/chat/components/SearchSourcesStack", () => ({ SearchSourcesStack: () => null }));
jest.mock("@/features/chat/components/RecallTypingIndicator", () => ({ RecallTypingIndicator: () => null }));
jest.mock("@/features/chat/components/UserMessageContent", () => ({ UserMessageContent: () => null }));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn(), selection: jest.fn() }));
jest.mock("@/components/rich/MathText", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  const { useEffect: useMountEffect } = jest.requireActual<typeof import("react")>("react");
  return {
    MathText: ({ latex }: { latex: string }) => {
      useMountEffect(() => {
        mockMounts.set(latex, (mockMounts.get(latex) ?? 0) + 1);
      }, []);
      return <Text>{latex}</Text>;
    },
  };
});

const PARAGRAPH = "and the next step follows from the one before it ".repeat(8).trim();
const REPLY = [
  `Start from $a^2 + b^2$. ${PARAGRAPH}.`,
  "",
  `Then $c^2$ is the sum. ${PARAGRAPH}.`,
  "",
  "- First $p+1$ point",
  "- Second $p+2$ point",
  "",
  "So the length is $c = 5$.",
].join("\n");

const user = {
  id: "u-1",
  role: "user",
  content: "Why?",
  model: null,
  created_at: "2026-10-01T10:00:00Z",
} as Message;
const live = {
  id: "streaming",
  renderKey: "stream-1",
  role: "assistant",
  content: "",
  model: null,
  created_at: "2026-10-01T10:00:01Z",
} as Message;

function Rows({ messages, streaming }: { messages: Message[]; streaming: boolean }) {
  const { renderItem } = useChatMessageList({
    messages,
    streaming,
    finalizing: false,
    selectedModel: "free-chat",
    highlightedMessageId: null,
    sendingMessageId: null,
    setMenuVisible: () => {},
    regenerateResponse: () => {},
    handleFeedback: () => {},
    onSelectSuggestion: () => {},
  });
  // As FlashList does: one cell per key, the row inside it.
  return (
    <>
      {messages.map((item, index) => (
        <Fragment key={messageListKey(item)}>{renderItem({ item, index })}</Fragment>
      ))}
    </>
  );
}

beforeEach(() => {
  jest.useFakeTimers();
  mockMounts.clear();
  publishStreamingDraft(null);
});
afterEach(() => {
  publishStreamingDraft(null);
  jest.useRealTimers();
});

async function streamReply() {
  const view = await render(<Rows messages={[user, live]} streaming />);
  for (let end = 30; end < REPLY.length + 30; end += 30) {
    const content = REPLY.slice(0, Math.min(end, REPLY.length));
    await act(async () => {
      // Past the draft's ~30 fps throttle, so each flush draws at once.
      jest.advanceTimersByTime(40);
      publishStreamingDraft({ content });
    });
  }
  return view;
}

describe("a reply's row from its first token to `done`", () => {
  it("draws the saved reply in the row it streamed into, creating nothing again", async () => {
    const view = await streamReply();
    const mountedWhileStreaming = Object.fromEntries(mockMounts);
    expect(Object.keys(mountedWhileStreaming)).toEqual(
      expect.arrayContaining(["c^2", "p+1", "p+2", "c = 5"]),
    );
    const firstParagraph = view.getByLabelText(/^Start from/);
    expect(view.queryByTestId("assistant-actions")).toBeNull();

    const saved = { ...live, id: "m-1", content: REPLY, model: "free-chat", related_prompts: ["Why squares?"] };
    await act(async () => {
      publishStreamingDraft(null);
      view.rerender(<Rows messages={[user, saved]} streaming={false} />);
    });

    expect(Object.fromEntries(mockMounts)).toEqual(mountedWhileStreaming);
    expect(view.getByLabelText(/^Start from/)).toBe(firstParagraph);
    // The action row and the follow-up questions land with the saved reply, not after a hold.
    expect(view.getByTestId("assistant-actions")).toBeTruthy();
    expect(view.getByTestId("related-prompts")).toBeTruthy();

    // No settle timer is left to change anything later.
    await act(async () => {
      jest.advanceTimersByTime(1_000);
    });
    expect(Object.fromEntries(mockMounts)).toEqual(mountedWhileStreaming);
    expect(view.getByLabelText(/^Start from/)).toBe(firstParagraph);
    await view.unmount();
  });
});

describe("follow-up questions", () => {
  it("are not shown under a reply that asks with a card", async () => {
    const card = JSON.stringify({
      when: "first",
      questions: [
        { id: "budget", label: "Budget", question: "What is your budget?", options: ["Low", "High"], multi: false },
      ],
    });
    const asks = {
      ...live,
      id: "m-2",
      content: `Two quick questions:\n\n\`\`\`clarify\n${card}\n\`\`\``,
      model: "free-chat",
      related_prompts: ["What is your budget?"],
    };
    const view = await render(<Rows messages={[user, asks]} streaming={false} />);
    expect(view.queryByTestId("related-prompts")).toBeNull();
    await view.unmount();
  });
});
