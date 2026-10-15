// Existing focused Root scenarios keep the new manual editor idle.
// Actual manual form/controller/admission/context guards are tested separately.
export function withIdleManualReframe(...args){
 const body=args.pop();
 return withIdleBrollPlan(...args,`
 const manualReframeEditor=null,manualReframeApplying=null,manualReframeAdmission=Symbol('idle-manual-fixture');
 const manualReframeHeld=()=>false,manualReframeDirty=()=>false,manualReframeDraft=()=>"idle-manual-fixture",syncManualReframeForm=()=>{};
 ${body}`);
}

// Pre-existing focused scenarios leave the newly mounted B-roll preparation
// idle. Actual B-roll Root/controller guards have their own integrated tests.
export function withIdleBrollPlan(...args){const body=args.pop();return new Function(...args,`
 const brollPlanController=null,brollPlanBusy=false,brollPlanOperation=null,brollPlanAdmission=Symbol('idle-broll-fixture');
 const brollTimelineController=null,brollTimelineBusy=false,brollTimelineOperation=null,brollTimelineAdmission=Symbol('idle-broll-timeline-fixture');
 const brollTimelineHeld=()=>false,brollTimelineDirty=()=>false,brollTimelineDraft=()=>'idle-broll-timeline-fixture',syncBrollTimelineForm=()=>{};
 const brollInternalController=null,brollInternalBusy=false,brollInternalOperation=null,brollInternalAdmission=Symbol('idle-broll-internal-fixture');
 const brollInternalHeld=()=>false,brollInternalDirty=()=>false,brollInternalDraft=()=>'idle-broll-internal-fixture',syncBrollInternalForm=()=>{};
 const brollTerminalController=null,brollTerminalBusy=false,brollTerminalOperation=null,brollTerminalAdmission=Symbol('idle-terminal-fixture');
 const brollTerminalHeld=()=>false,brollTerminalDirty=()=>false,brollTerminalDraft=()=>'idle-terminal-fixture',syncBrollTerminalForm=()=>{};
 const brollPlanHeld=()=>false,brollPlanDirty=()=>false,brollPlanDraft=()=>"idle-broll-fixture",syncBrollPlanForm=()=>{};
 ${body}`);}
