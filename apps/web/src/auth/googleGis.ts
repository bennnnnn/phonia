// Google Identity Services (GIS) loader for the browser. The mobile app uses
// @react-native-google-signin/google-signin; the web client uses GIS directly
// with the same web client ID (VITE_GOOGLE_CLIENT_ID == API GOOGLE_CLIENT_ID).
//
// Owner ops: add the web origin (http://localhost:5173 locally, the prod web
// origin in production) to the OAuth client's "Authorized JavaScript origins"
// in the Google Cloud Console, or the GIS token client will throw.

const GIS_SRC = "https://accounts.google.com/gsi/client";
let loadPromise: Promise<void> | null = null;

function loadGoogleGis(): Promise<void> {
  const existing = (window as unknown as { google?: unknown }).google;
  if (typeof window !== "undefined" && existing) {
    return Promise.resolve();
  }
  if (loadPromise) return loadPromise;
  loadPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = GIS_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Google Identity Services"));
    document.head.appendChild(script);
  });
  return loadPromise;
}

function googleClientId(): string {
  const id = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
  if (!id) {
    throw new Error(
      "VITE_GOOGLE_CLIENT_ID is not set. Copy .env.example to .env and set it.",
    );
  }
  return id;
}

// Render the Google "Sign in with Google" button into `container` and call
// `onIdToken` with the resulting ID token on a successful sign-in.
// Minimal typing for the Google Identity Services client we actually use.
// The full GIS typings are heavy and not on npm as a standalone package; we
// only call initialize / renderButton, which both take a small shape.
type GoogleAccountsId = {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (response: { credential?: string }) => void;
      }) => void;
      renderButton: (
        parent: HTMLElement,
        options: { theme: string; size: string; width: number },
      ) => void;
    };
  };
};

function getGoogleAccounts(): GoogleAccountsId | null {
  return (window as unknown as { google?: GoogleAccountsId }).google ?? null;
}

export async function renderGoogleButton(
  container: HTMLElement,
  onIdToken: (idToken: string) => void,
): Promise<void> {
  await loadGoogleGis();
  const google = getGoogleAccounts();
  if (!google) throw new Error("Google Identity Services not available");
  google.accounts.id.initialize({
    client_id: googleClientId(),
    callback: (response: { credential?: string }) => {
      if (response.credential) onIdToken(response.credential);
    },
  });
  google.accounts.id.renderButton(container, {
    theme: "outline",
    size: "large",
    width: 280,
  });
}
