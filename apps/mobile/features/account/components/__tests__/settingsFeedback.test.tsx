import { fireEvent, render } from "@testing-library/react-native";

import { FieldSheet } from "@/ui/overlay/FieldSheet";
import { SettingsMenuRow, SettingsSwitchRow } from "@/features/account/components/settingsUi";

jest.mock("expo-router", () => ({ Redirect: () => null, router: { push: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ token: "token" }) }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/ui/overlay/Sheet", () => {
  const { View: RNView } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Sheet: ({
      children,
      visible,
    }: {
      children: React.ReactNode;
      visible?: boolean;
    }) => (visible ? <RNView>{children}</RNView> : null),
  };
});

describe("settings action feedback", () => {
  it("replaces a saving switch with row-level progress", async () => {
    const { getByRole, queryByRole } = await render(
      <SettingsSwitchRow
        title="Memory"
        value
        disabled
        busy
        onValueChange={jest.fn()}
      />,
    );

    expect(getByRole("progressbar")).toBeOnTheScreen();
    expect(queryByRole("switch")).toBeNull();
  });

  it("binds the visible title to the native switch", async () => {
    const onValueChange = jest.fn();
    const { getByLabelText, getByRole } = await render(
      <SettingsSwitchRow
        title="Memory"
        value
        onValueChange={onValueChange}
      />,
    );

    const sw = getByRole("switch");
    expect(sw).toBe(getByLabelText("Memory"));
    expect(sw.props.accessibilityState).toEqual(
      expect.objectContaining({ checked: true, disabled: false }),
    );
  });

  it("marks choice rows busy without hiding their current value", async () => {
    const { getByText, getByRole, queryByTestId } = await render(
      <SettingsMenuRow
        title="Tone"
        value="Balanced"
        options={[{ key: "balanced", label: "Balanced" }]}
        selectedKey="balanced"
        disabled
        busy
        onSelect={jest.fn()}
      />,
    );

    expect(getByText("Balanced")).toBeOnTheScreen();
    expect(queryByTestId("select-menu")).toBeNull();
    expect(getByRole("button").props.accessibilityState).toEqual({
      expanded: false,
      disabled: true,
      busy: true,
    });
  });

  it("opens choices in a popup instead of expanding inside the card", async () => {
    const onSelect = jest.fn();
    const { getByTestId, getByLabelText, queryByTestId, queryByText } = await render(
      <SettingsMenuRow
        title="Tone"
        value="Casual"
        options={[
          { key: "funny", label: "Funny" },
          { key: "casual", label: "Casual" },
        ]}
        selectedKey="casual"
        onSelect={onSelect}
      />,
    );

    expect(queryByTestId("select-menu")).toBeNull();
    await fireEvent.press(getByLabelText("Tone, Casual"));
    expect(getByTestId("select-menu")).toBeOnTheScreen();
    expect(queryByText("Funny")).toBeOnTheScreen();
    await fireEvent.press(getByLabelText("Funny"));
    expect(onSelect).toHaveBeenCalledWith("funny");
  });

  it("locks the field editor while its save is pending", async () => {
    const { getByLabelText, getByPlaceholderText } = await render(
      <FieldSheet
        visible
        title="Name"
        value="Ada"
        placeholder="Your name"
        onChangeText={jest.fn()}
        onClose={jest.fn()}
        onSave={jest.fn()}
        saving
      />,
    );

    expect(getByPlaceholderText("Your name").props.editable).toBe(false);
    expect(getByLabelText("settings.save").props.accessibilityState).toEqual({
      disabled: true,
      busy: true,
    });
  });
});
