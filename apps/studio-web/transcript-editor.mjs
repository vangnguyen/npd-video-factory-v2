export function transcriptEditPayload(analysis,timeline,segmentId,text){
  const transcript=analysis?.transcript;
  if(!transcript||!transcript.segments.some(s=>s.segment_id===segmentId))throw new Error('Transcript đã thay đổi. Làm mới trước khi sửa.');
  if(typeof text!=='string'||!text.trim()||text.length>4000)throw new Error('Nhập lời nhận diện, tối đa 4.000 ký tự.');
  if(timeline&&timeline.source_analysis_id!==analysis.analysis_id)throw new Error('Timeline đang dùng một kết quả phân tích khác.');
  return {expected_version:analysis.provenance?.human_transcript_revision??transcript.version,base_transcript_id:transcript.transcript_id??null,expected_timeline_version:timeline?.current_version??null,
    segments:[{segment_id:segmentId,text}],note:'Studio transcript text edit; retain source, discard old word alignment for changed text'};
}
