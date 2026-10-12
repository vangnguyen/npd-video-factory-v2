import test from 'node:test';
import assert from 'node:assert/strict';
import {validateVisionFrameClock} from '../native-official-vision.mjs';
import {framesMarkup} from '../native-media-frames.mjs';

const frame={frame_id:'mfr_'+'b'.repeat(24),timestamp_seconds:.4,decoded_pts_seconds:.4,timestamp_basis:'decoded_source_pts; copyts_start_at_zero',
  width:480,height:360,decoded_clock:{selected_ordinal:0,pts:400,time_base_numerator:1,time_base_denominator:1000,timestamp_seconds:.4,width:480,height:360},
  pixel_facts:{luma_mean:80,laplacian_variance:20,black_sample:false}};
const observation={schema:'native-media-frame-observations-v2',frames:[frame],decoded_clock_evidence:{algorithm:'single-decode-threshold-sampling-v1',sha256:'c'.repeat(64),log_sha256:'d'.repeat(64),
  reference:`media-clock://${'a'.repeat(32)}/clock-${'e'.repeat(24)}.json`,log_reference:`media-clock://${'a'.repeat(32)}/sampling-${'e'.repeat(24)}.log`}};
const binding={decoded_pts_verified:true,timestamp_basis:frame.timestamp_basis};

test('decoded clock is distinct from semantic inference and inconsistent rational times are refused',()=>{
  assert.equal(validateVisionFrameClock(observation,{kind:'video'},binding),true);
  for(const change of [{decoded_pts_seconds:.5},{decoded_clock:{...frame.decoded_clock,pts:401}},
    {decoded_clock:{...frame.decoded_clock,selected_ordinal:1}}])assert.throws(()=>validateVisionFrameClock({...observation,frames:[{...frame,...change}]},{kind:'video'},binding));
  assert.throws(()=>validateVisionFrameClock(observation,{kind:'video'},{...binding,decoded_pts_verified:false}));
});
test('legacy seek and still images cannot claim verified video PTS',()=>{
  const old={schema:'native-media-frame-observations-v1',frames:[{...frame,decoded_clock:null,decoded_pts_seconds:null}],decoded_clock_evidence:null};
  assert.equal(validateVisionFrameClock(old,{kind:'video'},{timestamp_basis:'requested_ffmpeg_source_seek; decoded_pts_unavailable'}),false);
  assert.throws(()=>validateVisionFrameClock(old,{kind:'video'},binding));
  assert.equal(validateVisionFrameClock({schema:'native-media-frame-observations-v2',frames:[{timestamp_seconds:0,decoded_pts_seconds:null,decoded_clock:null,timestamp_basis:'still_image'}]},
    {kind:'image'},{timestamp_basis:'still_image',decoded_pts_verified:false}),false);
});
test('thumbnail UI labels decoded, historical and static clock evidence separately',()=>{
  const render=f=>framesMarkup({project_id:'a'.repeat(32),observations:[{asset_id:'fixture',frames:[f],thumbnail_candidate_ids:[],rights_status:'unknown'}]});
  assert.match(render(frame),/PTS decoder đã xác minh/);
  assert.match(render({...frame,timestamp_basis:'still_image'}),/ảnh tĩnh/);
  assert.match(render({...frame,timestamp_basis:'requested_ffmpeg_source_seek; decoded_pts_unavailable'}),/PTS chưa xác minh/);
});
