import { useTranslation } from "react-i18next";

import {
  SettingsGroup,
  SettingsLinkRow,
  SettingsPage,
  SettingsValueRow,
  useSettingsAction,
} from "@/features/account/components/settingsUi";
import { openSettingsLink } from "@/features/account/model/openSettingsLink";
import { appVersion, versionLabel } from "@/lib/appVersion";
import { getLegalPrivacyUrl, getLegalTermsUrl } from "@/lib/legalUrls";

/** Settings → About: the legal pages, the licenses, and the version. */
export default function AboutScreen() {
  const { t } = useTranslation();
  const action = useSettingsAction();
  const app = appVersion();
  const open = (url: string) =>
    void action.run("link", () => openSettingsLink(url), { errorKey: "settings.link_failed" });

  return (
    <SettingsPage>
      <SettingsGroup label={t("settings.legal")}>
        <SettingsLinkRow title={t("privacy.title")} onPress={() => open(getLegalPrivacyUrl())} />
        <SettingsLinkRow title={t("terms.title")} onPress={() => open(getLegalTermsUrl())} />
        <SettingsLinkRow
          title={t("settings.licenses")}
          href="/settings/licenses"
        />
      </SettingsGroup>

      <SettingsGroup>
        <SettingsValueRow title={t("settings.about_version")} value={versionLabel(app)} />
        {app.update ? <SettingsValueRow title={t("settings.about_update")} value={app.update} /> : null}
      </SettingsGroup>
    </SettingsPage>
  );
}
