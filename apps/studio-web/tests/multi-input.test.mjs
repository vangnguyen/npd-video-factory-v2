import assert from "node:assert/strict";
import test from "node:test";
import {sceneSourceKind} from "../multi-input.mjs";

test("storyboard source identity is explicit and never a fake analysis", () => {
  const assets=[{asset_id:"ast_photo",content_type:"image/png"},{asset_id:"ast_video",content_type:"video/mp4"}];
  assert.equal(sceneSourceKind([],assets),"storyboard_media");
  assert.equal(sceneSourceKind([{asset_id:"ast_photo"}],assets),"storyboard_media");
  assert.equal(sceneSourceKind([{asset_id:"ast_photo"},{asset_id:"ast_video"}],assets),"mixed");
  assert.equal(sceneSourceKind([{media_strategy:"ai_video",asset_id:null}],assets),"storyboard_media");
});
