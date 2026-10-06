import test from 'node:test';
import assert from 'node:assert/strict';
import {supportsNativeAnalysis,transcriptEdits,analysisMarkup} from '../native-auto-edit.mjs';

test('Native analysis is available only with an explicit server capability',()=>{
  assert.equal(supportsNativeAnalysis({capabilities:{native_auto_edit_analysis:true}}),true);
  assert.equal(supportsNativeAnalysis({capabilities:{native_auto_edit_analysis:'true'}}),false);
  assert.equal(supportsNativeAnalysis({}),false);
});
test('transcript edit payload contains only changed segment text',()=>{
  const transcript={segments:[{segment_id:'seg_a',text:'Xin chào.'},{segment_id:'seg_b',text:'Tiếp theo.'}]};
  assert.deepEqual(transcriptEdits(transcript,{seg_a:'Vang Nguyễn.',seg_b:'Tiếp theo.'}),[{segment_id:'seg_a',text:'Vang Nguyễn.'}]);
  assert.deepEqual(transcriptEdits(transcript,{}),[]);
});
test('empty or missing Native evidence remains visibly unavailable',()=>{
  assert.match(analysisMarkup(null),/Chưa có phân tích/);
  const markup=analysisMarkup({analyses:[{filename:'<script>fixture</script>',analysis:{analysis_id:'ana_a',transcript:null,source_media:{duration_seconds:3},silence_decisions:[]},scenes:[],highlights:[],transcript_history:[]}]});
  assert.ok(!markup.includes('<script>fixture'));
  assert.match(markup,/Chưa có lời nói nhận diện/);
  assert.match(markup,/chưa được chọn cho bản dựng hiện tại/);
});
test('edited transcript discloses missing word alignment and renders immutable history',()=>{
  const transcript={version:2,language:'vi',segments:[{segment_id:'seg_a',start_seconds:0,end_seconds:1,text:'Cần Giờ <img onerror=x>',words:[]}]};
  const markup=analysisMarkup({analyses:[{filename:'Source.mp4',analysis:{analysis_id:'ana_a',transcript,source_media:{duration_seconds:3},silence_decisions:[]},scenes:[],highlights:[],transcript_history:[{transcript_id:'trn_a',version:1,is_original_evidence:true},{transcript_id:'trn_b',version:2,is_original_evidence:false}]}]});
  assert.match(markup,/không có căn chỉnh từng từ/);
  assert.match(markup,/Khôi phục thành bản mới/);
  assert.ok(!markup.includes('<img onerror'));
  assert.match(markup,/Cần Giờ &lt;img/);
});
