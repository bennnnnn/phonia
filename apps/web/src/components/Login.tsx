import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { renderGoogleButton } from "@/auth/googleGis";

export function Login() {
  const { user, loading, signInWithGoogle, signInWithDev, error } = useAuth();
  const navigate = useNavigate();
  const googleButtonRef = useRef<HTMLDivElement>(null);
  const [devEmail, setDevEmail] = useState("dev@recall.local");
  const [devName, setDevName] = useState("bini");
  const [localError, setLocalError] = useState<string | null>(null);

  // Render the Google button if a client ID is configured.
  useEffect(() => {
    if (loading || user) return;
    if (!googleButtonRef.current) return;
    renderGoogleButton(googleButtonRef.current, async (idToken) => {
      try {
        await signInWithGoogle(idToken);
        navigate("/chats");
      } catch (e) {
        setLocalError(e instanceof Error ? e.message : "Google login failed");
      }
    }).catch(() => {
      // No client ID configured — GIS not available; dev login still works.
      setLocalError(null);
    });
  }, [signInWithGoogle, navigate, loading, user]);

  const onDev = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      await signInWithDev(devEmail, devName);
      navigate("/chats");
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Dev login failed");
    }
  };

  if (loading) return <div className="loading-screen">Loading…</div>;
  if (user) return <Navigate to="/chats" replace />;

  return (
    <div className="login">
      <div className="login-card">
        <h1>Recall</h1>
        <p className="subtitle">Your personal AI that remembers.</p>
        <div ref={googleButtonRef} className="google-button" />
        <p className="or">or</p>
        <form className="dev-login" onSubmit={onDev}>
          <input
            type="email"
            value={devEmail}
            onChange={(e) => setDevEmail(e.target.value)}
            placeholder="email"
          />
          <input
            type="text"
            value={devName}
            onChange={(e) => setDevName(e.target.value)}
            placeholder="name"
          />
          <button type="submit">Continue (dev)</button>
        </form>
        {(localError || error) && (
          <p className="error">{localError ?? error}</p>
        )}
      </div>
    </div>
  );
}
