export function silenceSelection(analysis,ids){
  if(!analysis||analysis.status!=='succeeded')throw new Error('Chờ phân tích hoàn tất trước khi chọn khoảng lặng.');
  const safe=new Set(analysis.silence_decisions.filter(d=>d.enabled&&!d.conflicts_with_speech).map(d=>d.decision_id));
  if(!Array.isArray(ids)||new Set(ids).size!==ids.length||ids.some(id=>!safe.has(id)))throw new Error('Khoảng cắt chưa an toàn hoặc không thuộc bản phân tích này.');
  return [...ids];
}
export function canonicalShotClips(snapshot){
  return snapshot?.tracks?.filter(t=>t.type==='video'&&t.kind==='source'&&!t.disabled)
    .flatMap(t=>t.clips.map(c=>({...c,track_id:t.track_id,track_locked:t.locked})))
    .sort((a,b)=>a.timeline_start-b.timeline_start)??[];
}
