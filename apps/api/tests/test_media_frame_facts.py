import pytest
from app.media_frame_facts import pixel_facts,PixelFacts


def test_measured_black_and_white_keep_semantic_and_exposure_judgment_unknown():
    black=pixel_facts(bytes(64),8,8);white=pixel_facts(bytes([255])*64,8,8)
    assert black.black_sample and black.luma_mean==0 and black.heuristic_quality_score==0
    assert not white.black_sample and white.high_luma_fraction==1
    for result in [black,white]:
        assert result.confidence is None and result.calibration is None
        assert not result.semantic_inference_performed
        for key in ['frame_caption','object_detections','person_detections','ocr','safe_crop','blur_score','overexposed','watermark_or_logo_evidence']:
            assert getattr(result,key) is None


def test_edge_measurement_and_checksum_are_deterministic_without_claiming_calibration():
    edges=bytes(255*((x+y)%2) for y in range(8) for x in range(8))
    result=pixel_facts(edges,8,8)
    assert result.laplacian_variance>1000 and result==pixel_facts(edges,8,8)
    assert result.laplacian_variance>pixel_facts(bytes([128])*64,8,8).laplacian_variance
    with pytest.raises(ValueError):pixel_facts(b'abc',8,8)
    with pytest.raises(ValueError):PixelFacts.model_validate({**result.model_dump(),'ocr':[{'text':'fabricated'}]})
