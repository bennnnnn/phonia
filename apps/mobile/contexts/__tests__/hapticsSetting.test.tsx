import { act, fireEvent, render } from "@testing-library/react-native";
import * as Haptics from "expo-haptics";

import { useHaptics } from "@/contexts/AppearanceContext";
import { setHapticsEnabledSnapshot } from "@/lib/haptics";
import { ListRow } from "@/ui/list/ListRow";

jest.mock("@/lib/appearancePrefs", () => ({}));
jest.mock("@/lib/accentPrefs", () => ({}));
jest.mock("@/lib/hapticsPrefs", () => ({
  getHapticsPreference: jest.fn(async () => true),
  setHapticsPreference: jest.fn(async () => undefined),
}));

/** Settings → Personalization → Haptics: a SettingsSwitchRow is this ListRow. */
function HapticsRow() {
  const haptics = useHaptics();
  return (
    <ListRow
      title="Haptics"
      switchValue={haptics.enabled}
      onSwitchChange={(next) => void haptics.setEnabled(next)}
    />
  );
}

beforeEach(() => {
  setHapticsEnabledSnapshot(true);
  jest.spyOn(Haptics, "selectionAsync").mockResolvedValue(undefined);
});
afterEach(() => jest.restoreAllMocks());

it("ticks as haptics turn off, and again once they are back on", async () => {
  const view = await render(<HapticsRow />);
  const row = () => view.getByRole("switch", { name: "Haptics" });
  await act(async () => { fireEvent.press(row()); });
  expect(row().props.accessibilityState.checked).toBe(false);
  expect(Haptics.selectionAsync).toHaveBeenCalledTimes(1);

  await act(async () => { fireEvent.press(row()); });
  expect(row().props.accessibilityState.checked).toBe(true);
  expect(Haptics.selectionAsync).toHaveBeenCalledTimes(2);
});
