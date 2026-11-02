/** Sign-in with Google, Apple, or dev auth, and the consent asked of an account without it.
 * Session refresh lives in lib/api/client.ts. */
import {
  ApiRequestError,
  apiUrl,
  AUTH_FETCH_TIMEOUT_MS,
  fetchWithTimeout,
  request,
} from "@/lib/api/client";
import { withDeadline } from "@/lib/api/deadline";
import { responseRequestId } from "@/lib/api/requestId";
import type { AuthResult, User } from "@/lib/api/types";
import { AccountExistsError, accountExistsProvider } from "@/features/auth/model/accountExists";
import {
  SignInRefusedError,
  signInRefusalKey,
  signInUnreachable,
} from "@/features/auth/model/signInRefusal";
import { deviceSessionFields } from "@/lib/deviceSession";

/**
 * Every sign-in starts from a button on the sign-in page, under the line saying that
 * continuing agrees to the Terms, the Privacy Policy and outside AI processing
 * (`login.consent_line`): the tap is the agreement, and the server records it with the
 * sign-in, so the reply comes back agreed. Only those buttons call these functions.
 */
const AGREED_BY_SIGNING_IN = { ai_data_consent: true } as const;

/** A refused sign-in, read by its code: never the server's English (signInRefusal.ts). */
async function loginFailure(response: Response): Promise<Error> {
  const refused = new ApiRequestError(
    response.status,
    await response.text(),
    null,
    responseRequestId(response),
  );
  const provider = accountExistsProvider(refused);
  if (provider) return new AccountExistsError(provider);
  return new SignInRefusedError(signInRefusalKey(refused));
}

/** One sign-in call and the reading of its reply, under one deadline: the headers'
 * timer alone left a stalled body spinning the sign-in button (code-health audit NET-17).
 * No answer in time, or none at all, is `signInUnreachable`: its English was shown. */
function signIn(
  path: string,
  body: Record<string, unknown>,
  read: (response: Response) => Promise<AuthResult>,
): Promise<AuthResult> {
  return withDeadline(AUTH_FETCH_TIMEOUT_MS, null, async (signal) => {
    let response: Response;
    try {
      response = await fetchWithTimeout(apiUrl(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });
    } catch {
      throw signInUnreachable();
    }
    return read(response);
  }, signInUnreachable);
}

export function loginWithGoogle(idToken: string): Promise<AuthResult> {
  const body = { id_token: idToken, ...AGREED_BY_SIGNING_IN, ...deviceSessionFields() };
  return signIn("/auth/google", body, async (response) => {
    if (!response.ok) throw await loginFailure(response);
    return (await response.json()) as AuthResult;
  });
}

export function loginWithApple(
  idToken: string,
  name: string | null,
  nonce: string,
): Promise<AuthResult> {
  const body = {
    id_token: idToken,
    name: name ?? null,
    nonce,
    ...AGREED_BY_SIGNING_IN,
    ...deviceSessionFields(),
  };
  return signIn("/auth/apple", body, async (response) => {
    if (!response.ok) throw await loginFailure(response);
    return (await response.json()) as AuthResult;
  });
}

export function loginWithDev(
  email = "dev@recall.local",
  name = "bini",
): Promise<AuthResult> {
  const body = { email, name, ...AGREED_BY_SIGNING_IN, ...deviceSessionFields() };
  return signIn("/auth/dev", body, async (response) => {
    if (!response.ok) throw await loginFailure(response);
    return (await response.json()) as AuthResult;
  });
}

/** Record that an account without the agreement (one from before sign-in recorded it, or
 * one that withdrew) agreed on the consent screen; the server stamps the time. */
export function agreeToAiDataSharing(token: string): Promise<User> {
  return setAiDataSharing(token, true);
}

/** Withdraw that agreement: chat, voice and photo reads stop until the user agrees again. */
export function withdrawAiDataSharing(token: string): Promise<User> {
  return setAiDataSharing(token, false);
}

function setAiDataSharing(token: string, agreed: boolean): Promise<User> {
  return request<User>("/auth/me", token, {
    method: "PATCH",
    body: JSON.stringify({ ai_data_consent: agreed }),
  });
}
