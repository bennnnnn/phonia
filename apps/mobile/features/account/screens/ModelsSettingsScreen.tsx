import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { UpgradeSheet } from "@/features/billing/components/UpgradeSheet";
import {
  SettingsGroup,
  SettingsMenuRow,
  SettingsPage,
  SettingsSwitchRow,
  SettingsValueRow,
} from "@/features/account/components/settingsUi";
import { useAuth } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { buildModelPreferences, useModels } from "@/hooks/useModels";
import { planNameKey } from "@/lib/plan";
import { reportRecoverableError } from "@/lib/reportRecoverableError";

function sameIdSet(a: Set<string>, b: Set<string>): boolean {
  if (a.size !== b.size) return false;
  for (const id of a) {
    if (!b.has(id)) {
      return false;
    }
  }
  return true;
}

type DraftPrefs = {
  auto: boolean;
  models: Set<string>;
};

export default function ModelsSettingsScreen() {
  const { user, updateUser } = useAuth();
  const { t } = useTranslation();
  const { models, isPaid, autoEnabled, modelEnabledSet } = useModels();
  const [upgradeVisible, setUpgradeVisible] = useState(false);
  const [draft, setDraft] = useState<DraftPrefs | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const savingRef = useRef(false);
  const feedback = useActionFeedbackOptional();

  const effectiveAuto = draft?.auto ?? autoEnabled;
  const effectiveModels = draft?.models ?? modelEnabledSet;

  useEffect(() => {
    if (!draft) return;
    if (draft.auto === autoEnabled && sameIdSet(draft.models, modelEnabledSet)) {
      setDraft(null);
    }
  }, [autoEnabled, modelEnabledSet, draft]);

  const patchPreferences = (auto: boolean, modelIds: Set<string>, key: string) => {
    if ((!auto && modelIds.size === 0) || savingRef.current) return;
    savingRef.current = true;
    setSavingKey(key);
    const nextModels = new Set(modelIds);
    setDraft({ auto, models: nextModels });
    void updateUser({ enabled_models: buildModelPreferences(auto, nextModels) })
      .catch(() => {
        setDraft(null);
        reportRecoverableError(feedback, t("common.error"));
      })
      .finally(() => {
        savingRef.current = false;
        setSavingKey(null);
      });
  };

  const toggleAuto = (enabled: boolean) => {
    if (!enabled && effectiveModels.size === 0) return;
    patchPreferences(enabled, effectiveModels, "auto");
  };

  /** With Auto off, every message goes to the first model switched on; this puts `modelId` first. */
  const chooseModelInUse = (modelId: string) => {
    const rest = [...effectiveModels].filter((id) => id !== modelId);
    patchPreferences(false, new Set([modelId, ...rest]), "in-use");
  };
  const usable = models.filter(
    (option) => effectiveModels.has(option.id) && (isPaid || option.plan_access !== "pro"),
  );
  const inUse = usable.find((option) => option.id === [...effectiveModels][0]) ?? usable[0];

  const toggleModel = (modelId: string, enabled: boolean) => {
    if (!user) return;
    const option = models.find((m) => m.id === modelId);
    if (!option?.available) return;
    if (!isPaid && option.plan_access === "pro") {
      if (enabled) setUpgradeVisible(true);
      return;
    }
    const next = new Set(effectiveModels);
    if (enabled) next.add(modelId);
    else next.delete(modelId);
    if (next.size === 0 && !effectiveAuto) return;
    patchPreferences(effectiveAuto, next, modelId);
  };

  return (
    <>
      <SettingsPage>
        <SettingsGroup>
          <SettingsSwitchRow
            title={t("settings.model_auto")}
            subtitle={t("settings.model_auto_summary")}
            value={effectiveAuto}
            disabled={Boolean(savingKey) || (effectiveAuto && effectiveModels.size === 0)}
            busy={savingKey === "auto"}
            onValueChange={toggleAuto}
          />
          {!effectiveAuto && inUse ? (
            usable.length > 1 ? (
              <SettingsMenuRow
                title={t("settings.model_in_use")}
                subtitle={t("settings.model_in_use_summary")}
                value={inUse.label}
                options={usable.map((option) => ({ key: option.id, label: option.label }))}
                selectedKey={inUse.id}
                disabled={Boolean(savingKey)}
                busy={savingKey === "in-use"}
                onSelect={chooseModelInUse}
              />
            ) : (
              <SettingsValueRow
                title={t("settings.model_in_use")}
                subtitle={t("settings.model_in_use_summary")}
                value={inUse.label}
              />
            )
          ) : null}
        </SettingsGroup>

        <SettingsGroup label={t("settings.models_list")}>
          {models.map((option) => {
            const proLocked = !isPaid && option.plan_access === "pro";
            const enabled = effectiveModels.has(option.id) && !proLocked;
            const isLastModel = enabled && effectiveModels.size <= 1 && !effectiveAuto;
            const switchDisabled =
              isLastModel || (!enabled && !option.available && !proLocked);

            return (
              <SettingsSwitchRow
                key={option.id}
                title={option.label}
                subtitle={
                  proLocked
                    ? t(planNameKey("plus"))
                    : option.healthy === false
                      ? t("settings.model_degraded")
                      : undefined
                }
                value={enabled}
                disabled={Boolean(savingKey) || switchDisabled}
                busy={savingKey === option.id}
                onValueChange={(value) => toggleModel(option.id, value)}
              />
            );
          })}
        </SettingsGroup>
      </SettingsPage>
      <UpgradeSheet
        visible={upgradeVisible}
        source="model_gate"
        onClose={() => setUpgradeVisible(false)}
      />
    </>
  );
}
