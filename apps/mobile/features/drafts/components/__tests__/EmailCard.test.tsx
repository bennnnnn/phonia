import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { flushEmailDrafts } from "@/features/drafts/model/emailDraftFlush";

import { EmailCard } from "@/features/drafts/components/EmailCard";
import {
  AssistantMessageScope,
  EmailDraftPersistProvider,
} from "@/features/drafts/context/emailDraftPersist";

jest.mock("react-native-svg", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    __esModule: true,
    default: View,
    Svg: View,
    Path: View,
    Circle: View,
    Rect: View,
    Line: View,
    Polyline: View,
    Polygon: View,
    Ellipse: View,
    Defs: View,
    Mask: View,
  };
});

const MESSAGE_ID = "11111111-1111-1111-1111-111111111111";

describe("EmailCard persist", () => {
  it("flush waits for the in-flight save; failure keeps the edit available for retry", async () => {
    let resolveSave!: (ok: boolean) => void;
    const save = jest.fn(() => new Promise<boolean>((resolve) => { resolveSave = resolve; }));
    const ui = await render(
      <EmailDraftPersistProvider save={save}>
        <AssistantMessageScope messageId={MESSAGE_ID}>
          <EmailCard draft={{ subject: "Old", body: "Hello" }} />
        </AssistantMessageScope>
      </EmailDraftPersistProvider>,
    );
    await fireEvent.press(ui.getByLabelText("chat.email_card_edit"));
    await fireEvent.changeText(ui.getByPlaceholderText("chat.email_card_subject_placeholder"), "New");
    await fireEvent.press(ui.getByLabelText("chat.email_card_done"));
    let flushed = false;
    const flushing = flushEmailDrafts().then((ok) => { flushed = true; return ok; });
    await act(async () => { await Promise.resolve(); });
    expect(flushed).toBe(false);
    expect(save).toHaveBeenCalledTimes(1);
    await act(async () => { resolveSave(false); });
    expect(await flushing).toBe(false);
    expect(ui.getByPlaceholderText("chat.email_card_subject_placeholder").props.value).toBe("New");
    expect(ui.getByLabelText("chat.email_card_done")).toBeTruthy();
  });

  it("saves the current draft when Done is pressed", async () => {
    const save = jest.fn().mockResolvedValue(true);
    const { getByLabelText, getByPlaceholderText } = await render(
      <EmailDraftPersistProvider save={save}>
        <AssistantMessageScope messageId={MESSAGE_ID}>
          <EmailCard
            draft={{ to: "a@b.com", subject: "Hi", body: "Hello" }}
          />
        </AssistantMessageScope>
      </EmailDraftPersistProvider>,
    );

    await fireEvent.press(getByLabelText("chat.email_card_edit"));
    await fireEvent.changeText(getByPlaceholderText("chat.email_card_subject_placeholder"), "Shorter");
    await fireEvent.press(getByLabelText("chat.email_card_done"));

    await waitFor(() => {
      expect(save).toHaveBeenCalledWith(MESSAGE_ID, {
        to: "a@b.com",
        subject: "Shorter",
        body: "Hello",
      });
    });
  });

  it("does not persist a streaming placeholder id", async () => {
    const save = jest.fn().mockResolvedValue(true);
    const { getByLabelText, getByPlaceholderText } = await render(
      <EmailDraftPersistProvider save={save}>
        <AssistantMessageScope messageId="streaming">
          <EmailCard
            draft={{ to: "a@b.com", subject: "Hi", body: "Hello" }}
          />
        </AssistantMessageScope>
      </EmailDraftPersistProvider>,
    );

    await fireEvent.press(getByLabelText("chat.email_card_edit"));
    await fireEvent.changeText(getByPlaceholderText("chat.email_card_subject_placeholder"), "Shorter");
    await fireEvent.press(getByLabelText("chat.email_card_done"));

    await waitFor(() => {
      expect(getByLabelText("chat.email_card_edit")).toBeTruthy();
    });
    expect(save).not.toHaveBeenCalled();
  });
});
