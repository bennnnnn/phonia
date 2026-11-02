import { fireEvent, render } from "@testing-library/react-native";

import { SegmentedControl } from "../SegmentedControl";

const SIZES = [
  { key: "small", label: "Small" },
  { key: "medium", label: "Medium" },
  { key: "large", label: "Large" },
] as const;

describe("SegmentedControl", () => {
  it("checks the current choice and reports a new one", async () => {
    const onChange = jest.fn();
    const view = await render(
      <SegmentedControl segments={SIZES} value="medium" onChange={onChange} accessibilityLabel="Text size" />,
    );
    expect(view.getByRole("radio", { name: "Medium" }).props.accessibilityState).toEqual({ checked: true });
    expect(view.getByRole("radio", { name: "Large" }).props.accessibilityState).toEqual({ checked: false });

    await fireEvent.press(view.getByRole("radio", { name: "Large" }));
    expect(onChange).toHaveBeenCalledWith("large");
    await fireEvent.press(view.getByRole("radio", { name: "Medium" }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("sizes the thumb to one segment once laid out", async () => {
    const view = await render(<SegmentedControl segments={SIZES} value="small" onChange={jest.fn()} />);
    expect(view.queryByTestId("segmented-thumb")).toBeNull();
    await fireEvent(view.getByTestId("segmented"), "layout", {
      nativeEvent: { layout: { width: 308, height: 48, x: 0, y: 0 } },
    });
    expect(view.getByTestId("segmented-thumb")).toHaveStyle({ width: 100 });
  });
});
