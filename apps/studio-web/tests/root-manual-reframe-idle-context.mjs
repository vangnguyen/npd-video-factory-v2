// Existing focused Root scenarios keep the new manual editor idle.
// Actual manual form/controller/admission/context guards are tested separately.
export function withIdleManualReframe(...args){
 const body=args.pop();
 return new Function(...args,`
 const manualReframeEditor=null,manualReframeApplying=null,manualReframeAdmission=Symbol('idle-manual-fixture');
 const manualReframeHeld=()=>false,manualReframeDirty=()=>false,manualReframeDraft=()=>"idle-manual-fixture",syncManualReframeForm=()=>{};
 ${body}`);
}
