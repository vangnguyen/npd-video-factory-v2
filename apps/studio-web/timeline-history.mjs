// Saved immutable versions are history; restores create new versions rather than moving a counter.
export function timelineHistory(versions,currentVersion){
  const ordered=[...(versions??[])].filter(v=>Number.isInteger(v.version)&&v.version<=currentVersion).sort((a,b)=>a.version-b.version);
  const undo=[],redo=[];let previous=null;
  for(const version of ordered){
    if(previous!==null){
      const mutation=version.mutation??{},target=mutation.restored_from_version;
      if(mutation.type==='restore'&&target===undo.at(-1)){undo.pop();redo.push(previous);}
      else if(mutation.type==='restore'&&target===redo.at(-1)){redo.pop();undo.push(previous);}
      else {undo.push(previous);redo.length=0;}
    }
    previous=version.version;
  }
  return {undo,redo};
}
export function timelineTranscriptId(timeline){
  return timeline?.snapshot?.metadata?.transcript_revision?.transcript_id??timeline?.snapshot?.tracks?.flatMap(t=>t.clips).find(c=>c.metadata?.transcript_id)?.metadata.transcript_id??null;
}
