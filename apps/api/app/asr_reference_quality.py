"""Reproducible reference comparisons; no transcript rewrite or approval authority."""
import hashlib,unicodedata

NORMALIZER='unicode-nfc-casefold-letter-number-whitespace.v1'

def normalize_text(value):
    if not isinstance(value,str) or len(value.encode('utf-8'))>128*1024:raise ValueError('ASR_REFERENCE_TEXT_INVALID')
    text=unicodedata.normalize('NFC',value).casefold()
    return ' '.join(''.join(c if c.isspace() or unicodedata.category(c)[0] in 'LNM' else ' ' for c in text).split())

def distance(reference,hypothesis):
    if len(reference)>10000 or len(hypothesis)>10000:raise ValueError('ASR_REFERENCE_SEQUENCE_LIMIT')
    previous=list(range(len(hypothesis)+1))
    for i,expected in enumerate(reference,1):
        current=[i]
        for j,observed in enumerate(hypothesis,1):
            current.append(min(previous[j]+1,current[j-1]+1,previous[j-1]+(expected!=observed)))
        previous=current
    return previous[-1]

def assessment(reference,hypothesis):
    expected=normalize_text(reference);observed=normalize_text(hypothesis)
    tokens=expected.split();actual=observed.split()
    if not tokens:raise ValueError('ASR_REFERENCE_EMPTY')
    chars=list(expected.replace(' ',''));hyp_chars=list(observed.replace(' ',''))
    token_errors=distance(tokens,actual);char_errors=distance(chars,hyp_chars)
    return {'normalizer':NORMALIZER,'reference_sha256':hashlib.sha256(reference.encode()).hexdigest(),
        'hypothesis_sha256':hashlib.sha256(hypothesis.encode()).hexdigest(),'reference_tokens':len(tokens),
        'hypothesis_tokens':len(actual),'token_edit_distance':token_errors,'whitespace_token_error_rate':token_errors/len(tokens),
        'reference_characters':len(chars),'character_edit_distance':char_errors,'character_error_rate':char_errors/len(chars),
        'timestamps_evaluated':False,'proper_names_evaluated':False,'approval_granted':False}

def aggregate(items):
    if not items or any(item.get('normalizer')!=NORMALIZER for item in items):raise ValueError('ASR_REFERENCE_COHORT_INVALID')
    words=sum(i['reference_tokens'] for i in items);chars=sum(i['reference_characters'] for i in items)
    if not words or not chars:raise ValueError('ASR_REFERENCE_EMPTY')
    errors=sum(i['token_edit_distance'] for i in items);character_errors=sum(i['character_edit_distance'] for i in items)
    return {'samples':len(items),'reference_tokens':words,'token_edit_distance':errors,'whitespace_token_error_rate':errors/words,
        'reference_characters':chars,'character_edit_distance':character_errors,'character_error_rate':character_errors/chars,
        'normalizer':NORMALIZER,'sample_scope_only':True,'full_ASR_quality_accepted':False}
