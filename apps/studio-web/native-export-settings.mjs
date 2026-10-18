// Changes canonical project settings; no transcoding of an approved byte stream.
const shapes={'vertical-short':['9:16',''],'landscape':['16:9','landscape'],'square':['1:1','square'],'portrait-feed':['4:5','feed']};
export const canConfigureExport=p=>Boolean(p?.document?.canonical_timeline&&(p.document.canonical_timeline.snapshot?.metadata?.native_auto_edit_schema||p.document.prepared_narration));
export async function applyNativeExportSettings({api,project,choice,catalog}){
  const shape=shapes[choice.profile];if(!shape)throw Error('Chọn định dạng hợp lệ.');
  const id=project.id,doc=project.document,canonical=doc.canonical_timeline;
  if(canonical?.snapshot?.metadata?.native_auto_edit_schema)return api(`/api/projects/${id}/auto-edit/timeline`,{revision:project.revision,action:'configure',payload:{expected_version:canonical.version,
    aspect_ratio:shape[0],fps:choice.fps,quality_preset:choice.quality_preset,burn_subtitles:choice.burn_subtitles,audio_included:choice.audio_included}});
  const current=doc.brand_template;
  if((current?.template.aspect_ratio??canonical?.snapshot.aspect_ratio??'9:16')!==shape[0]){
    const base=current?.template.id.replace(/-(landscape|square|feed)$/,'');
    const target=base?base+(shape[1]?'-'+shape[1]:''):catalog?.templates.find(t=>t.aspect_ratio===shape[0]&&t.purpose==='property_presentation'&&t.duration_seconds===30)?.id;
    if(!target)throw Error('Chưa có mẫu cho định dạng này.');
    project=await api(`/api/projects/${id}/brand-template`,{revision:project.revision,brand_id:current?.brand.id??'vf-reference',template_id:target,duration_mode:current?.template.duration_policy??'fit_narration_preserve_voice_speed'});
  }
  if(canConfigureExport(project)){
    const state=project.document.canonical_timeline;
    return api(`/api/projects/${id}/narrated-timeline/configure`,{revision:project.revision,expected_version:state.version,timeline_sha256:state.sha256,
      fps:choice.fps,quality_preset:choice.quality_preset,burn_subtitles:choice.burn_subtitles,audio_included:choice.audio_included});
  }
  if(choice.fps!==30||choice.quality_preset!=='standard'||!choice.burn_subtitles||!choice.audio_included)throw Error('Chuẩn bị giọng và timeline trước khi đổi cài đặt xuất.');
  return project;
}
