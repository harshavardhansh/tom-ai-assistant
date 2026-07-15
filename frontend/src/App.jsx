import { MsalProvider, useMsal, useIsAuthenticated } from "@azure/msal-react";
import { PublicClientApplication } from "@azure/msal-browser";
import ChatWindow from "./components/ChatWindow.jsx";
import { authEnabled, msalConfig, loginRequest } from "./auth/msalConfig.js";

function TopBar({ userName, onSignOut }) {
  return (
    <header className="topbar">
      <span className="mark">KPMG</span>
      <div className="title">
        TOM AI Knowledge Assistant
        <small>Target Operating Model · process intelligence</small>
      </div>
      <div className="spacer" />
      {userName && (
        <div className="user">
          <span>{userName}</span>
          {onSignOut && (
            <button className="ghost" onClick={onSignOut}>
              Sign out
            </button>
          )}
        </div>
      )}
    </header>
  );
}

// Dev path: no auth configured. The backend runs with AUTH_DISABLED=true.
function DevApp() {
  return (
    <div className="app">
      <TopBar userName="Local Developer" />
      <ChatWindow getToken={null} />
    </div>
  );
}

// Inner authenticated view (rendered inside MsalProvider).
function AuthedInner() {
  const { instance, accounts } = useMsal();
  const isAuthed = useIsAuthenticated();

  const getToken = async () => {
    const result = await instance.acquireTokenSilent({
      ...loginRequest,
      account: accounts[0],
    });
    return result.accessToken;
  };

  if (!isAuthed) {
    return (
      <div className="app">
        <TopBar />
        <div className="welcome" style={{ marginTop: "12vh" }}>
          <h1>Sign in to continue</h1>
          <p>Use your KPMG account to access the TOM AI Knowledge Assistant.</p>
          <button
            className="send"
            style={{ marginTop: 18 }}
            onClick={() => instance.loginRedirect(loginRequest)}
          >
            Sign in with KPMG
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <TopBar
        userName={accounts[0]?.name || accounts[0]?.username}
        onSignOut={() => instance.logoutRedirect()}
      />
      <ChatWindow getToken={getToken} />
    </div>
  );
}

// Single MSAL instance for the app lifetime.
const pca = authEnabled ? new PublicClientApplication(msalConfig) : null;

export default function App() {
  if (!authEnabled) return <DevApp />;
  return (
    <MsalProvider instance={pca}>
      <AuthedInner />
    </MsalProvider>
  );
}
