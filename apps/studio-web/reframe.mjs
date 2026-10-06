const profiles={
  '9:16':{review:'review-540x960',final:'vertical-1080x1920'},
  '16:9':{review:'review-960x540',final:'landscape-1920x1080'},
  '1:1':{review:'review-540x540',final:'square-1080x1080'},
  '4:5':{review:'review-432x540',final:'portrait-1080x1350'},
};
export function reframeProfiles(snapshot){
  const ratio=snapshot?.metadata?.reframe?.aspect_ratio;
  return profiles[ratio]??profiles['9:16'];
}
export function matchingVision(analyses,source){
  return (analyses??[]).filter(item=>item.status==='succeeded'&&item.analysis_id===source?.analysis_id&&item.asset_id===source?.asset_id);
}
export function needsProductionReview(snapshot){return Boolean(snapshot?.metadata?.reframe);}
