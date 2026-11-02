import { fireEvent, render } from "@testing-library/react-native";

import { Slider } from "../Slider";

const base = {
  label: "Interest rate",
  valueText: "6.25%",
  value: 6.25,
  min: 0,
  max: 15,
  step: 0.05,
};

describe("Slider", () => {
  it("shows its label and value and speaks as an adjustable control", async () => {
    const view = await render(<Slider {...base} onChange={jest.fn()} />);
    expect(view.getByText("Interest rate")).toBeTruthy();
    expect(view.getByTestId("slider-value")).toHaveTextContent("6.25%");
    const track = view.getByTestId("slider-track");
    expect(track.props.accessibilityRole).toBe("adjustable");
    expect(track.props.accessibilityLabel).toBe("Interest rate");
    expect(track.props.accessibilityValue).toEqual({ min: 0, max: 15, now: 6.25, text: "6.25%" });
  });

  it("steps by one step for a screen reader, then lets go", async () => {
    const onChange = jest.fn();
    const onRelease = jest.fn();
    const view = await render(<Slider {...base} onChange={onChange} onRelease={onRelease} />);
    const track = view.getByTestId("slider-track");
    await fireEvent(track, "accessibilityAction", { nativeEvent: { actionName: "increment" } });
    expect(onChange).toHaveBeenLastCalledWith(6.3);
    expect(onRelease).toHaveBeenLastCalledWith(6.3);
    await fireEvent(track, "accessibilityAction", { nativeEvent: { actionName: "decrement" } });
    expect(onChange).toHaveBeenLastCalledWith(6.2);
  });

  it("does not step past its range", async () => {
    const onChange = jest.fn();
    const view = await render(
      <Slider {...base} value={15} valueText="15%" onChange={onChange} />,
    );
    await fireEvent(view.getByTestId("slider-track"), "accessibilityAction", {
      nativeEvent: { actionName: "increment" },
    });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("jumps to the marker's exact value when it is tapped", async () => {
    const onChange = jest.fn();
    const onRelease = jest.fn();
    const view = await render(
      <Slider
        {...base}
        value={1}
        valueText="1%"
        onChange={onChange}
        onRelease={onRelease}
        marker={{ value: 6.27, label: "Avg 6.27% · Oct 16", accessibilityLabel: "Average 6.27%" }}
      />,
    );
    expect(view.getByText("Avg 6.27% · Oct 16")).toBeTruthy();
    await fireEvent.press(view.getByRole("button", { name: "Average 6.27%" }));
    // The marker's own value, not the nearest step: today's average exactly.
    expect(onChange).toHaveBeenCalledWith(6.27);
    expect(onRelease).toHaveBeenCalledWith(6.27);
  });

  it("ignores a screen-reader step while disabled", async () => {
    const onChange = jest.fn();
    const view = await render(<Slider {...base} disabled onChange={onChange} />);
    await fireEvent(view.getByTestId("slider-track"), "accessibilityAction", {
      nativeEvent: { actionName: "increment" },
    });
    expect(onChange).not.toHaveBeenCalled();
    expect(view.getByTestId("slider-track").props.accessibilityState).toEqual({ disabled: true });
  });
});
