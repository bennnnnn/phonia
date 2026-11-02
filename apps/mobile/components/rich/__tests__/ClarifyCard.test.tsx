import { fireEvent, render } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { ClarifyCard } from "@/components/rich/ClarifyCard";
import { ClarifyActionsProvider, ClarifyMessageScope } from "@/components/rich/clarifyContext";
import { ReplyStreaming } from "@/components/markdown/ReplyStreaming";
import { selection } from "@/lib/haptics";

jest.mock("@/lib/i18n", () => ({
  __esModule: true,
  default: {
    t: (key: string, options?: Record<string, string>) =>
      options ? `${key}|${Object.values(options).join("|")}` : key,
  },
}));
jest.mock("@/lib/haptics", () => ({ selection: jest.fn() }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

const COUNTRY = JSON.stringify({
  questions: [
    {
      id: "priority",
      label: "Main priority",
      question: "What matters most to you?",
      options: ["💰 Making money", "🌿 Quality of life", "🛡️ Safety"],
      values: ["Making money", "Quality of life", "Safety"],
    },
    {
      id: "region",
      label: "Geographic preference",
      question: "Which region are you considering?",
      options: ["🌍 Anywhere", "🇪🇺 Europe", "🌎 The Americas"],
      values: ["Anywhere", "Europe", "The Americas"],
    },
  ],
  request: "Recommend the best country for me.",
  closing: "Compare the strongest options with practical pros and cons.",
  submit: "Find my best country",
});

// A card saved before cards had a button of their own.
const INTEGRALS = JSON.stringify({
  when: "first",
  questions: [
    {
      id: "level",
      label: "Studied it before",
      question: "Have you studied integrals before?",
      options: ["No, never", "A little", "Yes, I'm revising"],
      multi: false,
    },
  ],
});

const PICKS =
  "Recommend the best country for me. Main priority: Making money. Geographic preference: " +
  "Anywhere. Compare the strongest options with practical pros and cons.";

type Setup = {
  content?: string;
  latest?: boolean;
  nextUserText?: string | null;
  busy?: boolean;
  streaming?: boolean;
  provider?: boolean;
  /** Whether the chat took the send (false: offline, say). */
  accepted?: boolean;
};

async function setup({
  content = COUNTRY,
  latest = true,
  nextUserText = null,
  busy = false,
  streaming = false,
  provider = true,
  accepted = true,
}: Setup = {}) {
  const send = jest.fn(async (_text: string) => accepted);
  let tree: ReactNode = (
    <ClarifyMessageScope latest={latest} nextUserText={nextUserText}>
      <ReplyStreaming value={streaming}>
        <ClarifyCard content={content} />
      </ReplyStreaming>
    </ClarifyMessageScope>
  );
  if (provider) {
    tree = (
      <ClarifyActionsProvider send={send} busy={busy}>
        {tree}
      </ClarifyActionsProvider>
    );
  }
  const view = await render(<>{tree}</>);
  return { view, send };
}

function checked(view: Awaited<ReturnType<typeof setup>>["view"], label: string): boolean {
  return view.getByRole("radio", { name: label }).props.accessibilityState?.checked === true;
}

describe("ClarifyCard", () => {
  it("shows every question with its choices, the first one picked, and its own button", async () => {
    const { view } = await setup();
    expect(view.getByText("What matters most to you?")).toBeTruthy();
    expect(view.getByText("🌎 The Americas")).toBeTruthy();
    expect(checked(view, "💰 Making money")).toBe(true);
    expect(checked(view, "🌍 Anywhere")).toBe(true);
    expect(checked(view, "🛡️ Safety")).toBe(false);
    expect(view.getByText("Find my best country")).toBeTruthy();
  });

  it("sends the likeliest picks at once", async () => {
    const { view, send } = await setup();
    await fireEvent.press(view.getByText("Find my best country"));
    expect(send).toHaveBeenCalledWith(PICKS);
  });

  it("sends the request, each label with its pick, then the closing", async () => {
    const { view, send } = await setup();
    await fireEvent.press(view.getByText("🛡️ Safety"));
    await fireEvent.press(view.getByText("🇪🇺 Europe"));
    await fireEvent.press(view.getByText("Find my best country"));
    expect(send).toHaveBeenCalledWith(
      "Recommend the best country for me. Main priority: Safety. Geographic preference: Europe. " +
        "Compare the strongest options with practical pros and cons.",
    );
  });

  it("ticks only when the pick changes", async () => {
    jest.mocked(selection).mockClear();
    const { view } = await setup();
    // Already picked: the card starts on the first choice.
    await fireEvent.press(view.getByText("💰 Making money"));
    expect(selection).not.toHaveBeenCalled();
    await fireEvent.press(view.getByText("🛡️ Safety"));
    await fireEvent.press(view.getByText("🛡️ Safety"));
    expect(selection).toHaveBeenCalledTimes(1);
  });

  it("keeps one pick per question", async () => {
    const { view } = await setup();
    await fireEvent.press(view.getByText("🌿 Quality of life"));
    await fireEvent.press(view.getByText("🛡️ Safety"));
    expect(checked(view, "🛡️ Safety")).toBe(true);
    expect(checked(view, "🌿 Quality of life")).toBe(false);
    expect(checked(view, "💰 Making money")).toBe(false);
    expect(checked(view, "🌍 Anywhere")).toBe(true);
  });

  it("labels the button Submit when the card names none", async () => {
    const { view, send } = await setup({ content: INTEGRALS });
    await fireEvent.press(view.getByText("clarify.submit"));
    expect(send).toHaveBeenCalledWith("Studied it before: No, never.");
  });

  it("sends once, then stays read-only with the picks ticked and no button", async () => {
    const { view, send } = await setup();
    await fireEvent.press(view.getByText("🌿 Quality of life"));
    await fireEvent.press(view.getByText("Find my best country"));
    expect(send).toHaveBeenCalledTimes(1);
    expect(view.queryByText("Find my best country")).toBeNull();
    expect(checked(view, "🌿 Quality of life")).toBe(true);
    await fireEvent.press(view.getByText("🛡️ Safety"));
    expect(checked(view, "🛡️ Safety")).toBe(false);
  });

  it("stays live when the chat refused the send, so the picks can go once it can", async () => {
    const { view, send } = await setup({ accepted: false });
    await fireEvent.press(view.getByText("🛡️ Safety"));
    await fireEvent.press(view.getByText("Find my best country"));
    expect(send).toHaveBeenCalledTimes(1);
    expect(checked(view, "🛡️ Safety")).toBe(true);
    await fireEvent.press(view.getByText("Find my best country"));
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("ticks the picks a later message sent, read-only", async () => {
    const { view, send } = await setup({
      latest: false,
      nextUserText: PICKS.replace("Making money", "Safety").replace("Anywhere", "The Americas"),
    });
    expect(view.queryByText("Find my best country")).toBeNull();
    expect(checked(view, "🛡️ Safety")).toBe(true);
    expect(checked(view, "🌎 The Americas")).toBe(true);
    expect(checked(view, "💰 Making money")).toBe(false);
    await fireEvent.press(view.getByText("💰 Making money"));
    expect(send).not.toHaveBeenCalled();
  });

  it("ticks the lines an older phone sent", async () => {
    const { view } = await setup({ content: INTEGRALS, latest: false, nextUserText: "Studied it before: A little" });
    expect(checked(view, "A little")).toBe(true);
    expect(checked(view, "No, never")).toBe(false);
  });

  it("is read-only with nothing ticked when something was typed instead", async () => {
    const { view } = await setup({ nextUserText: "Just answer" });
    expect(view.queryByText("Find my best country")).toBeNull();
    expect(checked(view, "💰 Making money")).toBe(false);
  });

  it.each([
    ["while a reply is streaming or saving", { busy: true }],
    ["while its own reply is still streaming", { streaming: true }],
  ])("shows its button but cannot be answered %s", async (_name, options) => {
    const { view, send } = await setup(options);
    await fireEvent.press(view.getByText("Find my best country"));
    await fireEvent.press(view.getByText("🛡️ Safety"));
    expect(checked(view, "🛡️ Safety")).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });

  it.each([
    ["on an older reply", { latest: false }],
    ["outside a chat", { provider: false }],
  ])("has no button and cannot be answered %s", async (_name, options) => {
    const { view, send } = await setup(options);
    expect(view.queryByText("Find my best country")).toBeNull();
    await fireEvent.press(view.getByText("🛡️ Safety"));
    expect(checked(view, "🛡️ Safety")).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });

  it("never shows a broken card's JSON", async () => {
    const { view } = await setup({ content: '{"questions": [{"question": "Which?"' });
    expect(view.toJSON()).toBeNull();
  });

  it("shows a card written as plain text as text", async () => {
    const { view } = await setup({ content: "Have you studied integrals before?" });
    expect(view.getByText("Have you studied integrals before?")).toBeTruthy();
  });
});
