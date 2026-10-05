"""Transparent editorial heuristics; no statistical prediction or weight learning."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from .contracts import WorkflowError, digest
from .intelligence_models import DIMENSIONS, IdeaScore

DEFAULT_CONFIG=Path(__file__).parent/'profiles/intelligence.json'


def configuration(path=DEFAULT_CONFIG):
    data=json.loads(Path(path).read_bytes())
    weights=data['scoring']['weights']
    if set(weights)!=set(DIMENSIONS) or any(type(v) not in (int,float) or not 0<=v<=10 for v in weights.values()) or not sum(weights.values())>0:
        raise WorkflowError('INTELLIGENCE_SCORING_WEIGHTS_INVALID')
    return data


def tokens(text): return {v.casefold() for v in re.findall(r'\w+',text) if len(v)>2}


def score(idea,findings,sources,profile,config,previous=(),as_of=None):
    as_of=as_of or datetime.now(timezone.utc)
    rules=config['scoring']; weights=rules['weights']
    if set(weights)!=set(DIMENSIONS) or any(type(v) not in (int,float) or not 0<=v<=10 for v in weights.values()) or sum(weights.values())<=0:
        raise WorkflowError('INTELLIGENCE_SCORING_WEIGHTS_INVALID')
    chosen=[f for f in findings if f['id'] in idea['supporting_research']]
    dates=[datetime.fromisoformat(s['timestamp']) for s in sources if s['id'] in idea['evidence_references'] and s['timestamp']]
    freshness=sum(max(0,100*(1-max(0,(as_of-d).days)/rules['freshness_window_days'])) for d in dates)/len(dates) if dates else rules['unknown_publication_score']
    related=profile.get('related_project')
    overlaps=[len(tokens(idea['title']+' '+idea['angle']) & tokens(p['title']+' '+p['angle']))/max(1,len(tokens(idea['title']+' '+idea['angle']) | tokens(p['title']+' '+p['angle']))) for p in previous]
    components={
        'relevance':100*sum(f['relevance'] for f in chosen)/max(1,len(chosen)),
        'freshness':freshness,
        'audience_fit':100*len(tokens(idea['target_audience']) & tokens(profile['target_audience']))/max(1,len(tokens(profile['target_audience']))),
        'product_fit':100 if related and tokens(related)<=tokens(idea['title']+' '+idea['angle']) else rules['contextual_fit_score'],
        'hook_strength':rules['hook_length_score'] if rules['hook_min_chars']<=len(idea['hook'])<=rules['hook_max_chars'] else rules['hook_other_score'],
        'evidence_strength':min(100,rules['points_per_finding']*len(chosen))*len(dates)/max(1,len(idea['evidence_references'])),
        'production_feasibility':100 if idea['estimated_duration'] in profile['duration_seconds'] and idea['format'] in profile['preferred_formats'] else rules['unmatched_format_score'],
        'lead_potential':rules['configured_cta_score'] if any(t.casefold() in idea['cta'].casefold() for t in profile['cta_keywords']) else rules['unmatched_cta_score'],
        'novelty':100*(1-max(overlaps,default=0)),
        'risk':min(100,rules['unknown_date_risk']*(1-len(dates)/max(1,len(idea['evidence_references'])))+rules['risk_per_marker']*sum(m.casefold() in (idea['title']+' '+idea['hook']+' '+idea['angle']).casefold() for m in rules['risk_markers']))}
    rationale={
        'relevance':'Query-token overlap measured in supporting quotations; no semantic truth claim.',
        'freshness':'Publication age only, never retrieval age; unknown dates score conservatively.',
        'audience_fit':'Audience keyword overlap with selected profile.',
        'product_fit':'Related project name coverage or contextual configuration default.',
        'hook_strength':'Configured hook-length heuristic; human quality review required.',
        'evidence_strength':'Number of referenced quotations, discounted for unknown publication dates; no independent truth verification.',
        'production_feasibility':'Configured format and duration match; media rights still require review.',
        'lead_potential':'CTA keyword fit only; no conversion prediction.',
        'novelty':'Token distance from other retained candidates; no market originality claim.',
        'risk':'Higher means more risk; inverted in total. Unknown dates and configured warning phrases increase risk.'}
    components={k:round(max(0,min(100,v)),3) for k,v in components.items()}
    total=sum(weights[k]*(100-components[k] if k=='risk' else components[k]) for k in DIMENSIONS)/sum(weights.values())
    return IdeaScore(idea_id=idea['id'],idea_version=idea['version'],components=components,weights=weights,final_score=round(total,3),rationale=rationale,config_sha256=digest(config['scoring']),as_of=as_of,
        provenance={'origin':'configured_editorial_heuristics','statistically_predictive':False,'profile_sha256':digest(profile)})
