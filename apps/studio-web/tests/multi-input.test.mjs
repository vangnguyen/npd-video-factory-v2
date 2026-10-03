import assert from "node:assert/strict";
import test from "node:test";
import {sceneSourceKind,generationInputsChanged} from "../multi-input.mjs";

test("storyboard source identity is explicit and never a fake analysis", () => {
  const assets=[{asset_id:"ast_photo",content_type:"image/png"},{asset_id:"ast_video",content_type:"video/mp4"}];
  assert.equal(sceneSourceKind([],assets),"storyboard_media");
  assert.equal(sceneSourceKind([{asset_id:"ast_photo"}],assets),"storyboard_media");
  assert.equal(sceneSourceKind([{asset_id:"ast_photo"},{asset_id:"ast_video"}],assets),"mixed");
  assert.equal(sceneSourceKind([{media_strategy:"ai_video",asset_id:null}],assets),"storyboard_media");
});

test("proposal cannot overwrite unsaved kind/script/original/facts", () => {
  const doc={input_kind:"idea",original_text:"Ý tưởng.",script:"",supplied_facts:["Chưa xác minh."]};
  const input={kind:"idea",original:"Ý tưởng.",script:"",facts:"Chưa xác minh."};
  assert.equal(generationInputsChanged(doc,input),false);
  assert.equal(generationInputsChanged(null,input),true);
  for(const [key,value] of [["kind","prompt"],["original","Khác."],["script","Đang sửa."],["facts","Thông tin khác."]])
    assert.equal(generationInputsChanged(doc,{...input,[key]:value}),true);
});
