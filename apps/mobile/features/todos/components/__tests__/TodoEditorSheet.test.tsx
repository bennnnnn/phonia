import type { ReactNode } from "react";
import { fireEvent, render } from "@testing-library/react-native";

import { TodoEditorSheet } from "@/features/todos/components/TodoEditorSheet";

jest.mock("@/lib/i18n", () => ({
  __esModule: true,
  default: { t: (key: string) => key },
  ensureLocale: jest.fn(),
}));

jest.mock("@/lib/reduceMotion", () => ({
  useReduceMotion: () => false,
}));

jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  selection: jest.fn(),
}));
// The detail page asks the server for Remind at; signed out here, it asks nothing.
jest.mock("@/contexts/AuthContext", () => ({ useAuthOptional: () => null }));
jest.mock("@/lib/api", () => ({ api: { previewReminder: jest.fn() } }));
jest.mock("@/features/todos/model/todoReminders", () => ({
  ensureNotificationPermission: jest.fn(async () => true),
}));

jest.mock("@/ui/overlay/Sheet", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Sheet: ({
      children,
      overlay,
      visible,
    }: {
      children: ReactNode;
      overlay?: ReactNode;
      visible: boolean;
    }) => (visible ? <View>{children}{overlay}</View> : null),
  };
});

describe("TodoEditorSheet", () => {
  it("picks one repeat type from a popup list", async () => {
    const { getByLabelText, queryByLabelText } = await render(
      <TodoEditorSheet
        visible
        saving={false}
        todos={[]}
        onClose={jest.fn()}
        onSave={jest.fn()}
      />,
    );

    await fireEvent.press(getByLabelText("todos.add_date"));
    const field = getByLabelText("todos.repeat_label, todos.repeat_none");
    expect(queryByLabelText("todos.repeat_weekly")).toBeNull();

    await fireEvent.press(field);
    expect(getByLabelText("todos.repeat_weekly").props.accessibilityRole).toBe("radio");

    await fireEvent.press(getByLabelText("todos.repeat_weekly"));
    expect(getByLabelText("todos.repeat_label, todos.repeat_weekly")).toBeTruthy();
    expect(queryByLabelText("todos.repeat_monthly")).toBeNull();
  });

  it("saves a built-in category and a newly named one", async () => {
    const onSave = jest.fn();
    const ui = await render(
      <TodoEditorSheet visible saving={false} todos={[]} onClose={jest.fn()} onSave={onSave} />,
    );
    await fireEvent.changeText(ui.getByPlaceholderText("todos.todo_placeholder"), "Call Mom");
    await fireEvent.press(ui.getByLabelText("todos.category_label, todos.category_none"));
    await fireEvent.press(ui.getByLabelText("todos.category_work"));
    await fireEvent.press(ui.getByLabelText("todos.category_label, todos.category_work"));
    await fireEvent.press(ui.getByLabelText("todos.category_new"));
    await fireEvent.changeText(ui.getByLabelText("todos.category_placeholder"), "School");
    await fireEvent(ui.getByLabelText("todos.category_placeholder"), "submitEditing");
    expect(ui.getByLabelText("todos.category_label, School")).toBeTruthy();
    await fireEvent.press(ui.getByLabelText("todos.save"));
    expect(onSave).toHaveBeenCalledWith("Call Mom", null, null, "School");
  });
});
