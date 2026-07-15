// Microsoft Entra ID (MSAL) configuration.
// Auth is enabled only when the tenant/client are configured via env, so the
// app runs locally against a backend with AUTH_DISABLED=true without sign-in.

const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID || "";
const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID || "";
const apiScope = import.meta.env.VITE_ENTRA_API_SCOPE || "";

export const authEnabled = Boolean(tenantId && clientId);

export const msalConfig = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: window.location.origin,
  },
  cache: { cacheLocation: "sessionStorage", storeAuthStateInCookie: false },
};

// Scope requested for the protected TOM API.
export const loginRequest = {
  scopes: apiScope ? [apiScope] : ["User.Read"],
};
