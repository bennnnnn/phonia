import { useRef } from "react";
import { useTranslation } from "react-i18next";

import { SelectMenu } from "@/ui/overlay/SelectMenu";
import { DatePickerDialog } from "@/ui/pickers/DatePickerDialog";
import { TimePickerDialog } from "@/ui/pickers/TimePickerDialog";
import { repeatMessageKey } from "@/features/todos/model/repeatLabel";
import { TodoCategoryPicker } from "@/features/todos/components/TodoCategoryField";
import type { SchedulePanel } from "@/features/todos/components/TodoDateFields";
import { withCalendarDate } from "@/features/todos/model/dueDate";
import type { RecurrenceRule, Todo } from "@/lib/api";
import { RECURRENCE_RULES } from "@/lib/api/types";
import { timeFromDate, withTimeOfDay } from "@/lib/datetime/clockDial";

export type TodoPicker = "category" | SchedulePanel;

/**
 * The editor's pickers: category sheet, repeat popover, and the app's date
 * and clock dialogs. They stay mounted so each one can fade out; `picker`
 * says which is open. A date or time from an earlier opening (another to-do,
 * or a dialog left over while saving) is dropped.
 */
export function TodoPickers({
  picker,
  topic,
  todos,
  dueDate,
  repeat,
  disabled,
  onTopic,
  onDueDate,
  onRepeat,
  onClose,
}: {
  picker: TodoPicker | null;
  topic: string;
  todos: Todo[];
  dueDate: Date | null;
  repeat: RecurrenceRule | null;
  disabled?: boolean;
  onTopic: (topic: string) => void;
  onDueDate: (date: Date) => void;
  onRepeat: (rule: RecurrenceRule | null) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const due = dueDate ?? new Date();
  const opened = useRef({ picker: null as TodoPicker | null, count: 0 });
  if (picker !== opened.current.picker) {
    opened.current = { picker, count: opened.current.count + (picker ? 1 : 0) };
  }
  const openedCount = opened.current.count;
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;
  const apply = (next: Date) => {
    // An older opening leaves whatever is open now alone.
    if (opened.current.count !== openedCount) return;
    if (!disabledRef.current) onDueDate(next);
    onClose();
  };

  return (
    <>
      {picker === "category" ? (
        <TodoCategoryPicker
          topic={topic}
          todos={todos}
          disabled={disabled}
          onChange={onTopic}
          onClose={onClose}
        />
      ) : null}
      <SelectMenu
        visible={picker === "repeat"}
        options={[
          { key: "none", label: t("todos.repeat_none") },
          ...RECURRENCE_RULES.map((rule) => ({ key: rule, label: t(repeatMessageKey(rule)) })),
        ]}
        selectedKey={repeat ?? "none"}
        disabled={disabled}
        onSelect={(key) => onRepeat(key === "none" ? null : (key as RecurrenceRule))}
        onClose={onClose}
      />
      <DatePickerDialog
        visible={picker === "date" && dueDate != null}
        value={due}
        onConfirm={(date) => apply(withCalendarDate(due, date))}
        onCancel={onClose}
      />
      <TimePickerDialog
        visible={picker === "time" && dueDate != null}
        value={timeFromDate(due)}
        onConfirm={(time) => apply(withTimeOfDay(due, time))}
        onCancel={onClose}
      />
    </>
  );
}
