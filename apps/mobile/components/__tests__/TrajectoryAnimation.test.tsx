/**
 * Native trajectory playback: the graph waits for its button (a projectile or
 * spring reply also carries a scene, which is the one moving picture), plays
 * and pauses from it, and keeps it under Reduce Motion.
 */
import { fireEvent, render } from "@testing-library/react-native";
import { Dimensions } from "react-native";

import { FunctionGraphBlock } from "@/components/rich/FunctionGraphBlock";

const mockUseReduceMotion = jest.fn<boolean | null, []>(() => false);
jest.mock("@/lib/motion", () => ({
  ...jest.requireActual("@/lib/motion"),
  useReduceMotion: () => mockUseReduceMotion() ?? false,
  useReduceMotionSetting: () => mockUseReduceMotion(),
}));

const PARAMETRIC = {
  type: "trajectory",
  expr: "y(x)",
  points: [
    [0, 0],
    [10, 8],
    [20, 10],
    [30, 8],
    [40, 0],
  ],
  x_min: 0,
  x_max: 42,
  title: "Projectile Trajectory",
  x_label: "Distance (m)",
  y_label: "Height (m)",
  trajectory_type: "parametric",
};

const HEIGHT_VS_TIME = {
  ...PARAMETRIC,
  title: "Height vs. Time",
  x_label: "Time (s)",
  trajectory_type: "position_vs_time",
};

const VELOCITY_VS_TIME = {
  ...PARAMETRIC,
  title: "Velocity vs. Time",
  x_label: "Time (s)",
  y_label: "Velocity (m/s)",
  trajectory_type: "velocity_vs_time",
};

const draw = async (spec: object) =>
  await render(<FunctionGraphBlock content={JSON.stringify(spec)} />);

describe("native trajectory playback", () => {
  beforeEach(() => {
    jest
      .spyOn(Dimensions, "get")
      .mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 1 });
    mockUseReduceMotion.mockReturnValue(false);
  });
  afterEach(() => jest.restoreAllMocks());

  it("renders on Skia and waits for its play button", async () => {
    const { getByTestId } = await draw(PARAMETRIC);

    expect(getByTestId("trajectory-canvas")).toBeTruthy();
    expect(getByTestId("trajectory-control")).toBeTruthy();
    expect(getByTestId("trajectory-play-symbol").props.name).toBe("play");
  });

  it("plays and pauses from the triangle play button", async () => {
    const { getByLabelText, getByTestId } = await draw(PARAMETRIC);

    await fireEvent.press(getByLabelText("rich.graph_play_a11y"));
    expect(getByTestId("trajectory-stop-symbol").props.name).toBe("pause");
    await fireEvent.press(getByLabelText("rich.simulation_pause_a11y"));
    expect(getByTestId("trajectory-play-symbol").props.name).toBe("play");
  });

  it("keeps a complete chart and its play button under Reduce Motion", async () => {
    mockUseReduceMotion.mockReturnValue(true);
    const { getByLabelText, getByTestId, getByText } = await draw(PARAMETRIC);

    expect(getByTestId("trajectory-canvas")).toBeTruthy();
    getByText("Projectile Trajectory");
    await fireEvent.press(getByLabelText("rich.graph_play_a11y"));
    expect(getByTestId("trajectory-stop-symbol").props.name).toBe("pause");
  });

  it("is one image described by its title and axes", async () => {
    const { getByRole } = await draw(HEIGHT_VS_TIME);
    expect(getByRole("image").props.accessibilityLabel).toBe("rich.trajectory_a11y");
  });

  it("renders a velocity chart with its own title", async () => {
    const { getByText } = await draw(VELOCITY_VS_TIME);
    getByText("Velocity vs. Time");
  });
});
