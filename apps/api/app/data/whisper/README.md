# Offline Whisper prompt tokenizer data

This directory contains text vocabulary DATA, not model weights. No inference is
performed. The original MIT notice accompanies the vendored rank file.

Pinned upstream: OpenAI Whisper commit
`86098128c0b4f24f0e2aa2994de830614b474227`.

- [Vocabulary](https://github.com/openai/whisper/blob/86098128c0b4f24f0e2aa2994de830614b474227/whisper/assets/multilingual.tiktoken)
- [Tokenizer/regex](https://github.com/openai/whisper/blob/86098128c0b4f24f0e2aa2994de830614b474227/whisper/tokenizer.py)
- [Upstream prompt context preprocessing](https://github.com/openai/whisper/blob/86098128c0b4f24f0e2aa2994de830614b474227/whisper/decoding.py)
- [Tiktoken 0.12.0 constructor](https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/tiktoken/core.py)

Runtime uses `tiktoken==0.12.0` directly with local hash-verified ranks and the
upstream Unicode regex. It does not call the encoding registry, cache/network
loaders, Whisper, Torch, or a model. The exact allowlisted profiles contain
ordinary text; special/control tokens are not part of these text token counts.

Raw W1: 105 UTF-8 bytes / 34 tokens. Upstream context form (`" " + prompt.strip()`):
106 bytes / 33 tokens. Raw bytes sent to the provider remain unchanged; context
preprocessing is counted separately, not applied to the request. These are exact
local source-derived counts, not proof of undocumented hosted preprocessing.

Raw W2: 149 UTF-8 bytes / 43 tokens. Its upstream context form is 150 bytes /
43 tokens. W2 is a distinct explicit selection; it is neither the default nor an
automatic W1 fallback.

Only the fixed W1 and W2 profiles are accepted. No arbitrary prompt, truncation,
reference transcript injection or temperature adjustment is enabled by this
module. The profile and vocabulary hashes, token count, package version and
complete JSON profile must all validate again before a future separately
authorized execution.

The existing 224-token documentation limit is a ceiling, not authority. Package
presence or a valid profile never enables a provider call or grants a new gate.
