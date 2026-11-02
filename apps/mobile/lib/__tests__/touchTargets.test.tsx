/**
 * Small press targets reach 44pt (Apple HIG, WCAG 2.5.5) with hitSlop where the drawing
 * stays smaller. Heights are read from styles at the default text size (support/touchTarget).
 */
import { render } from "@testing-library/react-native";

import { ChatQuotaNudge } from "@/features/chat/components/ChatQuotaNudge";
import { makeChatScreenStyles } from "@/features/chat/components/chatScreenStyles";
import { lightTheme } from "@/lib/theme";
import { SearchField } from "@/ui/controls/SearchField";
import { SegmentedControl } from "@/ui/controls/SegmentedControl";

import { touchTargetHeight } from "./support/touchTarget";

const MIN_TOUCH = 44;

describe("touch targets", () => {
  it("the quota nudge's Upgrade and close reach 44pt", async () => {
    const view = await render(
      <ChatQuotaNudge
        styles={makeChatScreenStyles(lightTheme)}
        theme={lightTheme}
        bottomOffset={0}
        usedPct={80}
        onUpgrade={jest.fn()}
        onDismiss={jest.fn()}
      />,
    );
    const [, upgrade] = view.getAllByRole("button");
    expect(touchTargetHeight(upgrade!)).toBeGreaterThanOrEqual(MIN_TOUCH);
    expect(touchTargetHeight(view.getByLabelText("common.cancel"))).toBeGreaterThanOrEqual(MIN_TOUCH);
  });

  it("a search field's clear button reaches 44pt", async () => {
    const view = await render(
      <SearchField value="cats" onChangeText={jest.fn()} placeholder="Search" onClear={jest.fn()} clearAccessibilityLabel="Clear" />,
    );
    expect(touchTargetHeight(view.getByLabelText("Clear"))).toBeGreaterThanOrEqual(MIN_TOUCH);
  });

  it("a segment reaches 44pt", async () => {
    const view = await render(
      <SegmentedControl
        segments={[
          { key: "a", label: "A" },
          { key: "b", label: "B" },
        ]}
        value="a"
        onChange={jest.fn()}
      />,
    );
    expect(touchTargetHeight(view.getByRole("radio", { name: "A" }))).toBeGreaterThanOrEqual(MIN_TOUCH);
  });
});
