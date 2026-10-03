// Browser E2E of the EXISTING Studio. All Owner approvals here are SYNTHETIC DEV actions.
// Never real ASR/TTS/provider/production acceptance. No benchmark media or provider secrets.
import fs from "node:fs/promises";
import path from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
const [root, playwrightPath, scenario="image-script"] = process.argv.slice(2);
if (!root || !playwrightPath) throw new Error("root and local Playwright module path required");
const {chromium} = await import(pathToFileURL(playwrightPath).href);
const output = path.join(root, `ui-${scenario}-${Date.now()}`);
await fs.mkdir(output, {recursive:false});
const token = await fs.readFile(path.join(root,".dev-session"),"utf8");
const origin="http://127.0.0.1:8017";
let localRequests=0;
async function api(url, options={}) {
  localRequests++;
  const r=await fetch(origin+url,{...options,headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`,...options.headers}});
  const body=await r.json();
  if(!r.ok)throw new Error(`${url}: ${r.status} ${JSON.stringify(body)}`);
  return body;
}
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"});
const context=await browser.newContext({viewport:{width:1440,height:1080}});
await context.route("**/*", route=> {
  const url=new URL(route.request().url());
  if(url.hostname!=="127.0.0.1") return route.abort();
  return route.continue();
});
await context.addInitScript(t=>sessionStorage.setItem("npd-video-factory-human-session-v1",t),token);
const page=await context.newPage();
const errors=[];
page.on("pageerror",e=>errors.push(e.message));
const log={scenario,classification:"ISOLATED_UI_E2E_SYNTHETIC_MEDIA_OFFLINE_VOICE",
  started_at_utc:new Date().toISOString(), external_provider_calls:0,provider_credential_reads:0,
  human_quality_accepted:false,production_path_accepted:false,steps:[]};
let projectId;
async function waitValue(fn,predicate,label,timeout=60000) {
  const until=Date.now()+timeout;
  while(Date.now()<until) {
    const v=await fn();if(predicate(v))return v;
    await page.waitForTimeout(600);
  }
  throw new Error(`timeout: ${label}`);
}
async function storedContent() {return api(`/api/v1/projects/${projectId}/content`);}
async function render(kind, suffix="") {
  await page.locator(`#${kind}-render-button`).click();
  const packageData=await waitValue(()=>api(`/api/v1/projects/${projectId}/production-package`),p=>!!p[`latest_${kind}_render`],`${kind} queued`);
  const id=packageData[`latest_${kind}_render`].render_id;
  const done=await waitValue(()=>api(`/api/v1/projects/${projectId}/renders/${id}`),r=>!["queued","running"].includes(r.status),`${kind} terminal`,600000);
  await fs.writeFile(path.join(output,`${kind}${suffix}-render.json`),JSON.stringify(done,null,2));
  if(!["awaiting_review","ready"].includes(done.status))throw new Error(`${kind}: ${done.status}: ${done.failure_reason}`);
  const r=await fetch(origin+done.playback_url,{headers:{Authorization:`Bearer ${token}`}});localRequests++;
  if(!r.ok)throw new Error("MP4 download failed");
  const bytes=Buffer.from(await r.arrayBuffer());
  await fs.writeFile(path.join(output,`${kind}${suffix}.mp4`),bytes);
  log.steps.push({step:`${kind}${suffix}_render`,render_id:id,status:done.status,qc:done.qc_status,
    mp4_sha256:createHash("sha256").update(bytes).digest("hex")});
  await page.locator("#production-video").waitFor({state:"visible",timeout:15000});
  await page.waitForFunction(()=>document.querySelector("#production-video").readyState>=2,{},{timeout:30000});
  return done;
}
try {
  await page.goto(origin+"/studio.html");
  await page.locator("#mvp-project-name").fill(`MVP proof ${scenario}`);
  await page.locator("#mvp-project-form button").click();
  await page.waitForFunction(()=>!!localStorage.getItem("npd-studio-project"));
  projectId=await page.evaluate(()=>localStorage.getItem("npd-studio-project"));
  await page.waitForFunction(()=>document.querySelector("#project-select").value===localStorage.getItem("npd-studio-project"));
  await page.waitForFunction(()=>document.querySelector("#multi-input-workbench").dataset.loading==="false");
  if(scenario==="spoken-blocked") {
    await page.locator("#mvp-rights").check();
    await page.locator("#mvp-upload").setInputFiles(path.join(root,"fixtures-spoken","owned-spoken-video.mp4"));
    await page.waitForFunction(()=>document.querySelector("#mvp-video-analysis").options.length>0);
    const responsePromise=page.waitForResponse(r=>r.url().endsWith(`/projects/${projectId}/analyze`)&&r.request().method()==="POST");
    await page.locator("#mvp-analyze-video").click();
    const response=await responsePromise;
    if(response.status()!==503)throw new Error(`unexpected speech stage status ${response.status()}`);
    const analyses=await api(`/api/v1/projects/${projectId}/analyses`);
    if(analyses.some(a=>a.status==="succeeded"||a.transcript))throw new Error("speech ASR was fabricated");
    await fs.writeFile(path.join(output,"speech-analysis-blocked.json"),JSON.stringify({response:await response.json(),analyses},null,2));
    log.steps.push({step:"T01_speech_ASR_stage_blocked",http_status:503,fake_transcript:false});
    log.verdict="UI_SPEECH_ASR_CORRECTLY_BLOCKED_DEV_PASS";
  } else {
  if(["image-script","mixed","image-only"].includes(scenario)) {
    await page.locator("#mvp-rights").check();
    const files=scenario==="image-only"?["owned-photo.png"]:["owned-photo.png","synthetic-architecture.png"];
    if(scenario==="mixed")files.unshift("owned-silent-video.mp4");
    await page.locator("#mvp-upload").setInputFiles(files.map(f=>path.join(root,"fixtures",f)));
    await waitValue(()=>api(`/api/v1/projects/${projectId}/assets`),a=>a.length>=files.length,"uploads");
    await page.waitForFunction(()=>document.querySelector("#mvp-upload").value==="");
    if(scenario==="mixed") {
      await page.waitForFunction(()=>document.querySelector("#mvp-video-analysis").options.length>0);
      const responsePromise=page.waitForResponse(r=>r.url().endsWith(`/projects/${projectId}/analyze`)&&r.request().method()==="POST");
      await page.locator("#mvp-analyze-video").click();
      const response=await responsePromise;
      if(response.status()!==201)throw new Error(`silent analysis: ${response.status()} ${await response.text()}`);
      await waitValue(()=>api(`/api/v1/projects/${projectId}/analyses`),a=>a.some(v=>v.status==="succeeded"),"real silent-video signal analysis");
      await page.waitForTimeout(1000);
    }
  }
  const kind=scenario==="idea"?"idea":scenario==="prompt"?"prompt":"script";
  const script=scenario==="mixed"?"Đây là video thử nghiệm nội bộ.\nĐây là ảnh do nhóm tạo.\nPhối cảnh minh họa, không phải thiết kế chính thức.":"Đây là ảnh do nhóm tạo.\nNội dung chỉ dùng để thử nghiệm.";
  if(scenario==="image-only") {
    await page.waitForFunction(()=>document.querySelector("#mvp-status").textContent.includes("không bắt buộc video"));
    await page.locator("#mvp-from-media").click();
  } else {
  await page.locator("#mvp-kind").selectOption(kind);
  await page.locator("#mvp-original").fill(kind==="prompt"?`Dựng video giới thiệu nội bộ. Không thêm giá hay chính sách.\nLời đọc:\n${script}`:script);
  await page.locator("#mvp-draft").click();
  }
  await waitValue(storedContent,v=>!!v?.snapshot.content.scenes.length,"draft saved");
  await page.locator(".mvp-scene").first().waitFor();
  const assets=await api(`/api/v1/projects/${projectId}/assets`);
  const scenes=page.locator(".mvp-scene");
  for(let i=0;i<await scenes.count();i++) {
    const row=scenes.nth(i);await row.locator("[data-field=duration]").fill("6");
    await row.locator("[data-field=transition]").selectOption(i?"fade":"cut");
    if(scenario==="image-script"||scenario==="mixed") {
      const filename=scenario==="mixed"?["owned-silent-video.mp4","owned-photo.png","synthetic-architecture.png"][i]:["owned-photo.png","synthetic-architecture.png"][i];
      await row.locator("[data-field=media]").selectOption(assets.find(a=>a.filename===filename).asset_id);
      if(filename.includes("architecture"))await row.locator("[data-field=render]").check();
    }
  }
  await page.locator("#mvp-approve").click();
  await waitValue(storedContent,v=>v.snapshot.content.approved,"content approval");
  await page.waitForTimeout(800);
  await page.locator("#mvp-timeline").click();
  const timeline=await waitValue(()=>api(`/api/v1/projects/${projectId}/timeline`).catch(()=>null),v=>!!v,"timeline");
  await page.reload(); // real refresh verifies durable project/content/timeline, not browser-only state.
  await page.locator("#studio-workspace").waitFor({state:"visible"});
  if(await page.locator(".mvp-scene").count()!==timeline.snapshot.tracks[0].clips.length)throw new Error("storyboard lost on refresh");
  await page.locator("#production-package-button").click();
  await page.locator("#production-content").waitFor({state:"visible"});
  const review=await render("review");
  await page.locator("#request-approval-button").waitFor({state:"visible"});
  await page.waitForFunction(()=>!document.querySelector("#request-approval-button").disabled);
  await page.locator("#request-approval-button").click();
  await page.waitForFunction(()=>!document.querySelector("#approve-button").disabled);
  await page.locator("#approve-button").click();
  await page.waitForFunction(()=>!document.querySelector("#final-render-button").disabled);
  const final=await render("final");
  await fs.writeFile(path.join(output,"timeline.json"),JSON.stringify(timeline,null,2));
  await fs.writeFile(path.join(output,"storyboard.json"),JSON.stringify(await storedContent(),null,2));
  await fs.writeFile(path.join(output,"media-plan.json"),JSON.stringify(await api(`/api/v1/projects/${projectId}/storyboard-media-plan`),null,2));
  await fs.writeFile(path.join(output,"production-package.json"),JSON.stringify(await api(`/api/v1/projects/${projectId}/production-package`),null,2));
  await fs.writeFile(path.join(output,"source-assets.json"),JSON.stringify(assets,null,2));
  await page.screenshot({path:path.join(output,"studio-final.png"),fullPage:true});
  if(scenario==="image-script") {
    await page.locator(".mvp-scene").first().locator("[data-field=narration]").fill("Nội dung đã chỉnh sửa.");
    await page.locator("#mvp-save").click();
    const stale=await waitValue(()=>api(`/api/v1/projects/${projectId}/renders/${final.render_id}`),r=>r.status==="stale","final invalidation");
    await fs.writeFile(path.join(output,"stale-final.json"),JSON.stringify(stale,null,2));
    log.steps.push({step:"T08_edit_invalidates_final",status:stale.status});
    await page.waitForFunction(()=>document.querySelector("#final-render-button").disabled);
    await page.locator("#mvp-approve").click();
    await waitValue(storedContent,v=>v.snapshot.content.approved,"edited content reapproval");
    await page.waitForTimeout(800);
    await page.locator("#mvp-timeline").click();
    await waitValue(()=>api(`/api/v1/projects/${projectId}/timeline`),v=>v.current_version>timeline.current_version,"edited timeline");
    await page.waitForTimeout(800);
    await page.locator("#production-package-button").click();
    await page.waitForTimeout(800);
    await render("review","-after-edit");
    await page.waitForFunction(()=>!document.querySelector("#request-approval-button").disabled);
    await page.locator("#request-approval-button").click();
    await page.waitForFunction(()=>!document.querySelector("#approve-button").disabled);
    await page.locator("#approve-button").click();
    await page.waitForFunction(()=>!document.querySelector("#final-render-button").disabled);
    const newFinal=await render("final","-after-edit");
    if(newFinal.render_id===final.render_id)throw new Error("stale final was reused");
    log.steps.push({step:"T08_reapproved_rerender",status:newFinal.status});
    for(const [name,url] of [["timeline",`/api/v1/projects/${projectId}/timeline`],
        ["storyboard",`/api/v1/projects/${projectId}/content`],
        ["media-plan",`/api/v1/projects/${projectId}/storyboard-media-plan`],
        ["production-package",`/api/v1/projects/${projectId}/production-package`]])
      await fs.writeFile(path.join(output,`${name}-after-edit.json`),JSON.stringify(await api(url),null,2));
    await page.screenshot({path:path.join(output,"studio-final-after-edit.png"),fullPage:true});
  }
  if(errors.length)throw new Error(`page errors: ${errors.join("; ")}`);
  log.verdict="UI_AV_REVIEW_FINAL_MP4_DEV_PASS";
  }
} catch(error) {
  log.verdict="DEV_PROOF_BLOCKED";log.error=error.message;
  await page.screenshot({path:path.join(output,"failure.png"),fullPage:true}).catch(()=>{});
  process.exitCode=1;
} finally {
  log.project_id=projectId;log.completed_at_utc=new Date().toISOString();log.local_api_reads=localRequests;log.browser_errors=errors;
  await fs.writeFile(path.join(output,"proof-report.json"),JSON.stringify(log,null,2));
  console.log(JSON.stringify({output,verdict:log.verdict,error:log.error,steps:log.steps}));
  await browser.close();
}
