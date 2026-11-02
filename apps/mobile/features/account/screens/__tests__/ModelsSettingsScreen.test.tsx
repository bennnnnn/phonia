import { act, fireEvent, render } from "@testing-library/react-native";

import ModelsSettingsScreen from "@/features/account/screens/ModelsSettingsScreen";

const mockUpdateUser = jest.fn();
const mockBuildModelPreferences = jest.fn(
  (_auto: boolean, modelIds: Set<string>) => [...modelIds],
);
let mockIsPro = true;
let mockAutoEnabled = true;
let mockEnabledModelIds = ["free-chat"];
let mockUpgradeVisible = false;
let mockModels = [
  {
    id: "free-chat",
    label: "Flash",
    description: "",
    tier: "flash",
    plan_access: "free",
    available: true,
    input_price_per_m: 0,
    output_price_per_m: 0,
    quota_multiplier: 1,
    healthy: true,
    latency_p50_ms: 1214,
  },
];

jest.mock("expo-router", () => ({
  Redirect: () => null,
  useFocusEffect: (cb: () => void) => cb(),
}));
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "tok",
    user: { name: "bini" },
    updateUser: mockUpdateUser,
  }),
}));
jest.mock("@/hooks/useModels", () => ({
  buildModelPreferences: (...args: [boolean, Set<string>]) => mockBuildModelPreferences(...args),
  useModels: () => ({
    models: mockModels,
    isPaid: mockIsPro,
    autoEnabled: mockAutoEnabled,
    modelEnabledSet: new Set(mockEnabledModelIds),
  }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({
  useActionFeedbackOptional: () => null,
}));
jest.mock("@/features/billing/components/UpgradeSheet", () => ({
  UpgradeSheet: ({ visible }: { visible: boolean }) => {
    mockUpgradeVisible = visible;
    return null;
  },
}));

describe("models settings", () => {
  beforeEach(() => {
    mockUpdateUser.mockReset().mockResolvedValue(undefined);
    mockBuildModelPreferences.mockClear();
    mockIsPro = true;
    mockAutoEnabled = true;
    mockEnabledModelIds = ["free-chat"];
    mockUpgradeVisible = false;
    mockModels = [
      {
        id: "free-chat",
        label: "Flash",
        description: "",
        tier: "flash",
        plan_access: "free",
        available: true,
        input_price_per_m: 0,
        output_price_per_m: 0,
        quota_multiplier: 1,
        healthy: true,
        latency_p50_ms: 1214,
      },
    ];
  });

  it("keeps model controls without Usage or Advanced diagnostics", async () => {
    const { getByText, queryByText } = await render(<ModelsSettingsScreen />);

    expect(getByText("settings.model_auto")).toBeTruthy();
    expect(getByText("Flash")).toBeTruthy();
    expect(queryByText("settings.usage_daily")).toBeNull();
    expect(queryByText("settings.usage_group")).toBeNull();
    expect(queryByText("settings.advanced")).toBeNull();
    expect(queryByText("settings.usage_split")).toBeNull();
    expect(queryByText("settings.prompt_window")).toBeNull();
    expect(queryByText("settings.model_latency")).toBeNull();
  });

  it("still saves model preferences when Auto is toggled", async () => {
    const { getByText } = await render(<ModelsSettingsScreen />);
    await fireEvent.press(getByText("settings.model_auto"));
    expect(mockUpdateUser).toHaveBeenCalledWith({ enabled_models: ["free-chat"] });
  });

  it("keeps the last enabled model protected when Auto is off", async () => {
    mockAutoEnabled = false;
    const { getByRole } = await render(<ModelsSettingsScreen />);

    expect(getByRole("switch", { name: "Flash" }).props.accessibilityState).toEqual({
      checked: true,
      disabled: true,
    });
  });

  it("preserves degraded metadata and disables an unavailable model", async () => {
    mockModels = [
      {
        ...mockModels[0],
        id: "offline-chat",
        label: "Offline",
        available: false,
        healthy: false,
      },
    ];
    mockEnabledModelIds = [];
    const { getByRole, getByText } = await render(<ModelsSettingsScreen />);

    expect(getByText("settings.model_degraded")).toBeTruthy();
    expect(getByRole("switch", { name: "Offline" }).props.accessibilityState).toEqual({
      checked: false,
      disabled: true,
    });
  });

  it("keeps Pro-locked model rows actionable for the upgrade sheet", async () => {
    mockIsPro = false;
    mockModels = [
      {
        ...mockModels[0],
        id: "smart-chat",
        label: "Smart",
        plan_access: "pro",
      },
    ];
    mockEnabledModelIds = [];
    const { getByRole, getByText } = await render(<ModelsSettingsScreen />);
    const smartSwitch = getByRole("switch", { name: "Smart" });

    expect(getByText("plans.plus")).toBeTruthy();
    expect(smartSwitch.props.accessibilityState.disabled).toBe(false);
    await fireEvent.press(smartSwitch);
    expect(mockUpgradeVisible).toBe(true);
    expect(mockUpdateUser).not.toHaveBeenCalled();
  });

  it("rolls controlled model draft state back after a failed save", async () => {
    mockAutoEnabled = false;
    mockModels = [
      mockModels[0],
      { ...mockModels[0], id: "balanced-chat", label: "Balanced" },
    ];
    let reject!: (error: Error) => void;
    mockUpdateUser.mockReturnValueOnce(
      new Promise((_resolve, rejectPromise) => {
        reject = rejectPromise;
      }),
    );
    const { getByRole } = await render(<ModelsSettingsScreen />);

    await fireEvent.press(getByRole("switch", { name: "Balanced" }));
    expect(getByRole("progressbar")).toBeTruthy();

    await act(async () => {
      reject(new Error("offline"));
    });
    expect(getByRole("switch", { name: "Balanced" }).props.accessibilityState.checked).toBe(false);
  });

  it("says which model messages use with Auto off, and lets the user choose it", async () => {
    mockAutoEnabled = false;
    mockEnabledModelIds = ["free-chat", "smart-chat"];
    mockModels = [
      ...mockModels,
      { ...mockModels[0], id: "smart-chat", label: "Smart", plan_access: "free" },
    ];
    const view = await render(<ModelsSettingsScreen />);
    expect(view.getByText("settings.model_in_use")).toBeTruthy();
    expect(view.getByLabelText("settings.model_in_use, Flash")).toBeTruthy();
    await fireEvent.press(view.getByLabelText("settings.model_in_use, Flash"));
    await act(async () => {
      fireEvent.press(view.getByRole("radio", { name: "Smart" }));
    });
    expect(mockUpdateUser).toHaveBeenCalledWith({ enabled_models: ["smart-chat", "free-chat"] });
  });

  it("shows no model-in-use row while Auto picks per message", async () => {
    const view = await render(<ModelsSettingsScreen />);
    expect(view.queryByText("settings.model_in_use")).toBeNull();
  });
});
