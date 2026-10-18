// Verified authoring receipts only. Saving never approves or dispatches media work.
const ordered=value=>Array.isArray(value)?value.map(ordered):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,ordered(value[k])])):value;
export const stableDramaJSON=value=>JSON.stringify(ordered(value));
export async function dramaRequestHash(request){
  const bytes=await globalThis.crypto.subtle.digest('SHA-256',new TextEncoder().encode(stableDramaJSON(request)));
  return [...new Uint8Array(bytes)].map(v=>v.toString(16).padStart(2,'0')).join('');
}
export async function verifyDramaSaveReceipt(result,{project_id,workspace_id,request}){
  if(result?.project_id!==project_id||result.workspace_id!==workspace_id||result.request_key!==request.request_key||
    result.base_revision!==request.revision||result.revision!==request.revision+1||result.provider_calls!==0||result.human_approval_granted!==false||
    result.request_sha256!==await dramaRequestHash(request))throw Error('Chưa xác minh được đúng lần lưu. Nội dung đang nhập và yêu cầu cũ được giữ để đối chiếu.');
  return result;
}
export function matchesSavedDramaProject(project,request,result=null){
  const record=project?.document?.drama_script,workflow=project?.document?.production_workflow;
  const confirmed=result?.confirmation_preserved===true&&result.characters_confirmed===true?true:request.confirm_characters;
  return Boolean(record&&record.raw_text===request.text&&record.input_mode===request.input_mode&&record.characters_confirmed===confirmed&&
    record.narrator_enabled===request.narrator_enabled&&stableDramaJSON(record.character_notes)===stableDramaJSON(request.character_notes)&&
    workflow?.series===request.series&&workflow?.episode===request.episode&&Object.entries(request.speaker_assignments).every(([line,character])=>
      record.parsed.lines.some(v=>v.line_id===line&&v.character_id===character)));
}
export async function verifyDramaCastingReceipt(result,{project_id,workspace_id,request}){
  if(result?.project_id!==project_id||result.workspace_id!==workspace_id||result.request_key!==request.body.request_key||result.request_sha256!==await dramaRequestHash(request.body)||
    result.project_revision_at_write!==request.body.revision+1||result.casting?.version!==request.body.expected_version+1||
    stableDramaJSON(result.casting?.configuration)!==stableDramaJSON(request.body.configuration)||result.human_approval_granted!==false||result.provider_calls!==0)
    throw Error('Chưa xác minh được đúng lần lưu phân vai. Giữ lựa chọn và đối chiếu yêu cầu cũ.');
  return result;
}
