"""Explicit generic Vision contract fixtures over checksum-bound Native frame references."""
from decimal import Decimal
from . import ingestion
from app.vision_models import NormalizedBox
from app.vision_providers import ProviderVisionFrame,ProviderVisionResult,ProviderObjectDetection,ProviderOCRDetection


class NativeFixtureVisionProvider:
    key='fixture-native-vision-v1'
    model='generic-frame-contract-v1'
    external_call=False
    paid=False
    credential_alias=None
    estimated_cost_vnd=Decimal('0')

    def __init__(self,frames):self.frames=frames

    async def analyze(self,path,*,metadata,scenes,asset_id,checksum_sha256,sample_interval_seconds,execution_trace=None):
        if not path.is_file():raise FileNotFoundError('NATIVE_VISION_SOURCE_NOT_FOUND')
        box=NormalizedBox(x=.3,y=.15,width=.3,height=.6);face=NormalizedBox(x=.36,y=.16,width=.12,height=.14)
        result=[]
        for frame in self.frames:
            result.append(ProviderVisionFrame(timestamp_seconds=frame['timestamp_seconds'],evidence_frame_reference=frame['reference'],
                caption='[EXPLICIT FIXTURE] Generic uploaded frame; no semantic pixel inference.',
                scene_description='[EXPLICIT FIXTURE] Demonstration of typed objects, OCR and composition; no real subject detection.',
                semantic_label='explicit_generic_contract_fixture',environment='explicit_fixture_environment',action='explicit_fixture_action',
                objects=(ProviderObjectDetection(label='EXPLICIT FIXTURE person',category='person',confidence=.65,bounding_box=box,track_hint='explicit-fixture-person'),
                    ProviderObjectDetection(label='EXPLICIT FIXTURE face',category='face',confidence=.6,bounding_box=face,track_hint='explicit-fixture-face')),
                ocr=(ProviderOCRDetection(text='[MẪU] VĂN BẢN',language='vi',confidence=.6,bounding_box=NormalizedBox(x=.1,y=.82,width=.5,height=.1)),),
                primary_subject_box=box,saliency_box=box,headroom_ratio=.15,visual_balance_score=.65,safe_crop=False,
                quality_score=.6,black_frame=False,blur_score=.2,overexposed=False,underexposed=False,low_resolution=False,
                watermark_or_logo_detected=False,frozen_or_duplicate=False,quality_issues=('explicit_fixture_not_real_inference',),confidence=.6))
        return ProviderVisionResult(frames=tuple(result),provenance={'fixture':True,'external_call':False,'paid':False,
            'source_checksum':checksum_sha256,'asset_id':asset_id,'structured_output':True,'semantic_model_saw_pixels':False,
            'frame_references_are_actual_native_evidence':True,'sample_times_are_requested_ffmpeg_seeks_not_decoded_pts':True},actual_cost_vnd=None)
