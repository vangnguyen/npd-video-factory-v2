export const timedSubtitleModes = ['word_highlight', 'word_by_word', 'karaoke'];

export function subtitleCueEdit(original, values) {
  const cue = {...values, text: values.text.normalize('NFC').trim()};
  const unchanged = original && original.text.normalize('NFC') === cue.text
    && original.start_seconds === cue.start_seconds && original.end_seconds === cue.end_seconds;
  return {...cue, words: unchanged ? structuredClone(original.words ?? []) : []};
}

export function compatibleSubtitleTemplates(catalog, cues) {
  const aligned = cues.length > 0 && cues.every(cue => cue.words?.length > 0);
  return (catalog?.templates ?? []).map(template => ({...template,
    disabled: template.requires_word_timestamps && !aligned}));
}

export function subtitleSaveStyle(base, template, values) {
  const style = {...base, ...(template?.style ?? {}), ...values};
  // Keep old strict APIs usable when no new template/effect was selected.
  if (!template && !base.template_ref && !['word_by_word','karaoke','keyword_highlight'].includes(style.animation)) {
    delete style.template_ref; delete style.keywords;
  }
  return style;
}
