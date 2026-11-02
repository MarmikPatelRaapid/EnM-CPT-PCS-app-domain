import { useEffect, useRef, useState } from "react";
import {
  GOOGLE_CLIENT_ID,
  clearSession,
  exchangeGoogleIdToken,
  getSession,
  setSession,
  verifySession
} from "./auth.js";

const GOOGLE_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

function loadGoogleScript() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) {
      resolve();
      return;
    }
    const existing = document.querySelector(`script[src="${GOOGLE_SCRIPT_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("Failed to load Google Sign-In script.")));
      return;
    }
    const script = document.createElement("script");
    script.src = GOOGLE_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Google Sign-In script."));
    document.head.appendChild(script);
  });
}

export default function AuthGate({ children }) {
  const [session, setSessionState] = useState(() => getSession());
  const [isChecking, setIsChecking] = useState(true);
  const [error, setError] = useState("");
  const buttonRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    verifySession().then((user) => {
      if (!isMounted) return;
      if (!user) {
        clearSession();
        setSessionState(null);
      }
      setIsChecking(false);
    });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (session || isChecking) return;
    if (!GOOGLE_CLIENT_ID) {
      setError("GOOGLE_CLIENT_ID is not configured (set VITE_GOOGLE_CLIENT_ID in frontend/.env).");
      return;
    }

    let cancelled = false;
    loadGoogleScript()
      .then(() => {
        if (cancelled) return;
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: async (response) => {
            try {
              const result = await exchangeGoogleIdToken(response.credential);
              setSession(result);
              setSessionState(result);
              setError("");
            } catch (err) {
              setError(err.message || "Sign-in failed.");
            }
          }
        });
        if (buttonRef.current) {
          window.google.accounts.id.renderButton(buttonRef.current, {
            theme: "outline",
            size: "large",
            text: "signin_with"
          });
        }
      })
      .catch((err) => setError(err.message || "Failed to load Google Sign-In."));

    return () => {
      cancelled = true;
    };
  }, [session, isChecking]);

  function handleSignOut() {
    clearSession();
    setSessionState(null);
  }

  if (isChecking) {
    return (
      <div className="auth-gate-screen">
        <p>Checking your session...</p>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="auth-gate-screen">
        <div className="auth-gate-card">
          <h2>Domain Workbench</h2>
          <p>Sign in with your raapidinc.com Google account to continue.</p>
          <div ref={buttonRef} />
          {error ? <p className="auth-gate-error">{error}</p> : null}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="auth-gate-bar">
        <span>
          Signed in as <strong>{session.email}</strong>
        </span>
        <button type="button" className="wb-button" onClick={handleSignOut}>
          Sign out
        </button>
      </div>
      {children}
    </>
  );
}
