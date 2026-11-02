import { useTranslation } from "react-i18next";

import { ProfileHeader } from "@/features/account/components/ProfileHeader";
import { SettingsProfileSheet } from "@/features/account/components/SettingsProfileSheet";
import { useAuth } from "@/contexts/AuthContext";
import { useProfileEditor } from "@/features/account/hooks/useProfileEditor";

/** Profile's header: tapping the avatar edits the name and photo. */
export function SettingsProfile() {
  const { user, token } = useAuth();
  const { t } = useTranslation();
  const editor = useProfileEditor();

  return (
    <>
      <ProfileHeader label={t("settings.edit_profile")} onPress={editor.open} />
      <SettingsProfileSheet editor={editor} avatarUri={user?.avatar_url} token={token} />
    </>
  );
}
