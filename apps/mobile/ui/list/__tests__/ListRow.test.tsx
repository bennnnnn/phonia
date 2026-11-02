import { fireEvent, render } from "@testing-library/react-native";
import { View } from "react-native";

import { lightTheme } from "@/lib/theme";
import { ListGroup, ListSeparator } from "../ListGroup";
import { ListRow } from "../ListRow";

describe("ListRow", () => {
  it("opens from a grouped row with its value under the title", async () => {
    const onPress = jest.fn();
    const view = await render(
      <ListGroup label="Experience">
        <ListRow icon="languages" title="Language" value="English" onPress={onPress} />
        <ListSeparator />
        <ListRow icon="palette" title="Appearance" value="System" onPress={jest.fn()} />
      </ListGroup>,
    );
    expect(view.getByRole("header", { name: "Experience" })).toBeTruthy();
    const row = view.getByRole("button", { name: "Language English" });
    expect(row).toHaveStyle({ minHeight: 56, backgroundColor: lightTheme.settingsSurface });
    await fireEvent.press(row);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("toggles as a switch from the whole row", async () => {
    const onSwitchChange = jest.fn();
    const view = await render(
      <ListRow title="Quiet hours" subtitle="Mute at night" switchValue={false} onSwitchChange={onSwitchChange} />,
    );
    const row = view.getByRole("switch", { name: "Quiet hours" });
    expect(row.props.accessibilityState).toEqual({ checked: false, disabled: false });
    await fireEvent.press(row);
    expect(onSwitchChange).toHaveBeenCalledWith(true);
  });

  it("shows a spinner instead of the switch while saving", async () => {
    const view = await render(
      <ListRow title="Push" switchValue onSwitchChange={jest.fn()} busy />,
    );
    expect(view.queryByRole("switch")).toBeNull();
    expect(view.getByRole("progressbar")).toBeTruthy();
  });

  it("blocks presses while busy and reports it", async () => {
    const onPress = jest.fn();
    const view = await render(<ListRow title="Sign out" danger busy onPress={onPress} />);
    const row = view.getByRole("button");
    expect(row.props.accessibilityState).toEqual({ disabled: true, busy: true });
    await fireEvent.press(row);
    expect(onPress).not.toHaveBeenCalled();
  });

  it("puts a detail capsule on the right of a plain row", async () => {
    const view = await render(
      <ListRow appearance="plain" icon="clock" title="Time" detail="9:30 AM" detailStyle="pill" onPress={jest.fn()} />,
    );
    expect(view.getByText("9:30 AM")).toBeTruthy();
    expect(view.getByRole("button", { name: "Time 9:30 AM" })).toHaveStyle({ minHeight: 44 });
  });

  it("reads a still row with its own label and says when a popover row is open", async () => {
    const view = await render(
      <>
        <ListRow title="Plan" value="Pro" accessibilityLabel="Plan, Pro" />
        <ListRow title="Tone" value="Warm" expanded onPress={jest.fn()} />
      </>,
    );
    expect(view.getByLabelText("Plan, Pro")).toBeTruthy();
    expect(view.getByRole("button", { name: "Tone Warm" }).props.accessibilityState.expanded).toBe(true);
  });

  it("caps lines, cuts a file name in the middle and passes the touch to long press", async () => {
    const onLongPress = jest.fn();
    const view = await render(
      <ListRow
        appearance="plain"
        title="quarterly-report-final.pdf"
        subtitle="Trip planning"
        numberOfLines={1}
        ellipsizeMode="middle"
        onPress={jest.fn()}
        onLongPress={onLongPress}
        accessibilityLabel="quarterly-report-final.pdf"
        accessibilityActions={[{ name: "share", label: "Share" }]}
      />,
    );
    const title = view.getByText("quarterly-report-final.pdf");
    expect(title.props.numberOfLines).toBe(1);
    expect(title.props.ellipsizeMode).toBe("middle");
    expect(view.getByText("Trip planning").props.numberOfLines).toBe(1);
    const row = view.getByRole("button", { name: "quarterly-report-final.pdf" });
    expect(row.props.accessibilityActions).toEqual([{ name: "share", label: "Share" }]);
    await fireEvent(row, "longPress", { nativeEvent: { pageX: 5, pageY: 6 } });
    expect(onLongPress).toHaveBeenCalledWith({ nativeEvent: { pageX: 5, pageY: 6 } });
  });
});

describe("ListSeparator", () => {
  it("is a thin page-colored gap in a group and a 1pt inset line between plain rows", async () => {
    const view = await render(
      <View testID="separators">
        <ListSeparator />
        <ListSeparator appearance="plain" inset={92} />
      </View>,
    );
    const [grouped, plain] = view.getByTestId("separators").children.filter(
      (child) => typeof child !== "string",
    );
    expect(grouped).toHaveStyle({ height: 2, backgroundColor: lightTheme.bg });
    expect(plain).toHaveStyle({ height: 1, marginLeft: 92, backgroundColor: lightTheme.separator });
  });
});
