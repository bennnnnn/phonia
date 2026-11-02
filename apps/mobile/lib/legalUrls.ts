import { getApiUrl } from "@/lib/config";

export function getLegalPrivacyUrl(): string {
  return `${getApiUrl()}/legal/privacy`;
}

export function getLegalTermsUrl(): string {
  return `${getApiUrl()}/legal/terms`;
}
