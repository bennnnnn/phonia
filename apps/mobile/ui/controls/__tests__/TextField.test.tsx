import { fireEvent, render } from "@testing-library/react-native";

import { lightTheme } from "@/lib/theme";
import { TextField } from "../TextField";

describe("TextField", () => {
  it("labels the box and passes typing through", async () => {
    const onChangeText = jest.fn();
    const view = await render(<TextField label="City" value="" onChangeText={onChangeText} />);
    expect(view.getByText("City")).toBeTruthy();
    await fireEvent.changeText(view.getByLabelText("City"), "Berlin");
    expect(onChangeText).toHaveBeenCalledWith("Berlin");
  });

  it("turns the border indigo while typing and keeps the caller's focus handlers", async () => {
    const onFocus = jest.fn();
    const onBlur = jest.fn();
    const view = await render(<TextField label="Name" onFocus={onFocus} onBlur={onBlur} />);
    const box = view.getByLabelText("Name");
    expect(box).toHaveStyle({ borderColor: lightTheme.border });
    await fireEvent(box, "focus");
    expect(view.getByLabelText("Name")).toHaveStyle({ borderColor: lightTheme.primary });
    await fireEvent(view.getByLabelText("Name"), "blur");
    expect(view.getByLabelText("Name")).toHaveStyle({ borderColor: lightTheme.border });
    expect(onFocus).toHaveBeenCalledTimes(1);
    expect(onBlur).toHaveBeenCalledTimes(1);
  });

  it("shows the error in place of the helper, in red", async () => {
    const view = await render(
      <TextField label="Salary" helper="Yearly, before tax" error="Enter a number" />,
    );
    expect(view.queryByText("Yearly, before tax")).toBeNull();
    expect(view.getByText("Enter a number")).toHaveStyle({ color: lightTheme.danger });
    expect(view.getByLabelText("Salary")).toHaveStyle({ borderColor: lightTheme.danger });
  });

  it("grows taller when multiline", async () => {
    const view = await render(<TextField label="Notes" multiline />);
    expect(view.getByLabelText("Notes")).toHaveStyle({ minHeight: 96, textAlignVertical: "top" });
  });
});
