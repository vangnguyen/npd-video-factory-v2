export const asrLanguageChoices=Object.freeze([
  Object.freeze({value:'legacy',label:'Tiếng Việt · profile hiện tại'}),
  Object.freeze({value:'vi',label:'Tiếng Việt · tổng quát'}),
  Object.freeze({value:'en',label:'Tiếng Anh · tổng quát'}),
  Object.freeze({value:'auto',label:'Tự phát hiện tiếng Việt / Anh'}),
]);

export function asrLanguageSelection(value,enabled=false){
  if(!enabled)return {request:undefined,keySuffix:''};
  if(!asrLanguageChoices.some(choice=>choice.value===value))throw Error('Chọn ngôn ngữ nhận diện hợp lệ.');
  return value==='legacy'?{request:undefined,keySuffix:''}:{request:{language:value},keySuffix:`-studio-${value}-v1`};
}

export function asrLanguageHint(value){
  if(!asrLanguageChoices.some(choice=>choice.value===value))throw Error('Chọn ngôn ngữ nhận diện hợp lệ.');
  const language=value==='auto'?'phát hiện ngôn ngữ từ âm thanh':value==='en'?'nhận diện tiếng Anh':'nhận diện tiếng Việt';
  return `Âm thanh nguồn sẽ được gửi đến AssemblyAI để ${language} và có thể phát sinh phí. Kiểm tra transcript trước khi dùng. Lựa chọn áp dụng cho nguồn chưa được phân tích; kết quả đã lưu được giữ nguyên.`;
}
