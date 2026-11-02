import { fireEvent, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { AttachmentSourceSheet } from "@/features/attachments/components/AttachmentSourceSheet";
import { Layer } from "@/lib/layer";
import { Space } from "@/lib/space";

jest.mock("@/lib/reduceMotion", () => ({
  useReduceMotion: () => false,
}));

jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  selection: jest.fn(),
}));

describe("AttachmentSourceSheet", () => {
  it("offers scan math plus camera, photo, and file", async () => {
    const onSelect = jest.fn();
    const { queryByText, getByText } = await render(
      <AttachmentSourceSheet visible onClose={jest.fn()} onSelect={onSelect} />,
    );

    expect(queryByText("chat.attach_generate_image")).toBeNull();
    expect(queryByText("chat.attach_library")).toBeNull();
    expect(getByText("chat.attach_solve_math_camera")).toBeTruthy();

    await fireEvent.press(getByText("chat.attach_camera"));
    expect(onSelect).toHaveBeenCalledWith("camera");
  });

  it("sits on the bottom edge and stacks above the composer", async () => {
    const { getByTestId, getByText } = await render(
      <AttachmentSourceSheet visible onClose={jest.fn()} onSelect={jest.fn()} />,
    );

    expect(getByText("chat.attach_file")).toBeOnTheScreen();
    const panel = StyleSheet.flatten(getByTestId("app-sheet-dialog").props.style);
    // Safe-area margin only. A composer-sized lift leaves the bar visible under the sheet.
    expect(panel.marginBottom).toBe(Space.xs + Space.sm);
    const host = StyleSheet.flatten(getByTestId("app-sheet-embedded").props.style);
    expect(host.zIndex).toBeGreaterThan(Layer.composerExpanded);
  });
});
