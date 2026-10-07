"""Map supported historical style associations to available versioned starters."""
import hashlib
from .subtitle_templates import CATALOG, template_catalog


def style_signature(style):
    return ':'.join(str(style[field]) for field in ('position', 'animation', 'font_family', 'font_weight'))


def subtitle_suggestions(snapshot, package):
    catalog = template_catalog()
    dimension = next(item for item in snapshot.dimensions if item.dimension == 'subtitle_style')
    aligned = bool(package and package.subtitle.cues and all(cue.words for cue in package.subtitle.cues))
    suggestions = []; unmatched = []
    for group in dimension.groups:
        if group.state != 'recommendation_candidate': continue
        matches = [template for template in catalog['templates'] if style_signature(template['style']) == group.value]
        if not matches: unmatched.append(group.value)
        for template in matches:
            suggestions.append({'template_ref': template['template_ref'], 'name': template['name'],
                'style': template['style'], 'source_style_signature': group.value,
                'historical_template_identity_verified': False, 'match_kind': 'style_fields_only',
                'sample_count': group.sample_count, 'control_count': group.control_count,
                'score_difference': group.score_difference, 'snapshot_ids': group.snapshot_ids,
                'control_snapshot_ids': group.control_snapshot_ids, 'requires_word_timestamps': template['requires_word_timestamps'],
                'selectable': package is not None and (not template['requires_word_timestamps'] or aligned),
                'attention': 'PRODUCTION_PACKAGE_REQUIRED' if package is None else 'WORD_TIMESTAMPS_REQUIRED'
                    if template['requires_word_timestamps'] and not aligned else None})
    suggestions.sort(key=lambda item: (-item['score_difference'], item['template_ref']))
    return {'schema_version': 'learning-subtitle-suggestions-v1', 'learning_snapshot_id': snapshot.learning_snapshot_id,
        'learning_content_sha256': snapshot.content_sha256, 'workspace_id': snapshot.workspace_id,
        'catalog_version': catalog['version'], 'catalog_sha256': hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        'suggestions': suggestions[:100], 'suggestions_truncated': len(suggestions) > 100,
        'unmatched_historical_styles': unmatched, 'mock_history': snapshot.scope['mock'],
        'subtitle_version': package.subtitle.version if package else None,
        'timeline_version': package.timeline_version if package else None,
        'recommendation_only': True, 'automatic_application': False, 'human_selection_required': True,
        'limitation': 'Only recorded style fields match. Full historic template identity and causal effects are unverified; choose and save explicitly.'}
