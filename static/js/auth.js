const TOKEN_KEY = "lumina_auth_token";

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/** Wrapper around fetch() that adds the Authorization header. */
async function authFetch(url, options = {}) {
  const token = getToken();
  if (token) {
    options.headers = {
      ...options.headers,
      Authorization: `Bearer ${token}`,
    };
  }
  const res = await fetch(url, options);
  if (res.status === 401) {
    showLogin();
  }
  return res;
}

/** Check if auth is needed and if we have a valid token. */
async function checkAuth() {
  try {
    const res = await fetch("/api/auth/status");
    const data = await res.json();
    if (!data.auth_enabled) {
      hideLogin();
      return true;
    }
  } catch {
    return false;
  }

  // Auth is enabled — check if our stored token is valid
  const token = getToken();
  if (!token) {
    showLogin();
    return false;
  }

  try {
    const res = await fetch("/api/auth/check", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      hideLogin();
      return true;
    }
  } catch {}

  showLogin();
  return false;
}

async function handleLogin(e) {
  e.preventDefault();
  const input = document.getElementById("login-key");
  const error = document.getElementById("login-error");
  error.textContent = "";

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: input.value }),
    });
    if (res.ok) {
      const data = await res.json();
      setToken(data.token);
      hideLogin();
      // Reload to initialize everything with auth
      location.reload();
    } else {
      error.textContent = "Invalid API key";
    }
  } catch {
    error.textContent = "Connection failed";
  }
}

function showLogin() {
  document.getElementById("login-overlay").classList.remove("hidden");
}

function hideLogin() {
  document.getElementById("login-overlay").classList.add("hidden");
}

function initAuth() {
  const form = document.getElementById("login-form");
  if (form) {
    form.addEventListener("submit", handleLogin);
  }
}

export { getToken, setToken, clearToken, authFetch, checkAuth, initAuth };
