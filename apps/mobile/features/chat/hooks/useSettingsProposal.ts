import { useState } from "react";

import { useAppearance } from "@/contexts/AppearanceContext";
import { useAuth } from "@/contexts/AuthContext";
import { normalizeAppearancePreference, type AppearancePreference } from "@/lib/appearance";
import { api } from "@/lib/api";
import { writeCachedUser } from "@/lib/cachedUser";
import type { SettingsProposal } from "@/lib/settingsProposal";

function isAppearance(value: string): value is AppearancePreference {
  return value === "light" || value === "dark" || value === "system";
}

export function useSettingsProposal(proposal: SettingsProposal) {
  const { token, mergeUser } = useAuth();
  const { setPreference } = useAppearance();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const confirm = async () => {
    if (!token || busy || done) return false;
    setBusy(true);
    try {
      const result = await api.confirmSettingsProposal(token, proposal.proposal_id);
      mergeUser(result.user);
      void writeCachedUser(result.user);
      if (result.appearance && isAppearance(result.appearance)) {
        await setPreference(normalizeAppearancePreference(result.appearance));
      }
      setDone(true);
      return true;
    } catch {
      return false;
    } finally {
      setBusy(false);
    }
  };

  return { busy, done, confirm };
}
