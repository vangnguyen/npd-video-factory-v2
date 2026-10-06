// Source-relative measured samples stay correct after canonical trim/split/move.
export function waveformPath(clip){
  const waveform=clip?.metadata?.source_audio_waveform;
  if(!waveform?.measured||waveform.method!=='ffmpeg-mono-pcm-peak-rms-v1'||!Array.isArray(waveform.bins))return null;
  const start=clip.source_start??0,end=clip.source_end??(start+clip.duration*(clip.speed??1));
  if(!(end>start))return null;
  const points=waveform.bins.filter(b=>Number.isFinite(b.peak)&&b.peak>=0&&b.end_seconds>start&&b.start_seconds<end)
    .map(b=>({x:Math.max(0,Math.min(100,(((b.start_seconds+b.end_seconds)/2-start)/(end-start))*100)),
             amplitude:Math.min(1,b.peak)*44}));
  if(!points.length)return null;
  return points.map(p=>`M${p.x.toFixed(3)} ${(50-p.amplitude).toFixed(3)}V${(50+p.amplitude).toFixed(3)}`).join(' ');
}
