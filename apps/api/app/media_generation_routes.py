"""Mode-specific envelopes for approved workflow IDs, never client graphs.

Reference strings are request evidence, not authorization to read local files
or download URLs. A live backend still needs a scoped verified-asset resolver.
"""
from types import MappingProxyType
import re
from .media_intelligence_models import ImageGenerationInput, VideoGenerationInput


IMAGE_ROUTES = {'generate': 'npd-text-to-image-v1', 'image_to_image': 'npd-image-to-image-v1',
    'variation': 'npd-image-to-image-v1', 'inpaint': 'npd-inpaint-v1', 'upscale': 'npd-upscale-v1'}
VIDEO_ROUTES = {'text_to_video': 'npd-video-generation-v1', 'image_to_video': 'npd-image-to-video-v1',
    'reference_assisted': 'npd-image-to-video-v1'}


def workflow_routes(modality, primary_workflow_id, overrides=None):
    if modality not in {'image', 'video'}:
        raise ValueError('GENERATION_MODALITY_INVALID')
    routes = dict(IMAGE_ROUTES if modality == 'image' else VIDEO_ROUTES)
    routes['generate' if modality == 'image' else 'text_to_video'] = primary_workflow_id
    if overrides:
        if not isinstance(overrides, dict) or set(overrides) - set(routes):
            raise ValueError('GENERATION_WORKFLOW_ROUTES_INVALID')
        routes.update(overrides)
    if any(not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,80}', value) for value in routes.values()):
        raise ValueError('GENERATION_WORKFLOW_ID_INVALID')
    return MappingProxyType(routes)


def generation_envelope(modality, payload, routes):
    if modality == 'image':
        if not isinstance(payload, ImageGenerationInput):
            raise ValueError('GENERATION_MODALITY_MISMATCH')
        mode = 'image_to_image' if payload.operation == 'generate' and payload.reference_images else payload.operation
        if mode == 'inpaint':
            inputs = {'prompt': payload.prompt, 'reference_images': payload.reference_images,
                'mask_reference': payload.mask_reference, 'seed': payload.seed}
        elif mode == 'upscale':
            inputs = {'prompt': payload.prompt, 'reference_images': payload.reference_images,
                'scale': payload.upscale_factor, 'seed': payload.seed}
        else:
            inputs = payload.model_dump(mode='json')
            inputs['operation'] = mode
    else:
        if not isinstance(payload, VideoGenerationInput):
            raise ValueError('GENERATION_MODALITY_MISMATCH')
        mode = payload.mode
        inputs = payload.model_dump(mode='json')
    return routes[mode], mode, inputs
