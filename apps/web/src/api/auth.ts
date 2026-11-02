import { apiUrl, csrfHeaders, fetchWithTimeout, request, setAccessSession } from "@/api/client";
import type { AuthResult, User } from "@/api/types";

export async function loginWithGoogle(idToken: string): Promise<AuthResult> {
  const response = await fetchWithTimeout(apiUrl("/auth/google"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: idToken }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Google login failed");
  }
  const result = (await response.json()) as AuthResult;
  setAccessSession(result.access_token, result.csrf_token);
  return result;
}

export async function loginWithDev(
  email = "dev@recall.local",
  name = "bini",
): Promise<AuthResult> {
  const response = await fetchWithTimeout(apiUrl("/auth/dev"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Dev login failed — is the API running?");
  }
  const result = (await response.json()) as AuthResult;
  setAccessSession(result.access_token, result.csrf_token);
  return result;
}

export async function logoutSession(token: string): Promise<void> {
  try {
    await fetch(apiUrl("/auth/logout"), {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...csrfHeaders(),
      },
      body: JSON.stringify({}),
    });
  } catch {
    /* best-effort */
  }
}

/** Record agreement to the outside-AI disclosure; the server stamps the time. */
export function agreeToAiDataSharing(token: string): Promise<User> {
  return request<User>("/auth/me", token, {
    method: "PATCH",
    body: JSON.stringify({ ai_data_consent: true }),
  });
}
