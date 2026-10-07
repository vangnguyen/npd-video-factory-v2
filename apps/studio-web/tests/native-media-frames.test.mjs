import test from 'node:test';
import assert from 'node:assert/strict';
import {supportsMediaFrames,frameImageUrl,framesMarkup} from '../native-media-frames.mjs';

test('frame evidence needs an explicit capability and scoped frame identifiers',()=>{
  assert.equal(supportsMediaFrames({capabilities:{native_media_frame_analysis:true}}),true);
  assert.equal(supportsMediaFrames({capabilities:{native_media_frame_analysis:'true'}}),false);
  assert.equal(supportsMediaFrames({}),false);
  assert.throws(()=>frameImageUrl('../private','mfr_'+'b'.repeat(24)));
  assert.throws(()=>frameImageUrl('a'.repeat(32),'../../secrets'));
  assert.equal(frameImageUrl('a'.repeat(32),'mfr_'+'b'.repeat(24)),`/api/projects/${'a'.repeat(32)}/media-frames/mfr_${'b'.repeat(24)}/image`);
});
test('unknown analysis is unavailable and measured samples never imply semantic or rights acceptance',()=>{
  assert.match(framesMarkup(null),/Chưa có khung hình đã đo/);
  const frame={frame_id:'mfr_'+'b'.repeat(24),timestamp_seconds:.5,width:320,height:240,duplicate_sample_of:'mfr_old',
    pixel_facts:{luma_mean:0,laplacian_variance:0,black_sample:true}};
  const markup=framesMarkup({project_id:'a'.repeat(32),observations:[{asset_id:'<script>fixture</script>',frames:[frame],
    thumbnail_candidate_ids:[],rights_status:'unknown',identity_rebinding:{fresh_measurement:false}}]});
  assert.ok(!markup.includes('<script>fixture'));
  assert.match(markup,/&lt;script&gt;fixture/);assert.match(markup,/chưa có nhận diện đối tượng/);
  assert.match(markup,/Quyền sử dụng: chưa rõ/);assert.match(markup,/Độ tin cậy AI: chưa có/);
  assert.match(markup,/Tái sử dụng phép đo/);assert.match(markup,/không kết luận video bị đứng/);
  assert.match(markup,/0\.50s/);assert.match(markup,/mẫu đen/);
});
