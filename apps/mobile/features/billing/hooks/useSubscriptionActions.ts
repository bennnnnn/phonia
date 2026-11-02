import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import type { PaidPlanId } from "@/lib/plan";

export function useSubscriptionActions() {
  const { token, user, refreshUser } = useAuth();

  /** Ask the server to re-read the store; the plan only changes there. Both calls
   * return the account, shown as is (code-health audit NET-19). */
  const syncSubscription = async () => {
    if (!token) return false;
    await refreshUser(api.syncSubscription);
    return true;
  };

  const devUpgrade = async (plan: PaidPlanId) => {
    if (!token) return false;
    try {
      await refreshUser((current) => api.devUpgradePro(current, plan));
      return true;
    } catch {
      return false;
    }
  };

  return { token, user, syncSubscription, devUpgrade };
}
