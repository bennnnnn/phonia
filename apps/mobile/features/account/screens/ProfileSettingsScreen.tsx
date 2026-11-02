import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { useTranslation } from "react-i18next";

import { FieldSheet } from "@/ui/overlay/FieldSheet";
import { SettingsProfile } from "@/features/account/components/SettingsProfile";
import {
  SettingsGroup,
  SettingsLinkRow,
  SettingsPage,
  useSettingsAction,
} from "@/features/account/components/settingsUi";
import { useAuth } from "@/contexts/AuthContext";
import { type User } from "@/lib/api";
import { Space } from "@/lib/space";
import { alertDialog } from "@/ui/overlay/dialogs";

type AboutField = "age" | "country" | "job";

const FIELD_COPY: Record<AboutField, { title: string; placeholder: string; maxLength: number }> = {
  age: { title: "settings.your_age", placeholder: "settings.age_placeholder", maxLength: 3 },
  country: {
    title: "settings.your_country",
    placeholder: "settings.country_placeholder",
    maxLength: 64,
  },
  job: { title: "settings.your_job", placeholder: "settings.job_placeholder", maxLength: 128 },
};

function fieldSeed(user: User, field: AboutField): string {
  if (field === "age") return user.age != null ? String(user.age) : "";
  return (field === "country" ? user.country : user.job) ?? "";
}

/** The change to save, `{}` when nothing changed, or null when the age is invalid. */
function fieldPatch(user: User, field: AboutField, text: string): Partial<User> | null {
  const trimmed = text.trim();
  if (field === "age") {
    if (!trimmed) return user.age == null ? {} : { age: null };
    const age = Number.parseInt(trimmed, 10);
    if (!Number.isFinite(age) || age < 13 || age > 120) return null;
    return age === user.age ? {} : { age };
  }
  const next = trimmed || null;
  const current = (field === "country" ? user.country : user.job) ?? null;
  if (next === current) return {};
  return field === "country" ? { country: next } : { job: next };
}

/** Settings → Profile: name and photo, and the facts the assistant uses about you. */
export default function ProfileSettingsScreen() {
  const { user, updateUser } = useAuth();
  const { t } = useTranslation();
  const action = useSettingsAction();
  const [editField, setEditField] = useState<AboutField | null>(null);
  const [fieldText, setFieldText] = useState("");

  const openField = (field: AboutField) => {
    if (!user) return;
    setFieldText(fieldSeed(user, field));
    setEditField(field);
  };

  const saveField = async () => {
    if (!user || !editField) return;
    const patch = fieldPatch(user, editField, fieldText);
    if (patch === null) {
      void alertDialog({ title: t("common.error"), message: t("settings.age_invalid") });
      return;
    }
    if (Object.keys(patch).length === 0) {
      setEditField(null);
      return;
    }
    if (await action.run("field", () => updateUser(patch))) setEditField(null);
  };

  const copy = FIELD_COPY[editField ?? "age"];

  return (
    <>
      <SettingsPage>
        <View style={s.header}>
          <SettingsProfile />
        </View>

        <SettingsGroup label={t("settings.about_you")}>
          <SettingsLinkRow
            title={t("settings.age_label")}
            value={user?.age != null ? String(user.age) : t("settings.not_set")}
            onPress={() => openField("age")}
          />
          <SettingsLinkRow
            title={t("settings.country_label")}
            value={user?.country?.trim() || t("settings.not_set")}
            onPress={() => openField("country")}
          />
          <SettingsLinkRow
            title={t("settings.job_label")}
            value={user?.job?.trim() || t("settings.not_set")}
            onPress={() => openField("job")}
          />
        </SettingsGroup>
      </SettingsPage>

      <FieldSheet
        visible={editField != null}
        title={t(copy.title)}
        value={fieldText}
        onChangeText={setFieldText}
        onClose={() => setEditField(null)}
        onSave={() => void saveField()}
        saving={action.busy === "field"}
        maxLength={copy.maxLength}
        placeholder={t(copy.placeholder)}
        keyboardType={editField === "age" ? "number-pad" : "default"}
      />
    </>
  );
}

const s = StyleSheet.create({
  header: { alignItems: "center", paddingTop: Space.md },
});
