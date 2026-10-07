export const loginMessage = status => ({401:'Mã truy cập không hợp lệ hoặc đã hết hạn.',404:'Mã truy cập không thuộc không gian này.',429:'Có quá nhiều lần đăng nhập. Đợi một phút rồi thử lại.',503:'Chưa đọc được cấu hình truy cập. Liên hệ chủ không gian.'})[status] || 'Chưa đăng nhập được. Kiểm tra kết nối rồi thử lại.';

export async function submitNativeLogin(token, fetcher = globalThis.fetch) {
  const response = await fetcher('/api/login', {method:'POST',credentials:'same-origin',cache:'no-store',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
  if(!response.ok)throw new Error(loginMessage(response.status));
  // Session and CSRF are read afresh by Studio; no credential storage or URL handoff.
  return true;
}

export function mountNativeLogin(doc = globalThis.document, fetcher = globalThis.fetch, location = globalThis.location) {
  if(!doc)return;
  const form=doc.getElementById('native-login-form'),input=doc.getElementById('native-token'),
    submit=doc.getElementById('native-login-submit'),message=doc.getElementById('native-login-message'),open=doc.getElementById('native-login-open');
  let busy=true;
  input.disabled=true;submit.disabled=true;
  const bootstrap=async()=>{
    try {
      const response=await fetcher('/api/session',{credentials:'same-origin',cache:'no-store'});
      if(response.ok){form.hidden=true;open.hidden=false;message.textContent='Bạn có thể mở Studio bằng phiên hiện tại.';return;}
      if(response.status!==401)throw new Error(loginMessage(response.status));
    } catch(error){message.textContent=error instanceof TypeError?loginMessage(0):error.message;}
    finally{busy=false;input.disabled=false;submit.disabled=false;}
  };
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;
    const token=input.value.trim();input.value='';if(!token)return;
    busy=true;input.disabled=true;submit.disabled=true;message.textContent='Đang xác thực…';
    try {await submitNativeLogin(token,fetcher);location.assign('/');}
    catch(error){message.textContent=error instanceof TypeError?loginMessage(0):error.message;}
    finally{busy=false;input.disabled=false;submit.disabled=false;}
  });
  globalThis.window?.addEventListener('pagehide',()=>{input.value='';});
  return bootstrap();
}
if(typeof document!=='undefined')void mountNativeLogin();
