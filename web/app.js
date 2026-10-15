let sessionId=null, busy=false;
const chat=document.querySelector('#chat'), input=document.querySelector('#input');
function add(text,who){const el=document.createElement('div');el.className=`msg ${who}`;el.textContent=text;chat.append(el);chat.scrollTop=chat.scrollHeight}
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
async function loadStats(){try{const rows=await api('/api/stats');document.querySelector('#stats').innerHTML=rows.length?rows.slice(0,6).map(row=>`<li>${esc(row.knowledge_point)}：历史 ${row.not_understood}/${row.total} 次未独立理解<br>专项练习 ${row.independent_correct??0}/${row.practice_total??0} 独立答对，${esc(row.practice_status??'待练习')}<br>复习优先分 ${row.weak_score??row.not_understood*2}</li>`).join(''):'<li class="muted">暂无学习记录，可先做基础练习</li>'}catch(error){document.querySelector('#stats').textContent='统计暂时无法加载。'}}
const sendButton = document.querySelector('#send');
const newButton = document.querySelector('#new');
const photoInput = document.querySelector('#photo');
const statusLine = document.createElement('p');
statusLine.setAttribute('role', 'status');
statusLine.style.cssText = 'margin:0;padding:0 16px 8px;color:#667085';
document.querySelector('.composer').after(statusLine);
function waiting(value, text='老师正在思考…') {
  busy=value; sendButton.disabled=value; newButton.disabled=value; photoInput.disabled=value;
  sendButton.textContent=value?'请稍候':'发送'; statusLine.textContent=value?text:'';
}
function remember() {
  if(sessionId) localStorage.setItem('mathguide.session',sessionId);
  else localStorage.removeItem('mathguide.session');
}
async function sendMessage() {
  const text=input.value.trim(); if(!text||busy)return;
  waiting(true); input.value=''; add(text,'student');
  try {
    const starting=!sessionId;
    const data=await api(starting?'/api/sessions':'/api/replies',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(starting?{question:text}:{session_id:sessionId,message:text})
    });
    // clarify：题目不完整，AI 的反问作为普通提示；不创建 session，学生补充后重发
    if(data.clarify){add(data.message,'teacher');return}
    if(starting){sessionId=data.session_id;showCard(data)}
    else if(data.card){showCard({card:data.card})}
    add(data.reply,'teacher');
    if(data.alert)showAlert(data.alert);
    if(data.retryable){input.value=text;statusLine.textContent='调用失败，内容已保留，可再次发送。'}
    if(data.finished){sessionId=null;loadStats()}
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
  try{if(sessionId)await api('/api/sessions/abort',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId})});
    sessionId=null;remember();input.value='';document.querySelector('#formula').innerHTML='<h3>知识卡片</h3><p>开始题目后显示公式。</p>';add('好的，请发送新题目。','teacher');
  }catch(error){if(error.status===404){sessionId=null;remember()}else add(error.message,'teacher')}
  finally{waiting(false)}
};
photoInput.onchange=async event=>{
  const file=event.target.files[0];if(!file||busy)return;
  if(sessionId){add('请先点击“换一道题”，再上传新题目。','teacher');event.target.value='';return}
  if(file.size>10*1024*1024){add('图片不能超过 10 MB。','teacher');event.target.value='';return}
  waiting(true,'正在识别图片…');const form=new FormData();form.append('image',file);
  try{const data=await api('/api/ocr',{method:'POST',body:form});input.value=data.text;add('识别完成，请检查题目文字后发送。','teacher')}
  catch(error){add(`识别失败：${error.message}`,'teacher')}
  finally{waiting(false);event.target.value='';input.focus()}
};
async function loadRecords(){
  const status=document.querySelector('#record-status'),list=document.querySelector('#record-list');
  const params=new URLSearchParams();const date=document.querySelector('#record-date').value,type=document.querySelector('#record-type').value;
  if(date)params.set('date',date);if(type)params.set('qtype',type);status.textContent='正在查询…';list.replaceChildren();document.querySelector('#record-detail').replaceChildren();
  try{const rows=await api('/api/history?'+params);status.textContent=rows.length?`共 ${rows.length} 条记录`:'没有找到相关记录。';
    for(const row of rows){const button=document.createElement('button');button.className='secondary';button.style.cssText='display:block;width:100%;text-align:left;margin:10px 0';
      button.textContent=`${row.record_date} · ${row.question_type} · ${row.understood?'独立解出':'讲解后复习'}\n${row.question_text}`;
      button.onclick=()=>{const detail=document.querySelector('#record-detail');detail.replaceChildren();const title=document.createElement('h3');title.textContent=row.question_text;detail.append(title);const formula=document.createElement('p');formula.textContent=`${row.knowledge_point}：${row.formula}`;detail.append(formula);
        for(const message of row.dialogue){const el=document.createElement('div');el.className='msg '+(message.role==='student'?'student':'teacher');el.textContent=message.content;detail.append(el)}};
      list.append(button)}
  }catch(error){status.textContent=error.message}
}
document.querySelector('#history').onclick=()=>{document.querySelector('#records').showModal();loadRecords()};
document.querySelector('#close-records').onclick=()=>document.querySelector('#records').close();
document.querySelector('#filters').onsubmit=event=>{event.preventDefault();loadRecords()};
async function restoreSession(){
  const saved=localStorage.getItem('mathguide.session');if(!saved)return;waiting(true,'正在恢复上次辅导…');
  try{const data=await api('/api/sessions/'+encodeURIComponent(saved));sessionId=saved;showCard(data);chat.replaceChildren();add(data.question,'student');for(const message of data.dialogue)add(message.content,message.role==='student'?'student':'teacher');add('已恢复上次辅导，可以继续回答。','teacher')}
  catch(error){localStorage.removeItem('mathguide.session');add('上次会话无法恢复，请重新开始题目。','teacher')}
  finally{waiting(false)}
}
restoreSession();
loadStats();
api('/api/health').then(data=>{const el=document.querySelector('#health');el.textContent=data.ok?'● 模型已就绪':'● 模型未就绪';el.style.color=data.ok?'#07875d':'#c2410c';el.title=data.message}).catch(()=>document.querySelector('#health').textContent='服务检查失败');

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
}
async function nextExercise(){
  if(practiceBusy)return;practiceWait(true);practiceFeedback.textContent='正在安排练习…';
  try{showExercise(await api('/api/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}))}
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
  try{const data=await api('/api/practice/'+exerciseId+'/hint',{method:'POST'});practiceFeedback.textContent=`提示：${data.hint}\n公式：${data.formula}\n本题将计为使用提示的练习。`}
  catch(error){practiceFeedback.textContent=error.message}finally{practiceWait(false)}
};
document.querySelector('#practice-form').onsubmit=async event=>{
  event.preventDefault();if(practiceBusy||!exerciseId)return;
  const answer=document.querySelector('#practice-answer').value.trim();if(!answer)return;practiceWait(true);
  try{const data=await api('/api/practice/'+exerciseId+'/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer})});
    practiceFeedback.textContent=`${data.feedback}\n参考答案：${data.expected}\n思路：${data.explanation}\n${data.stats.practice_status}，连续独立答对 ${data.stats.streak} 题，复习优先分 ${data.stats.weak_score}`;
    document.querySelector('#practice-form').hidden=true;document.querySelector('#practice-hint').hidden=true;await loadStats();
  }catch(error){practiceFeedback.textContent=error.message}finally{practiceWait(false)}
};
