import {test} from 'node:test';
import assert from 'node:assert/strict';
import {costSummaryHTML,vnd} from '../native-costs.mjs';
import {loadNativeCosts,supportsNativeCosts} from '../native.mjs';

test('Cost UI loads only when an explicit current server capability is present',async()=>{
  let calls=0;
  const loader=async()=>{calls++;return {fixture:true};};
  for(const session of [null,{}, {capabilities:{native_cost_ledger:false}}, {capabilities:{native_cost_ledger:'true'}}]){
    assert.equal(supportsNativeCosts(session),false);assert.equal(await loadNativeCosts(session,loader),null);
  }
  assert.equal(calls,0);
  assert.deepEqual(await loadNativeCosts({capabilities:{native_cost_ledger:true}},loader),{fixture:true});
  assert.equal(calls,1);
});

test('Native cost summary distinguishes unknown amounts, zero and partial recorded history',()=>{
  assert.equal(vnd(null),'Chưa rõ');assert.equal(vnd(undefined),'Chưa rõ');
  assert.match(vnd('0'),/0/);assert.equal(vnd('NaN'),'Chưa rõ');assert.equal(vnd('Infinity'),'Chưa rõ');
  const html=costSummaryHTML({records:[],estimated_cost_total:null,actual_cost_total:null,
    known_actual_cost_subtotal:'70',unknown_actual_cost_operations:2});
  assert.match(html,/Đã tính phí: Chưa rõ/);assert.match(html,/chưa bao gồm đầy đủ lịch sử/);
  assert.match(html,/chưa phải số tiền đã tính phí/);assert.match(html,/2 thao tác/);
});

test('Native cost summary escapes provider and operation text and never substitutes reservations',()=>{
  const html=costSummaryHTML({records:[{provider:'<img src=x>',operation:'<script>',status:'dispatch_intent',
    estimated_cost:'100',actual_cost:null,budget_reserved_vnd:'100'}],needs_attention:true,needs_approval:true});
  assert.doesNotMatch(html,/<img|<script>/);assert.match(html,/&lt;img/);
  assert.match(html,/chưa rõ kết quả/);assert.match(html,/Cần kiểm tra và duyệt/);
  assert.match(html,/đã tính phí Chưa rõ/);
});
