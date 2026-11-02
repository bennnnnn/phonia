import { useTranslation } from "react-i18next";

import {
  SettingsGroup,
  SettingsPage,
  SettingsValueRow,
} from "@/features/account/components/settingsUi";
import licenses from "@/lib/licenses.generated.json";

/** Settings → About → Open-source licenses (built by `pnpm oss-licenses`). */
export default function LicensesScreen() {
  const { t } = useTranslation();
  return (
    <SettingsPage>
      <SettingsGroup label={t("settings.licenses_summary")}>
        {licenses.map((entry) => (
          <SettingsValueRow
            key={entry.name}
            title={entry.name}
            value={`${entry.version} · ${entry.license}`}
          />
        ))}
      </SettingsGroup>
    </SettingsPage>
  );
}
