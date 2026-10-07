"""Typed measured pixel facts. Absent semantic inference stays explicitly unknown."""
import hashlib
import math
from typing import Literal
from pydantic import Field,ConfigDict
from .models import StrictModel

ALGORITHM='pixel-quality-facts-v1'


class PixelFacts(StrictModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    algorithm:Literal['pixel-quality-facts-v1']=ALGORITHM
    sample_width:int=Field(ge=3,le=256)
    sample_height:int=Field(ge=3,le=256)
    luma_mean:float=Field(ge=0,le=255)
    luma_stddev:float=Field(ge=0,le=128)
    low_luma_fraction:float=Field(ge=0,le=1)
    high_luma_fraction:float=Field(ge=0,le=1)
    laplacian_variance:float=Field(ge=0)
    sample_pixels_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    black_sample:bool
    heuristic_quality_score:float=Field(ge=0,le=1)
    confidence:None=None
    calibration:None=None
    semantic_inference_performed:Literal[False]=False
    frame_caption:None=None
    scene_description:None=None
    object_detections:None=None
    person_detections:None=None
    ocr:None=None
    environment:None=None
    action:None=None
    subject_position:None=None
    safe_crop:None=None
    saliency:None=None
    headroom:None=None
    blur_score:None=None
    overexposed:None=None
    underexposed:None=None
    watermark_or_logo_evidence:None=None
    broll_relevance:None=None


class MeasuredFrame(StrictModel):
    frame_id:str=Field(min_length=1,max_length=80)
    timestamp_seconds:float=Field(ge=0,allow_inf_nan=False)
    reference:str=Field(min_length=1,max_length=500)
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    provider:Literal['local_ffmpeg_pillow_pixels']
    model:Literal['pixel-quality-facts-v1']
    pixel_facts:PixelFacts


class PixelAssetSummary(StrictModel):
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    observation_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    provider:Literal['local_ffmpeg_pillow_pixels']
    model:Literal['pixel-quality-facts-v1']
    sample_count:int=Field(ge=1,le=8)
    heuristic_quality_score:float=Field(ge=0,le=1)
    black_sample_fraction:float=Field(ge=0,le=1)
    confidence:None=None
    semantic_relevance:None=None
    frames:list[MeasuredFrame]=Field(min_length=1,max_length=8)


def pixel_facts(pixels:bytes,width:int,height:int):
    if type(width) is not int or type(height) is not int or not 3<=width<=256 or not 3<=height<=256 or len(pixels)!=width*height:
        raise ValueError('bounded decoded grayscale pixels required')
    values=list(pixels);count=len(values);mean=sum(values)/count
    variance=sum((value-mean)**2 for value in values)/count
    laplacian=[]
    for y in range(1,height-1):
        for x in range(1,width-1):
            i=y*width+x;laplacian.append(4*values[i]-values[i-1]-values[i+1]-values[i-width]-values[i+width])
    lm=sum(laplacian)/len(laplacian)
    sharpness=sum((value-lm)**2 for value in laplacian)/len(laplacian)
    low=sum(value<=20 for value in values)/count;high=sum(value>=235 for value in values)/count
    black=mean<=10 and low>=.98
    # A transparent uncalibrated ranking heuristic, never a model confidence or
    # exposure/blur diagnosis. Uniform artwork can be valid despite a low score.
    score=0 if black else .6*min(1,sharpness/1000)+.4*(1-min(1,abs(mean-127.5)/127.5))
    return PixelFacts(sample_width=width,sample_height=height,luma_mean=mean,luma_stddev=math.sqrt(variance),
        low_luma_fraction=low,high_luma_fraction=high,laplacian_variance=sharpness,
        sample_pixels_sha256=hashlib.sha256(pixels).hexdigest(),black_sample=black,heuristic_quality_score=round(score,6))
