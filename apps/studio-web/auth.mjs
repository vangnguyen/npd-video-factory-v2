const TOKEN_KEY = "npd-video-factory-human-session-v1";
let volatileToken = "";

export class AuthRequiredError extends Error {
  constructor(message, status = 401) {
    super(message);
    this.name = "AuthRequiredError";
    this.status = status;
  }
}

export function sessionToken() {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY) ?? volatileToken;
  } catch {
    return volatileToken;
  }
}

export function setSessionToken(token) {
  volatileToken = String(token ?? "").trim();
  try {
    if (volatileToken) window.sessionStorage.setItem(TOKEN_KEY, volatileToken);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // sessionStorage can be unavailable in hardened/private browser contexts.
  }
}

export function authenticatedHeaders(headers = {}, token = sessionToken()) {
  if (!token) throw new AuthRequiredError("Cần đăng nhập để truy cập workspace.");
  return { ...headers, Authorization: `Bearer ${token}` };
}

export async function authenticatedFetch(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: authenticatedHeaders(options.headers ?? {}),
  });
  if (response.status === 401) {
    setSessionToken("");
    window.location.reload();
    throw new AuthRequiredError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
  }
  return response;
}

function ensureOverlay() {
  let overlay = document.querySelector("#human-auth-overlay");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.id = "human-auth-overlay";
  overlay.className = "auth-overlay";
  overlay.innerHTML = `
    <form class="auth-card" autocomplete="off">
      <div class="auth-mark">N</div>
      <p class="eyebrow">Identity / Ingress Safety</p>
      <h1>Đăng nhập NPD Studio</h1>
      <p>Nhập session token được cấp riêng. Token chỉ được giữ trong phiên trình duyệt này và không được gửi tới dịch vụ khác.</p>
      <label>Session token<input name="token" type="password" minlength="36" maxlength="512" required autocomplete="off" spellcheck="false" /></label>
      <p class="auth-error" role="alert" hidden></p>
      <button class="primary-button" type="submit">Xác thực</button>
      <small>Không có token mặc định. Quyền truy cập bị từ chối theo workspace và vai trò.</small>
    </form>`;
  document.body.append(overlay);
  return overlay;
}

async function validateSession(token) {
  const response = await fetch("/api/v1/auth/session", {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message = body?.detail?.error?.message ?? `Không thể xác thực (HTTP ${response.status}).`;
    throw new AuthRequiredError(message, response.status);
  }
  return response.json();
}

function renderSession(principal) {
  const actions = document.querySelector(".topbar-actions");
  if (!actions || actions.querySelector("[data-human-session]")) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "session-chip";
  button.dataset.humanSession = "true";
  button.title = "Đăng xuất khỏi phiên này";
  button.textContent = `${principal.display_name} · ${principal.platform_role ?? "workspace"}`;
  button.addEventListener("click", () => {
    setSessionToken("");
    window.location.reload();
  });
  actions.prepend(button);
}

export async function ensureAuthenticatedSession() {
  const existing = sessionToken();
  if (existing) {
    try {
      const principal = await validateSession(existing);
      renderSession(principal);
      return principal;
    } catch (error) {
      setSessionToken("");
      if (error.status === 503) throw error;
    }
  }

  const overlay = ensureOverlay();
  overlay.hidden = false;
  const form = overlay.querySelector("form");
  const input = form.elements.token;
  const errorElement = overlay.querySelector(".auth-error");
  input.focus();

  return new Promise((resolve) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submit = form.querySelector("button[type=submit]");
      const token = String(input.value ?? "").trim();
      input.value = "";
      submit.disabled = true;
      errorElement.hidden = true;
      try {
        const principal = await validateSession(token);
        setSessionToken(token);
        overlay.remove();
        renderSession(principal);
        resolve(principal);
      } catch (error) {
        errorElement.textContent = error.message;
        errorElement.hidden = false;
        input.focus();
      } finally {
        submit.disabled = false;
      }
    });
  });
}
