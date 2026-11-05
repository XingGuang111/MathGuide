let sessionId=null, busy=false;
let completedQuestion=false;
let homeworkItemId=null;
const chat=document.querySelector('#chat'), input=document.querySelector('#input');
const notesContent=document.querySelector('#thinking-notes-content');
function showNotes(summary){
  if(!summary){notesContent.innerHTML='<p class="notes-empty">发来一道题，我会在这里记下条件、目标和已经确认的思路。</p>';return}
  const rows=[...(summary.shape?[{label:'形状',value:summary.shape}]:[]),...(summary.conditions||[])];
  const conditions=rows.map(item=>`<li><span>${esc(item.label)}<strong>${esc(item.value)}</strong></span><small class="${item.confirmed?'is-confirmed':''}">${item.confirmed?'✓ 已确认':'题目给出'}</small></li>`).join('');
  notesContent.innerHTML=`<p class="notes-stage">${esc(summary.status)}</p><details class="notes-question"><summary>回看本题</summary><p>${esc(summary.question)}</p></details>${conditions?`<div class="notes-section"><h4>题目告诉我们</h4><ul>${conditions}</ul></div>`:''}<div class="notes-section"><h4>我们要求什么${summary.target_confirmed?'<small>✓ 已确认</small>':''}</h4><p>${esc(summary.target||'还在一起读题，找出要求的内容。')}</p></div>${summary.method?`<div class="notes-section"><h4>已确认的思路</h4><p>${esc(summary.method)}</p></div>`:''}${summary.expression?`<div class="notes-section"><h4>已确认的算式</h4><p class="notes-expression">${esc(summary.expression)}</p></div>`:''}${summary.completed?.length?`<div class="notes-done">${summary.completed.map(step=>`<span>✓ ${esc(step)}</span>`).join('')}</div>`:''}<p class="notes-next">${esc(summary.next_step)}</p>`;
}
function clearQuestion(){
  homeworkItemId=null;document.querySelector('#tutor-homework-return')?.remove();
  sessionId=null;completedQuestion=false;remember();input.value='';chat.replaceChildren();showNotes(null);
  document.querySelector('#formula').innerHTML='<h3>知识卡片</h3><p class="muted">新题准备好啦！发来题目，就能看到对应的公式和提醒。</p>';
  statusLine.textContent='';photoInput.value='';
}
function add(text,who){chat.querySelector('.welcome-note')?.remove();const el=document.createElement('div');el.className=`msg ${who}`;el.textContent=text;chat.append(el);chat.scrollTop=chat.scrollHeight}
function esc(value){const el=document.createElement('div');el.textContent=value??'';return el.innerHTML}
function showCard(data){
  const card=data.card;
  if(!card){document.querySelector('#formula').innerHTML='<h3>知识卡片</h3><p>暂未匹配公式，将直接启发辅导。</p>';return}
  const grade=card.grade?`<p class="grade">📚 ${esc(card.grade)}</p>`:'';
  const temp=card.is_temp?'<p class="temp-badge">AI 生成</p>':'';
  const qtype=data.question_type?`<p>题型：${esc(data.question_type)}</p>`:'';
  document.querySelector('#formula').innerHTML=`<h3>${esc(card.knowledge_point)}</h3>${temp}${grade}${qtype}<p>公式：${esc(card.formula)}</p><p>易错提示：${esc(card.easy_tip)}</p>`;
}
function showAlert(text){
  const banner=document.querySelector('#alert-banner');
  if(!banner||!text)return;
  banner.textContent=text;banner.classList.add('show');
  clearTimeout(showAlert._t);
  showAlert._t=setTimeout(()=>banner.classList.remove('show'),3500);
}
async function loadStats(){try{const rows=await api('/api/stats');window.MathGuideLearning?.updateStats(rows)}catch(error){document.querySelector('#stats').textContent='统计暂时无法加载。'}}
const sendButton = document.querySelector('#send');
const newButton = document.querySelector('#new');
const photoInput = document.querySelector('#photo');
const statusLine = document.createElement('p');
statusLine.setAttribute('role', 'status');
statusLine.style.cssText = 'margin:0;padding:0 16px 8px;color:#667085';
document.querySelector('.composer').after(statusLine);
function waiting(value, text='老师正在思考…') {
  busy=value; sendButton.disabled=value; newButton.disabled=value; photoInput.disabled=value;
  window.MathGuidePet?.setLearning(value);
  sendButton.textContent=value?'想一想…':'发送 ✦'; statusLine.textContent=value?text:'';
}
function remember() {
  if(sessionId) localStorage.setItem('mathguide.session',sessionId);
  else localStorage.removeItem('mathguide.session');
}
async function sendMessage() {
  const text=input.value.trim(); if(!text||busy)return;
  if(completedQuestion)clearQuestion();
  waiting(true); input.value=''; add(text,'student');
  try {
    const starting=!sessionId;
    const data=await api(starting?'/api/sessions':'/api/replies',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(starting?{question:text,...(homeworkItemId?{homework_item_id:homeworkItemId}:{})}:{session_id:sessionId,message:text})
    });
    // clarify：题目不完整，AI 的反问作为普通提示；不创建 session，学生补充后重发
    if(data.clarify){add(data.message,'teacher');return}
    if(starting){sessionId=data.session_id;showCard(data);if(homeworkItemId)window.dispatchEvent(new CustomEvent('mathguide:homework-session',{detail:{itemId:homeworkItemId,sessionId}}));}
    else if(data.card){showCard({card:data.card})}
    showNotes(data.summary||{question:text,conditions:[],status:'正在整理',next_step:'和老师一起读题，确认条件和目标。'});
    add(data.reply,'teacher');
    if(data.pet_reaction)window.MathGuidePet?.react(data.pet_reaction);
    if(data.pet_progress_event)window.MathGuidePet?.claimReward(data.pet_progress_event);
    if(data.finished&&data.practice_knowledge_id){
      const button=document.createElement('button');button.className='secondary';button.textContent='试一道同类题';
      button.onclick=()=>openRelatedPractice(data.practice_knowledge_id);chat.append(button);
    }
    if(data.alert)showAlert(data.alert);
    if(data.retryable){input.value=text;statusLine.textContent='调用失败，内容已保留，可再次发送。'}
    if(data.finished){window.MathGuidePet?.claimReward('tutor:'+sessionId);sessionId=null;completedQuestion=true;loadStats()}
    remember();
  } catch(error) {
    input.value=text; add(`提示：${error.message}`,'teacher');
    if(error.status===404){sessionId=null;remember();add('会话已过期，请重新发送题目。','teacher')}
  } finally {waiting(false);input.focus()}
}
// 为错误恢复保留 HTTP 状态，并把输入校验错误转换为可读提示。
async function api(url, options={}) {
  const response=await fetch(url,options);const data=await response.json().catch(()=>({}));
  if(!response.ok){const detail=Array.isArray(data.detail)?'输入内容不符合要求，请检查后重试。':data.detail;
    const error=new Error(detail||'请求失败，请稍后重试。');error.status=response.status;throw error}
  return data;
}
sendButton.onclick=sendMessage;
input.onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();sendMessage()}};
newButton.onclick=async()=>{
  if(busy)return;waiting(true);
  try{
    if(sessionId){try{await api('/api/sessions/abort',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId})})}catch(error){if(error.status!==404)throw error}}
    clearQuestion();
  }catch(error){showAlert(error.message)}
  finally{waiting(false);input.focus()}
};
photoInput.onchange=async event=>{
  const file=event.target.files[0];if(!file||busy)return;
  if(sessionId){add('请先点击“换一道题”，再上传新题目。','teacher');event.target.value='';return}
  if(file.size>10*1024*1024){add('图片不能超过 10 MB。','teacher');event.target.value='';return}
  if(completedQuestion)clearQuestion();
  waiting(true,'正在识别图片…');const form=new FormData();form.append('image',file);
  try{const data=await api('/api/ocr',{method:'POST',body:form});input.value=data.text;add('识别完成，请检查题目文字后发送。','teacher')}
  catch(error){add(`识别失败：${error.message}`,'teacher')}
  finally{waiting(false);event.target.value='';input.focus()}
};
document.querySelector('.upload').onkeydown=event=>{
  if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){
    event.preventDefault();if(!photoInput.disabled)photoInput.click();
  }
};
async function loadRecords(){
  await window.MathGuideLearning.loadDialogRecords();
}
document.querySelector('#history').onclick=()=>window.MathGuideLearning.open('records');
document.querySelector('#close-records').onclick=()=>document.querySelector('#records').close();
document.querySelector('#filters').onsubmit=event=>{event.preventDefault();loadRecords()};
async function restoreSession(){
  const saved=localStorage.getItem('mathguide.session');if(!saved)return;waiting(true,'正在恢复上次辅导…');
  try{const data=await api('/api/sessions/'+encodeURIComponent(saved));sessionId=saved;homeworkItemId=data.homework_item_id||null;homeworkReturn();showCard(data);showNotes(data.summary);chat.replaceChildren();add(data.question,'student');for(const message of data.dialogue)add(message.content,message.role==='student'?'student':'teacher');add('已恢复上次辅导，可以继续回答。','teacher')}
  catch(error){localStorage.removeItem('mathguide.session');add('上次会话无法恢复，请重新开始题目。','teacher')}
  finally{waiting(false)}
}
function homeworkReturn(){
  document.querySelector('#tutor-homework-return')?.remove();
  if(!homeworkItemId)return;
  const button=document.createElement('button');button.id='tutor-homework-return';button.className='secondary';button.textContent='← 返回本题作业 · 作答与反思';
  button.onclick=()=>window.MathGuideHomework?.returnToItem(homeworkItemId);
  document.querySelector('.tutor-heading').after(button);
}
window.MathGuideTutor = {
  prepareQuestion(question) {
    if(busy || sessionId) return false;
    if(completedQuestion) clearQuestion();
    input.value=question;
    window.MathGuideWorkspace.show('tutor');
    input.focus();
    return true;
  },
  async openHomework(item) {
    if(busy || (sessionId && !homeworkItemId))return false;
    if(sessionId===item.tutor_session_id && homeworkItemId===item.id){window.MathGuideWorkspace.show('tutor');return true;}
    let data=null;
    if(item.tutor_session_id){
      try{data=await api('/api/sessions/'+encodeURIComponent(item.tutor_session_id));}
      catch(error){if(error.status!==404)throw error;}
    }
    clearQuestion();homeworkItemId=item.id;homeworkReturn();
    if(data){
      sessionId=data.session_id;showCard(data);showNotes(data.summary);add(data.question,'student');
      for(const message of data.dialogue)add(message.content,message.role==='student'?'student':'teacher');
      remember();
    }else input.value=item.text;
    window.MathGuideWorkspace.show('tutor');input.focus();return true;
  }
};
restoreSession();
loadStats();
api('/api/health').then(data=>{const el=document.querySelector('#health');el.textContent=data.ok?'● 模型已就绪':'● 模型未就绪';el.style.color=data.ok?'#07875d':'#c2410c';el.title=data.message;document.querySelector('#learning-demo-notice').hidden=!data.demo}).catch(()=>document.querySelector('#health').textContent='服务检查失败');
api('/api/qrcode').then(data=>{
  if(!data||!data.qrcode)return;
  const card=document.querySelector('#qrcode-card');
  if(card)card.classList.remove('hidden');
  const img=document.querySelector('#qrcode-img');
  if(img)img.src=data.qrcode;
  const url=document.querySelector('#qrcode-url');
  if(url)url.textContent=data.url;
}).catch(()=>{});

let exerciseId=localStorage.getItem('mathguide.practice'), practiceBusy=false;
const practiceDialog=document.querySelector('#practice-dialog');
const practiceFeedback=document.querySelector('#practice-feedback');
function practiceWait(value){practiceBusy=value;for(const id of ['practice-submit','practice-next','practice-hint'])document.querySelector('#'+id).disabled=value}
function showExercise(data){
  exerciseId=data.id;localStorage.setItem('mathguide.practice',exerciseId);
  document.querySelector('#practice-topic').textContent=data.knowledge_point;
  document.querySelector('#practice-question').textContent=data.question;
  document.querySelector('#practice-unit').textContent=data.answer_unit?`单位：${data.answer_unit}`:'填写数值或分数';
  document.querySelector('#practice-answer').value='';
  document.querySelector('#practice-answer').disabled=data.answered;
  document.querySelector('#practice-form').hidden=data.answered;
  document.querySelector('#practice-hint').hidden=data.answered;
  practiceFeedback.textContent=data.answered?`${data.feedback}\n你的答案：${data.answer}\n参考答案：${data.expected}\n思路：${data.explanation}`:data.hinted?'本题已查看提示，不计为独立答对。':'';
  window.MathGuidePet?.react(data.answered?(data.correct?'smile':'concerned'):'thinking');
}
async function nextExercise(){
  if(practiceBusy)return;practiceWait(true);practiceFeedback.textContent='正在安排练习…';
  try{showExercise(await api('/api/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}))}
  catch(error){practiceFeedback.textContent=error.message}
  finally{practiceWait(false)}
}

async function openRelatedPractice(knowledgeId){
  if(practiceBusy)return;practiceDialog.showModal();practiceWait(true);practiceFeedback.textContent='正在准备同类题…';
  try{showExercise(await api('/api/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({knowledge_id:knowledgeId})}))}
  catch(error){practiceFeedback.textContent=error.message}
  finally{practiceWait(false)}
}
document.querySelector('#practice').onclick=async()=>{
  if(practiceBusy)return;practiceDialog.showModal();
  if(!exerciseId){await nextExercise();return}
  practiceWait(true);
  try{showExercise(await api('/api/practice/'+encodeURIComponent(exerciseId)))}
  catch(error){if(error.status===404){exerciseId=null;localStorage.removeItem('mathguide.practice')}practiceFeedback.textContent=error.message}
  finally{practiceWait(false)}
  if(!exerciseId)await nextExercise();
};
document.querySelector('#practice-next').onclick=nextExercise;
document.querySelector('#practice-close').onclick=()=>practiceDialog.close();
document.querySelector('#practice-hint').onclick=async()=>{
  if(practiceBusy||!exerciseId)return;practiceWait(true);
  try{const data=await api('/api/practice/'+exerciseId+'/hint',{method:'POST'});practiceFeedback.textContent=`提示：${data.hint}\n公式：${data.formula}\n本题将计为使用提示的练习。`;window.MathGuidePet?.react('concerned')}
  catch(error){practiceFeedback.textContent=error.message}finally{practiceWait(false)}
};
document.querySelector('#practice-form').onsubmit=async event=>{
  event.preventDefault();if(practiceBusy||!exerciseId)return;
  const answer=document.querySelector('#practice-answer').value.trim();if(!answer)return;practiceWait(true);
  try{const data=await api('/api/practice/'+exerciseId+'/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer})});
    practiceFeedback.textContent=`${data.feedback}\n参考答案：${data.expected}\n思路：${data.explanation}\n${data.stats.practice_status}，连续独立答对 ${data.stats.streak} 题，复习优先分 ${data.stats.weak_score}`;
    window.MathGuidePet?.react(data.correct?(data.independent&&data.stats.streak>=3?'laugh':'smile'):'concerned');
    document.querySelector('#practice-form').hidden=true;document.querySelector('#practice-hint').hidden=true;await loadStats();
    window.MathGuidePet?.claimReward('practice:'+exerciseId);
  }catch(error){practiceFeedback.textContent=error.message}finally{practiceWait(false)}
};
