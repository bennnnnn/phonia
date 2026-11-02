import { fireEvent, render } from "@testing-library/react-native";

import { selection, tap } from "@/lib/haptics";
import { lightTheme } from "@/lib/theme";
import { Chip } from "../Chip";

jest.mock("@/lib/haptics", () => ({ selection: jest.fn(), tap: jest.fn() }));

describe("Chip", () => {
  it("is a 44 tall tappable suggestion", async () => {
    const onPress = jest.fn();
    const view = await render(<Chip label="Plan my week" icon="sparkles" onPress={onPress} />);
    const chip = view.getByRole("button", { name: "Plan my week" });
    expect(chip).toHaveStyle({ minHeight: 44, backgroundColor: lightTheme.surface });
    await fireEvent.press(chip);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("marks a picked filter as checked and turns it indigo", async () => {
    const view = await render(
      <>
        <Chip variant="filter" accessibilityRole="radio" label="All" selected onPress={jest.fn()} />
        <Chip variant="filter" accessibilityRole="radio" label="Files" onPress={jest.fn()} />
      </>,
    );
    const all = view.getByRole("radio", { name: "All" });
    expect(all.props.accessibilityState).toEqual({ checked: true, disabled: false });
    expect(all).toHaveStyle({ backgroundColor: lightTheme.primaryLight, borderColor: lightTheme.primary });
    expect(view.getByRole("radio", { name: "Files" }).props.accessibilityState.checked).toBe(false);
  });

  it("ticks once when a filter changes, as a segment does, and not for the one already picked", async () => {
    const onPress = jest.fn();
    const view = await render(
      <>
        <Chip variant="filter" accessibilityRole="radio" label="All" selected onPress={onPress} />
        <Chip variant="filter" accessibilityRole="radio" label="Files" onPress={onPress} />
        <Chip variant="filter" accessibilityRole="tab" label="Greek" onPress={onPress} />
        <Chip label="Plan my week" onPress={onPress} />
      </>,
    );
    await fireEvent.press(view.getByRole("radio", { name: "All" }));
    expect(selection).not.toHaveBeenCalled();
    await fireEvent.press(view.getByRole("radio", { name: "Files" }));
    await fireEvent.press(view.getByRole("tab", { name: "Greek" }));
    expect(selection).toHaveBeenCalledTimes(2);
    // A suggestion chip is a send, not a selection: its action owns any haptic.
    await fireEvent.press(view.getByRole("button", { name: "Plan my week" }));
    expect(selection).toHaveBeenCalledTimes(2);
    expect(tap).not.toHaveBeenCalled();
    expect(onPress).toHaveBeenCalledTimes(4);
  });

  it("removes an added value from its own button", async () => {
    const onRemove = jest.fn();
    const view = await render(
      <Chip variant="input" label="Python" onRemove={onRemove} removeLabel="Remove Python" testID="skill" />,
    );
    expect(view.getByText("Python")).toBeTruthy();
    await fireEvent.press(view.getByRole("button", { name: "Remove Python" }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it("shows a read-only tag with a muted lead-in", async () => {
    const view = await render(<Chip variant="tag" prefix="Pay" label="$120k" testID="salary" />);
    expect(view.getByTestId("salary")).toHaveTextContent("Pay $120k");
    expect(view.queryByRole("button")).toBeNull();
  });

  it("does not press while disabled", async () => {
    const onPress = jest.fn();
    const view = await render(<Chip variant="filter" label="10 jobs" disabled onPress={onPress} />);
    await fireEvent.press(view.getByRole("button", { name: "10 jobs" }));
    expect(onPress).not.toHaveBeenCalled();
  });
});
