import type {TimelineRenderManifest} from './types';

type Cue = TimelineRenderManifest['subtitles'][number];
type Style = TimelineRenderManifest['subtitle_style'];
export type CaptionPart = {text: string; wordIndex: number | null; highlighted: boolean; progress: number};

export const timedCaptionModes = ['word_highlight', 'word_by_word', 'karaoke'];

export const assertTimedCaptionText = (cue: Cue, style: Style): void => {
  if (style.animation === 'word_by_word') {
    const tokens = (text: string) => [...text.normalize('NFC').matchAll(/[\p{L}\p{N}]+/gu)]
      .map(match => match[0].toLocaleLowerCase('vi'));
    if (JSON.stringify(tokens(cue.text)) !== JSON.stringify(tokens(cue.words.map(word=>word.text).join(' ')))) {
      throw new Error('WORD_ALIGNMENT_TEXT_MISMATCH: select sentence captions');
    }
  }
  if (style.animation === 'karaoke') captionParts(cue, style, cue.start_seconds);
};

/** Token boundaries use Unicode letters/numbers, preserving Vietnamese accents. */
export const keywordParts = (text: string, keywords: string[]): CaptionPart[] => {
  const normalized = text.normalize('NFC');
  const tokens = [...normalized.matchAll(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu)];
  const marked = new Set<number>();
  for (const keyword of keywords) {
    const wanted = [...keyword.normalize('NFC').matchAll(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu)]
      .map(match => match[0].toLocaleLowerCase('vi'));
    if (!wanted.length) continue;
    for (let i = 0; i <= tokens.length - wanted.length; i++) {
      if (wanted.every((word, offset) => tokens[i + offset][0].toLocaleLowerCase('vi') === word)) {
        for (let j = 0; j < wanted.length; j++) marked.add(i + j);
      }
    }
  }
  const result: CaptionPart[] = [];
  let cursor = 0;
  tokens.forEach((token, index) => {
    if (token.index! > cursor) result.push({text: normalized.slice(cursor, token.index), wordIndex: null, highlighted: false, progress: 0});
    result.push({text: token[0], wordIndex: null, highlighted: marked.has(index), progress: marked.has(index) ? 1 : 0});
    cursor = token.index! + token[0].length;
  });
  if (cursor < normalized.length) result.push({text: normalized.slice(cursor), wordIndex: null, highlighted: false, progress: 0});
  return result;
};

/** Never interpolate a missing word timestamp. Gaps remain gaps. */
export const captionParts = (cue: Cue, style: Style, seconds: number): CaptionPart[] => {
  if (style.animation === 'keyword_highlight') return keywordParts(cue.text, style.keywords ?? []);
  if (style.animation === 'word_by_word') {
    const index = cue.words.findIndex(word => seconds >= word.start_seconds && seconds < word.end_seconds);
    return index < 0 ? [] : [{text: cue.words[index].text.normalize('NFC'), wordIndex: index, highlighted: true, progress: 1}];
  }
  if (style.animation === 'karaoke') {
    const text = cue.text.normalize('NFC');
    const result: CaptionPart[] = [];
    let cursor = 0;
    for (let index = 0; index < cue.words.length; index++) {
      const word = cue.words[index];
      const value = word.text.normalize('NFC');
      const start = text.toLocaleLowerCase('vi').indexOf(value.toLocaleLowerCase('vi'), cursor);
      if (start < 0) throw new Error('WORD_ALIGNMENT_TEXT_MISMATCH: select sentence captions');
      if (start > cursor) result.push({text: text.slice(cursor, start), wordIndex: null, highlighted: false, progress: 0});
      const progress = Math.max(0, Math.min(1, (seconds - word.start_seconds) / (word.end_seconds - word.start_seconds)));
      result.push({text: text.slice(start, start + value.length), wordIndex: index, highlighted: progress > 0, progress});
      cursor = start + value.length;
    }
    if (cursor < text.length) result.push({text: text.slice(cursor), wordIndex: null, highlighted: false, progress: 0});
    return result;
  }
  if (style.animation === 'word_highlight' && cue.words.length) {
    // Keep historical aligned-highlight presentation unchanged.
    return cue.words.map((word, index) => ({text: `${index ? ' ' : ''}${word.text}`, wordIndex: index,
      highlighted: seconds >= word.start_seconds && seconds < word.end_seconds, progress: 0}));
  }
  return [{text: cue.text.normalize('NFC'), wordIndex: null, highlighted: false, progress: 0}];
};
