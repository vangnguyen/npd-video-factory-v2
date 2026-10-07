import {renderNativeJob} from './native-job-render';

// Dependencies can report browser URLs and caption exceptions. The private
// job driver emits its own allowlisted progress/receipt/error events below.
console.log=console.info=console.warn=console.error=()=>undefined;

try {
  if(process.argv.length!==3&&(process.argv.length!==4||process.argv[3]!=='--preview'))throw new Error('NATIVE_RENDER_JOB_PATH_INVALID');
  const receipt=await renderNativeJob(process.argv[2],undefined,{preview:process.argv[3]==='--preview'});
  process.stdout.write(JSON.stringify(receipt)+'\n');
}catch(error){
  const message=error instanceof Error?error.message:'';
  const code=/^NATIVE_RENDER_[A-Z_]+$/.test(message)?message:
    message.includes('SUBTITLE_LAYOUT_OVERFLOW:')?'SUBTITLE_LAYOUT_OVERFLOW':'NATIVE_RENDER_FAILED';
  // No stack, paths, signed media URLs or caption text in public process output.
  process.stderr.write(JSON.stringify({status:'failed',error_code:code})+'\n');
  process.exitCode=1;
}
