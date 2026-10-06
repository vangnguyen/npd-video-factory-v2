"""Pure source selection that extends edges to complete measured speech."""
from __future__ import annotations


def protected_window(start,end,transcript,duration):
    """Extend selection outward, never cut through a measured word/speech interval."""
    intervals=[]
    if transcript:
        for segment in transcript.segments:
            intervals.extend((word.start_seconds,word.end_seconds) for word in segment.words)
            if not segment.words:intervals.append((segment.start_seconds,segment.end_seconds))
    # Expansions can touch another interval; reach a fixed point without guessing words.
    while True:
        before=(start,end)
        for a,b in intervals:
            if a<start<b:start=a
            if a<end<b:end=b
        if before==(start,end):break
    return max(0.,start),min(duration,end)


