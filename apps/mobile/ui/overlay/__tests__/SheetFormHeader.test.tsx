import { render } from "@testing-library/react-native";

import { SheetFormHeader } from "../SheetFormHeader";

jest.mock("@/lib/colorScheme", () => ({
  useResolvedColorScheme: () => "light",
}));

describe("SheetFormHeader", () => {
  it("renders cancel, title, and save with 44pt targets", async () => {
    const { getByTestId, getByText } = await render(
      <SheetFormHeader
        title="Rename"
        onCancel={jest.fn()}
        onSave={jest.fn()}
        cancelLabel="Cancel"
        saveLabel="Save"
      />,
    );

    expect(getByText("Rename")).toBeOnTheScreen();
    // A screen reader's heading navigation lands on the sheet's title.
    expect(getByText("Rename").props.accessibilityRole).toBe("header");
    expect(getByText("Cancel")).toBeOnTheScreen();
    expect(getByText("Save")).toBeOnTheScreen();
    expect(getByTestId("sheet-form-header-cancel")).toHaveStyle({ minHeight: 44 });
    expect(getByTestId("sheet-form-header-save")).toHaveStyle({ minHeight: 44 });
  });

  it("marks save busy and disabled while saving", async () => {
    const { getByTestId } = await render(
      <SheetFormHeader
        title="Name"
        onCancel={jest.fn()}
        onSave={jest.fn()}
        cancelLabel="settings.cancel"
        saveLabel="settings.save"
        saving
      />,
    );

    expect(getByTestId("sheet-form-header-save").props.accessibilityState).toEqual({
      disabled: true,
      busy: true,
    });
    expect(getByTestId("sheet-form-header-cancel").props.accessibilityState).toEqual({
      disabled: true,
    });
  });

  it("disables save without a spinner when saveDisabled", async () => {
    const { getByTestId, getByText, queryByRole } = await render(
      <SheetFormHeader
        title="Reminder"
        onCancel={jest.fn()}
        onSave={jest.fn()}
        cancelLabel="Cancel"
        saveLabel="Save"
        saveDisabled
      />,
    );

    expect(getByText("Save")).toBeOnTheScreen();
    expect(queryByRole("progressbar")).toBeNull();
    expect(getByTestId("sheet-form-header-save").props.accessibilityState.disabled).toBe(
      true,
    );
  });
});
