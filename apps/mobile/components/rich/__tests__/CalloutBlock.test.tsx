import { render } from "@testing-library/react-native";

import { CalloutBlock } from "@/components/rich/CalloutBlock";

describe("CalloutBlock", () => {
  it("titles a one-line callout with its kind", async () => {
    const view = await render(<CalloutBlock kind="note" content="check the units" />);
    expect(view.getByText("rich.callout_note")).toBeOnTheScreen();
    expect(view.getByText("check the units")).toBeOnTheScreen();
  });

  it("keeps the kind as the title of a multi-line callout", async () => {
    const view = await render(
      <CalloutBlock kind="warning" content={"Hot surface.\nLet it cool before you touch it."} />,
    );
    expect(view.getByText("rich.callout_warning")).toBeOnTheScreen();
    // The first sentence stays in the body instead of replacing the label.
    expect(view.getByText(/Hot surface\./)).toBeOnTheScreen();
    expect(view.getByText(/Let it cool before you touch it\./)).toBeOnTheScreen();
  });
});
