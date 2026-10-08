const messages = {
  ASSEMBLYAI_KEY_FORMAT_INVALID: "Khóa không đúng định dạng. Kiểm tra lại khóa trong tài khoản AssemblyAI.",
  ASSEMBLYAI_AUTHENTICATION_FAILED: "AssemblyAI từ chối khóa này. Kiểm tra khóa và quyền truy cập tài khoản.",
  ASSEMBLYAI_CONNECTION_UNAVAILABLE: "Chưa kết nối được AssemblyAI. Kiểm tra mạng và thử lại.",
  ASSEMBLYAI_CONNECTION_RATE_LIMITED: "AssemblyAI đang giới hạn yêu cầu. Chờ một lúc rồi kiểm tra lại.",
  ASSEMBLYAI_CONNECTION_CHECK_FAILED: "AssemblyAI chưa xác nhận kết nối. Thử lại sau.",
  ASSEMBLYAI_CREDENTIAL_ALREADY_SAVED: "Đã có khóa lưu trên PC. Dùng nút kiểm tra khóa đã lưu.",
  ASSEMBLYAI_CREDENTIAL_UNAVAILABLE: "Không đọc được khóa đã lưu bằng tài khoản Windows hiện tại.",
  ASSEMBLYAI_CONNECTION_WAIT_FOR_JOBS: "Chờ các job đang chạy hoàn tất rồi kết nối dịch vụ.",
};

export const connectionMessage = code => messages[code] ?? "Chưa lưu được kết nối. Kiểm tra quyền truy cập trên PC và thử lại.";
export const connectionLabel = value => value.connected ? "Đã xác thực kết nối" : value.credential_saved ? "Có khóa — cần kiểm tra" : "Chưa có khóa";


export async function installConnectionShell(session, options = {}, importer = () => import('./studio-shell.mjs')) {
  if(session?.capabilities?.native_studio_ux !== true)return false;
  try { const shell=await importer();shell.loadStudioShellStyles();shell.mountStudioShell({page:options.page || 'settings',context:options.context || 'Kết nối nhận diện lời nói',capabilities:session.capabilities});
    if(session.access?.mode==='registry'){const access=await import('./native-access.mjs');access.installNativeAccess(session);}
    return true; } catch { return false; }
}

if (typeof document !== "undefined") {
  const $ = id => document.getElementById(id);
  let csrf, busy = false, saved = false, stateKnown = false;
  const show = (text, error = false) => {
    $("connection-message").textContent = text;
    $("connection-message").className = "message" + (error ? " error" : "");
    $("connection-message").hidden = false;
  };
  const controls = () => {
    $("connection-refresh").disabled = busy;
    $("connect").disabled = !csrf || !stateKnown || busy || saved;
    $("assemblyai-key").disabled = busy || saved;
    $("verify-saved").disabled = !csrf || !stateKnown || busy;
  };
  const apply = value => {
    stateKnown = true;
    saved = value.credential_saved;
    $("connection-state").textContent = connectionLabel(value);
    $("connection-form").hidden = saved;
    $("verify-saved").hidden = !saved;
    controls();
  };
  const request = async body => {
    busy = true; controls();
    try {
      const response = await fetch("/api/connections/assemblyai", {
        method: "POST", headers: {"Content-Type": "application/json", "X-VF-CSRF": csrf},
        body: JSON.stringify(body), cache: "no-store",
      });
      const value = await response.json();
      if (!response.ok) throw new Error(connectionMessage(value.code));
      apply(value);
      show("Đã xác thực và lưu kết nối AssemblyAI. Bước kiểm tra này không gửi audio hoặc tạo job ASR.");
    } catch (error) {
      $("connection-state").textContent = "Chưa xác nhận kết nối";
      show(error instanceof TypeError ? "Không kết nối được Studio. Làm mới trang và thử lại." : error.message, true);
    } finally {
      busy = false; controls();
    }
  };
  $("connection-form").addEventListener("submit", event => {
    event.preventDefault();
    if (busy || !csrf || !stateKnown || saved) return;
    const key = $("assemblyai-key").value.trim();
    $("assemblyai-key").value = "";
    void request({key});
  });
  $("verify-saved").addEventListener("click", () => { if (!busy && csrf && stateKnown) void request({verify_saved: true}); });
  window.addEventListener("pagehide", () => { $("assemblyai-key").value = ""; });
  const loadState = async () => {
    if(busy)return;
    busy=true;stateKnown=false;controls();$("connection-state").textContent="Đang đọc trạng thái…";
    try {
      const session = await fetch("/api/session", {cache: "no-store"});
      const sessionValue = await session.json();
      if(session.status===401 && sessionValue.code==='NATIVE_AUTH_SESSION_REQUIRED')location.assign('/login');
      if (!session.ok) throw new Error();
      csrf = sessionValue.csrf;
      await installConnectionShell(sessionValue);
      const response = await fetch("/api/connections/assemblyai", {cache: "no-store"});
      if (!response.ok) throw new Error();
      apply(await response.json());
      $("connection-message").hidden=true;
    } catch {
      $("connection-state").textContent = "Chưa đọc được trạng thái";
      show("Không kết nối được Studio. Bấm Làm mới để thử lại.", true);
    } finally { busy=false;controls(); }
  };
  $("connection-refresh").addEventListener("click",()=>void loadState());
  void loadState();
}



