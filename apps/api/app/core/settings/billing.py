"""RevenueCat entitlements, its webhook and the hourly reconcile."""

from pydantic import BaseModel


class BillingSettings(BaseModel):
    revenuecat_secret_key: str = ""
    revenuecat_webhook_auth: str = ""
    # Top plan. Keeps the single-plan id so existing subscribers stay on it.
    revenuecat_entitlement_id: str = "pro"
    revenuecat_plus_entitlement_id: str = "plus"
    billing_reconcile_enabled: bool = True
    billing_reconcile_interval_seconds: int = 3600
    billing_reconcile_batch_size: int = 25
    # Pause between the cycle's RevenueCat REST calls, to stay inside its rate limit.
    billing_reconcile_rest_gap_seconds: float = 0.2
    # RevenueCat webhooks require a shared secret. In dev with no secret
    # configured, the webhook is 503 by default; set this true ONLY when
    # testing locally so a missing secret never silently accepts webhooks on
    # a non-production host (environment alone must not skip auth).
    dev_allow_unauthed_webhooks: bool = False
