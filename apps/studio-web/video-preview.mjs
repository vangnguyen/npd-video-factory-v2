/** The frame follows the saved project, and measured media once loaded. */
export function videoFormat(project, measured = null) {
  const template=project?.document?.brand_template?.template;
  const snapshot=project?.document?.canonical_timeline?.snapshot;
  const width=Number(measured?.width??snapshot?.width??template?.width??1080),height=Number(measured?.height??snapshot?.height??template?.height??1920);
  const safe=Number.isFinite(width)&&Number.isFinite(height)&&width>0&&height>0;
  const w=safe?width:1080,h=safe?height:1920;
  const gcd=(a,b)=>b?gcd(b,a%b):a,divisor=gcd(w,h);
  return {width:w,height:h,ratio:w/h,aspect:`${w/divisor}:${h/divisor}`,cssAspect:`${w} / ${h}`,portrait:h>w,label:`${w/divisor}:${h/divisor} · ${w}×${h}`};
}

export function applyVideoFormat(canvas, project, measured=null) {
  const format=videoFormat(project,measured);
  canvas.style.setProperty('--preview-aspect',format.cssAspect);
  canvas.style.setProperty('--preview-ratio',String(format.ratio));
  canvas.dataset.aspectRatio=format.aspect;
  canvas.dataset.width=String(format.width);canvas.dataset.height=String(format.height);
  canvas.setAttribute('aria-label',`Khung video ${format.label}`);
  return format;
}

export function nextProjectStage(project) {
  if(!project)return 'script';
  if(project.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1')return 'video';
  if(!project.document?.proposal)return project.document?.input_kind==='media'?'assets':'script';
  if(project.jobs?.some(j=>j.kind==='render'&&j.status==='succeeded'&&j.revision===project.revision))return 'video';
  if(!project.script_review?.current&&!project.approval)return 'script';
  const assets=project.document.assets??(project.document.asset?[project.document.asset]:[]);
  if(!assets.length)return 'assets';
  return 'storyboard';
}
