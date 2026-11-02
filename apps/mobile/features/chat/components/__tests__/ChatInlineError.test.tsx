import { fireEvent, render } from "@testing-library/react-native";

import { ChatInlineError } from "@/features/chat/components/ChatInlineError";

jest.mock("@/ui/icons/Icon", () => ({
  Icon: () => null,
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "common.retry": "Retry",
        "chat.regenerate": "Regenerate",
        "chat.regenerate_a11y": "Regenerate response",
        "chat.restore_draft": "Restore draft",
        "settings.model": "Models",
        "chat.error_dismiss_a11y": "Dismiss error",
      })[key] ?? key,
  }),
}));

jest.mock("@/lib/theme", () => ({
  useTheme: () => ({
    isDark: false,
    surface: "#fff",
    warning: "#f90",
    text: "#111",
    primary: "#36f",
    onPrimary: "#fff",
    textTertiary: "#777",
  }),
}));

describe("ChatInlineError", () => {
  it("exposes the quota upgrade CTA as a labeled button", async () => {
    const onUpgrade = jest.fn();
    const view = await render(
      <ChatInlineError
        error={{ kind: "quota", message: "Daily limit reached." }}
        upgradeLabel="Go Pro"
        onUpgrade={onUpgrade}
        onDismiss={jest.fn()}
        bottom={20}
      />,
    );

    fireEvent.press(view.getByRole("button", { name: "Go Pro" }));
    expect(onUpgrade).toHaveBeenCalledTimes(1);
  });

  it("offers Retry instead of Stop for a rejected unsaved message", async () => {
    const onRetry = jest.fn();
    const onStop = jest.fn();
    const view = await render(
      <ChatInlineError
        error={{ kind: "send_rejected", message: "Message wasn’t sent. Wait a moment, then retry." }}
        onRetry={onRetry}
        onStop={onStop}
        onDismiss={jest.fn()}
        bottom={20}
      />,
    );
    expect(view.queryByTestId("chat-busy-stop")).toBeNull();
    fireEvent.press(view.getByTestId("chat-error-retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onStop).not.toHaveBeenCalled();
  });

  it("keeps Stop available for an active reply", async () => {
    const onStop = jest.fn();
    const view = await render(
      <ChatInlineError
        error={{ kind: "busy", message: "Still generating" }}
        onRetry={jest.fn()}
        onStop={onStop}
        onDismiss={jest.fn()}
        bottom={20}
      />,
    );
    expect(view.queryByTestId("chat-error-retry")).toBeNull();
    fireEvent.press(view.getByTestId("chat-busy-stop"));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("offers one-tap regenerate for a failed saved reply", async () => {
    const onRetry = jest.fn();
    const view = await render(
      <ChatInlineError
        error={{ kind: "generic", message: "Connection lost. Try again." }}
        onRetry={onRetry}
        onDismiss={jest.fn()}
        bottom={20}
      />,
    );

    expect(view.queryByTestId("chat-error-retry")).toBeNull();
    fireEvent.press(view.getByTestId("chat-error-regenerate"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("opens model selection when the active model is unavailable", async () => {
    const onChangeModel = jest.fn();
    const view = await render(
      <ChatInlineError
        error={{ kind: "model_unavailable", message: "Pick a different model." }}
        onChangeModel={onChangeModel}
        onDismiss={jest.fn()}
        bottom={20}
      />,
    );

    fireEvent.press(view.getByTestId("chat-error-change-model"));
    expect(onChangeModel).toHaveBeenCalledTimes(1);
  });
});


it("offers explicit draft restoration for an unsaved file with no generic Retry or Stop", async () => {
  const onRetry = jest.fn();
  const view = await render(<ChatInlineError
    error={{ kind: "attachment_rejected", message: "Message wasn’t sent." }}
    onRetry={onRetry} onStop={jest.fn()} onDismiss={jest.fn()} bottom={20}
  />);
  expect(view.queryByTestId("chat-error-retry")).toBeNull();
  expect(view.queryByTestId("chat-busy-stop")).toBeNull();
  fireEvent.press(view.getByRole("button", { name: "Restore draft" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});
