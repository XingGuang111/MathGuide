/* Local assignment drafts, real AI feedback and server-backed student reflections. */
(() => {
  'use strict';
  const root = document.querySelector('#homework-view');
  const $ = id => root.querySelector('#' + id);
  const key = 'mathguide.homework.ui.v1';
  const today = new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai'}).format(new Date());
  const safe = value => {const node=document.createElement('span');node.textContent=value??'';return node.innerHTML;};
  const uid = () => crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)+Math.random().toString(36).slice(2);
  const labels = {todo:'待提交', skipped:'稍后再做', review:'待提交', done:'AI 分析通过', revision:'需要订正', uncertain:'待核实'};
  const verdicts = {correct:'AI 分析通过', incorrect:'需要订正', uncertain:'待核实，暂不判分'};
  const pending = new Set();
  let batching=false, recordFilter='all', recordRequest=0;
  const fresh = () => ({version:1,id:uid(),revision:0,title:'今天的数学作业',date:today,items:[],active:null,demo:false,draft:null,source_ids:[],sources:[],dirty:false});
  let state=fresh(), mode='student', edits=[], photos=[], storageError='';
  let ready=false, syncTimer, syncing=null, conflict=false, change=0, uploading=false, photoBusy=false;
  let importedSources=[];
  const visualBusy=new Set(), visualMessages=new Map(), visualDrafts=new Map();
  let visualRequest=0,cropTarget=null,visualLoadedKey='';
  try {
    const raw=JSON.parse(localStorage.getItem(key)||'null');
    if(raw) {
      if(raw.version!==1 || !Array.isArray(raw.items) || raw.items.length>100 ||
         !raw.items.every(item => item && typeof item.id==='string' && typeof item.text==='string' && Object.hasOwn(labels,item.status))) throw Error();
      state={...fresh(),...raw};
      for(const item of state.items){delete item.savingReflection;if(!item.analysis && ['done','review'].includes(item.status))item.status='todo';}
    }
  } catch {storageError='上次的本机清单无法读取。原数据尚未覆盖，请先检查浏览器存储。';}
  const nav=document.createElement('button');nav.id='homework-tab';nav.className='workspace-tab';
  nav.setAttribute('aria-pressed','false');nav.innerHTML='<span aria-hidden="true">☷</span> 今日作业';
  document.querySelector('#tutor-tab').before(nav);
  root.innerHTML=`
    <div class="hw-topline"><span id="hw-date-label"></span><div class="hw-mode" aria-label="作业视角"><button id="hw-student-mode" aria-pressed="true">学生做作业</button><button id="hw-parent-mode" aria-pressed="false">家长布置</button></div></div>
    <header class="hw-hero"><div><div class="hw-eyebrow">TODAY'S LITTLE ADVENTURE · 每日作业</div><h2 id="hw-heading">一小步，一道题，<br>今天的进步看得见。</h2><p id="hw-subtitle">把作业变成小清单，和星芽一起慢慢完成。</p><div class="hw-progress"><progress id="hw-progress" max="1" value="0" aria-label="作业完成进度"></progress><span id="hw-progress-text">等待今天的第一道题</span></div></div><img class="hw-hero-art" src="/assets/math-adventure.svg" alt="星星伙伴陪你打开数学书"></header>
    <div class="hw-overview"><div class="hw-metric"><span aria-hidden="true">☷</span><div><strong id="hw-total">0</strong><small>清单里的小任务</small></div></div><div class="hw-metric"><span aria-hidden="true">✓</span><div><strong id="hw-done">0</strong><small>AI 分析通过</small></div></div><div class="hw-metric"><span aria-hidden="true">◷</span><div><strong id="hw-remaining">0</strong><small>还可以慢慢完成</small></div></div></div>
    <p id="hw-message" class="hw-status" role="status" aria-live="polite"></p>
    <div id="hw-student"><div class="hw-actions hw-submit-bar"><span class="hw-help">写好答案后，可以逐题提交，也可以一起提交分析。</span><button id="hw-submit-all">提交作业 · AI 分析</button></div>
      <section id="hw-empty" class="hw-card hw-empty"><span class="hw-empty-symbol" aria-hidden="true">▤ ✦</span><h3>今天的小清单，等你来开启</h3><p>请家长把数学作业放进来。<br>准备好后，我们就从第一道题出发。</p><button id="hw-empty-create">＋ 布置今天的作业</button><button id="hw-demo" class="hw-link">先看看示例 →</button></section>
      <div id="hw-study" class="hw-layout" hidden><aside class="hw-card"><div class="hw-card-head"><h3>我的作业清单</h3><span id="hw-count" class="hw-pill"></span></div><div id="hw-list" class="hw-list" aria-label="选择一道作业题"></div><p class="hw-list-note">难题可以先放一放，再回来想一想。</p></aside>
      <section class="hw-card"><div class="hw-card-head"><h3 id="hw-question-number"></h3><span id="hw-question-status" class="hw-pill"></span></div><div id="hw-question" class="hw-question"></div><div class="hw-teacher"><span aria-hidden="true">✦</span><div><b>老师的小提醒</b><p id="hw-teacher-copy">先试着自己想一想。需要帮助时，可以把这道题带到 AI 老师那里。</p></div></div><label for="hw-answer">写下你的答案或解题思路</label><textarea id="hw-answer" rows="3" maxlength="2000" placeholder="我发现……所以我这样算……"></textarea><div class="hw-answer-actions"><button id="hw-save-answer">提交本题 · AI 分析</button><button id="hw-tutor" class="hw-secondary">✦ 请 AI 老师帮忙</button><button id="hw-skip" class="hw-link">稍后再做</button></div><div class="hw-bottom"><span id="hw-answer-note">草稿自动保留；提交后由 AI 分析。</span><button id="hw-next" class="hw-secondary">下一题 →</button></div><section class="hw-review-panel"><div class="hw-card-head"><h3>分析与反思</h3><span class="hw-pill">每道题，都有收获</span></div><div id="hw-analysis" class="hw-analysis"></div><label id="hw-reflection-label" for="hw-reflection">这道题，我学到了什么？</label><textarea id="hw-reflection" rows="3" maxlength="2000" placeholder="我用了什么方法？哪里需要改进？下次怎样检查？"></textarea><div class="hw-collection-options"><label><input id="hw-in-notes" type="checkbox"> 计入学习笔记</label><label><input id="hw-in-mistakes" type="checkbox"> 加入错题集</label></div><button id="hw-save-reflection" class="hw-secondary">保存反思与收录选择</button><p class="hw-help">两项都可以选，也可以都不选。AI 分析是本次作答的反馈，不代表长期掌握。</p></section></section></div>
    </div>
    <div id="hw-parent" hidden><div class="hw-parent-layout"><section class="hw-card"><div class="hw-card-head"><h3>① 放入今天的作业</h3><span class="hw-pill">家长操作</span></div><div class="hw-fields"><label>作业名称<input id="hw-title" type="text" maxlength="60"></label><label>作业日期<input id="hw-date" type="date" required></label></div><div class="hw-source-tabs" aria-label="录入方式"><button id="hw-text-tab" aria-pressed="true">✎ 输入文字</button><button id="hw-photo-tab" aria-pressed="false">▧ 拍照 / 选照片</button></div><div id="hw-photo-panel" hidden><div class="hw-drop"><span aria-hidden="true">▧</span><strong>把整页作业放在这里</strong><p>支持多张 JPG、PNG、BMP，每张不超过 10 MB。</p><button id="hw-pick-photo" class="hw-secondary">＋ 选择照片</button><input id="hw-photos" type="file" accept="image/jpeg,image/png,image/bmp" multiple hidden></div><div id="hw-photo-grid" class="hw-photo-grid"></div><p class="hw-help">上传后点击识别，逐页加入清单并对照原图校正。照片和识别结果会随清单保存。</p></div><label for="hw-batch">批量输入题目</label><textarea id="hw-batch" rows="7" maxlength="30000" placeholder="1. 计算：36 ÷ 6 = ?&#10;2. 长方形长 8 厘米，宽 5 厘米，面积是多少？&#10;3. 小明有 24 颗糖，平均分给 6 个朋友，每人几颗？"></textarea><p class="hw-help">有题号时按题号分题，多行题干会保留；无题号时按空行或每行分题。共享条件请放进每道小题，再检查右侧清单。</p><button id="hw-split">整理到右侧清单 →</button></section>
      <section class="hw-card"><div class="hw-card-head"><h3>② 检查作业清单</h3><span id="hw-draft-count" class="hw-pill">0 道题</span></div><p class="hw-help">检查题干是否完整，可修改、调序、删除。发布后孩子就能逐题开始。</p><div id="hw-editor" class="hw-editor-list"></div><button id="hw-add" class="hw-link">＋ 手动添加一道题</button><div class="hw-editor-footer"><span class="hw-help">编辑内容自动保存在本机</span><button id="hw-publish">发布给孩子 →</button></div><div id="hw-parent-summary" class="hw-parent-summary" hidden></div><div class="hw-confirm"><h3>查看孩子的学习过程</h3><p class="hw-help">AI 分析、孩子的订正与反思都会保存在学习档案。无需家长批改作业。</p><button id="hw-open-records" class="hw-secondary">查看作业学习记录 →</button></div></section></div></div>
    <p class="hw-notice" id="hw-scope">清单、答案与照片自动保存，可在同一家庭服务的手机或电脑上继续。</p>`;
  root.querySelector('.hw-topline').insertAdjacentHTML('afterend',`<section class="hw-library" aria-label="作业管理"><label for="hw-assignment-select">我的作业</label><select id="hw-assignment-select"><option value="">选择已保存的作业</option></select><button id="hw-new-assignment" class="hw-secondary">＋ 新建作业</button><button id="hw-reload" class="hw-link">载入最新</button><span id="hw-sync-status" role="status">正在读取作业…</span><button id="hw-save-copy" class="hw-link" hidden>另存为新作业</button></section>`);
  $('hw-question').insertAdjacentHTML('afterend','<div id="hw-source-links" class="hw-source-links"></div>');
  $('hw-source-links').insertAdjacentHTML('beforebegin','<div id="hw-question-images" class="hw-question-images"></div>');
  $('hw-teacher-copy').closest('.hw-teacher').insertAdjacentHTML('afterend','<section id="hw-visual-tutor" class="hw-visual-tutor" hidden><h3>看图老师 · 一起观察</h3><p class="hw-help">老师会结合上方配图提问，图太小或看不清时会请你确认。</p><div id="hw-visual-messages" class="hw-visual-messages" role="log" aria-live="polite"></div><label for="hw-visual-input">你的发现或问题</label><textarea id="hw-visual-input" rows="2" maxlength="2000" placeholder="我找到了对称轴，但不知道怎样找对应点……"></textarea><button id="hw-visual-send" class="hw-secondary">发送给看图老师</button><p id="hw-visual-status" class="hw-help" role="status"></p></section>');
  $('hw-photo-grid').insertAdjacentHTML('afterend','<button id="hw-recognize-all" class="hw-secondary" hidden>识别全部照片</button>');
  root.insertAdjacentHTML('beforeend','<dialog id="hw-source-dialog" class="hw-source-dialog"><header><h3>对照原图校对</h3><button id="hw-source-close" class="hw-secondary" autofocus>关闭</button></header><p id="hw-source-hint" class="hw-help"></p><div id="hw-source-image"></div></dialog>');
  $('hw-source-image').insertAdjacentHTML('beforebegin','<div id="hw-crop-controls" hidden><p class="hw-help">调整本题截图范围（0～1000），包含题干、选项与图形。</p><div class="hw-crop-fields"><label>左<input id="hw-crop-left" type="number" min="0" max="999"></label><label>上<input id="hw-crop-top" type="number" min="0" max="999"></label><label>右<input id="hw-crop-right" type="number" min="1" max="1000"></label><label>下<input id="hw-crop-bottom" type="number" min="1" max="1000"></label><button id="hw-crop-apply" class="hw-secondary">应用到本题</button></div></div>');
  $('hw-scope').textContent='清单、答案与来源照片保存在这台服务的学习档案中。同一家庭可用手机或电脑继续。';
  $('hw-photo-panel').querySelector(':scope > .hw-help').textContent='照片保存在本机服务中。识别后逐页加入清单，对照原图校正数字、题号与共享条件；复杂图形和手写内容可能需要手动补充。';
  $('hw-pick-photo').insertAdjacentHTML('afterend','<button id="hw-camera-button" class="hw-secondary">拍摄照片</button><input id="hw-camera" type="file" accept="image/jpeg,image/png" capture="environment" hidden>');
  function message(text){$('hw-message').textContent=text;}
  function cache(){
    try {localStorage.setItem(key,JSON.stringify(state));storageError='';return true;}
    catch {storageError='浏览器存储不可用或空间不足。本次修改仅在当前页面保留，请勿关闭页面。';message(storageError);return false;}
  }
  function save(){
    if(!state.demo){state.dirty=true;change++;clearTimeout(syncTimer);if(ready&&!conflict){syncStatus('修改已保留，等待保存…');syncTimer=setTimeout(()=>flush(),450);}}
    return cache();
  }
  function syncStatus(text){$('hw-sync-status').textContent=text;$('hw-save-copy').hidden=!conflict;}
  async function flush(){
    clearTimeout(syncTimer);
    if(syncing){const ok=await syncing;if(ok&&state.dirty&&!conflict)return flush();return ok&&!conflict;}
    if(!ready||conflict)return false;
    if(state.demo||!state.dirty)return true;
    const target=state,stamp=change;
    syncing=(async()=>{
      syncStatus('正在保存…');
      try{
        const data=await request('/api/homework/assignments/'+encodeURIComponent(target.id),'PUT',target);
        if(state===target){state.revision=data.revision;state.dirty=change!==stamp;for(const item of state.items){const saved=data.items.find(row=>row.id===item.id);if(!item.source_regions?.length&&saved?.source_regions?.length)item.source_regions=saved.source_regions;}cache();syncStatus(state.dirty?'还有修改待保存':'已保存，可换设备继续');}
        return true;
      }catch(error){
        if(error.status===409)conflict=true;
        syncStatus(conflict?'另一台设备有更新；本机修改已保留':error.message+' · 本机草稿已保留');
        return false;
      }finally{syncing=null;}
    })();
    const success=await syncing;
    if(success&&state.dirty&&!conflict)return flush();
    return success;
  }
  async function library(){
    const rows=await request('/api/homework/assignments');
    $('hw-assignment-select').innerHTML='<option value="">选择已保存的作业</option>'+rows.map(row=>`<option value="${safe(row.id)}">${safe(row.date)} · ${safe(row.title)} · ${row.draft?'草稿':row.done+'/'+row.total+' 题通过'}</option>`).join('');
    $('hw-assignment-select').value=state.id;
    return rows;
  }
  function useAssignment(data){
    state={...fresh(),...data,version:1,demo:false,dirty:false};change++;conflict=false;
    photos=state.sources||[];cache();render();renderPhotos();renderDemoExit();setMode(mode);$('hw-assignment-select').value=state.id;
    const url=new URL(location.href);url.searchParams.set('assignment',state.id);history.replaceState(null,'',url);
    syncStatus('已载入最新进度');
  }
  function busyAssignment(){return batching||pending.size>0||photoBusy||uploading||visualBusy.size>0;}
  $('hw-assignment-select').onchange=async()=>{
    const id=$('hw-assignment-select').value;if(!id||busyAssignment()){message('请等待当前处理完成，再切换作业。');$('hw-assignment-select').value=state.id;return;}
    if(!await flush()){$('hw-assignment-select').value=state.id;return;}
    try{useAssignment(await request('/api/homework/assignments/'+encodeURIComponent(id)));await library();}catch(error){message(error.message);}
  };
  $('hw-new-assignment').onclick=async()=>{
    if(busyAssignment()){message('请等待当前处理完成，再新建作业。');return;}
    if(!state.demo&&!await flush())return;
    state=fresh();photos=[];edits=[];importedSources=[];conflict=false;save();renderPhotos();setMode('parent');renderDemoExit();
    const url=new URL(location.href);url.searchParams.delete('assignment');history.replaceState(null,'',url);
    message('新建一份作业，之前的清单可以在“我的作业”中继续打开。');
    if(await flush())await library();
  };
  $('hw-reload').onclick=async()=>{
    if(busyAssignment()){message('请等待当前处理完成后载入。');return;}
    try{
      if(conflict)localStorage.setItem('mathguide.homework.backup.'+state.id,JSON.stringify(state));
      else if(!await flush())return;
      const rows=await library(),id=rows.some(row=>row.id===state.id)?state.id:rows[0]?.id;
      if(id)useAssignment(await request('/api/homework/assignments/'+encodeURIComponent(id)));
      await library();
    }catch(error){message(error.message);}
  };
  $('hw-save-copy').onclick=async()=>{
    if(busyAssignment())return;
    state.id=uid();state.revision=0;state.title=(state.title+'（本机副本）').slice(0,60);
    const ids=new Map();for(const item of [...state.items,...(state.draft?.items||[])]){if(!ids.has(item.id))ids.set(item.id,uid());item.id=ids.get(item.id);item.analysis=null;item.review_id=null;item.status='todo';}
    state.active=state.items[0]?.id||null;conflict=false;save();render();if(await flush())await library();
  };
  function current(){return state.items.find(item=>item.id===state.active)||state.items[0];}
  function imageRefs(item){return item?.source_regions?.length?item.source_regions:(item?.source_ids||[]).slice(0,4).map(id=>({source_id:id,box:[0,0,1000,1000]}));}
  function cropUrl(region){return '/api/homework/sources/'+encodeURIComponent(region.source_id)+'/image?box='+region.box.join(',');}
  function renderVisual(item){
    $('hw-visual-tutor').hidden=!imageRefs(item).length;
    const messages=visualMessages.get(item?.id)||[];
    $('hw-visual-messages').innerHTML=messages.length?messages.map(row=>`<p class="hw-visual-message ${row.role==='user'?'student':'teacher'}"><b>${row.role==='user'?'我':'老师'}</b><span>${safe(row.content)}</span></p>`).join(''):'<p class="hw-help">点击“请 AI 老师帮忙”，从观察这道题的图形开始。</p>';
    $('hw-visual-input').value=visualDrafts.get(item?.id)||'';
    const working=!!item&&visualBusy.has(item.id);
    $('hw-visual-send').disabled=working||state.demo;
    $('hw-visual-input').disabled=working;
    $('hw-visual-status').textContent=working?'老师正在看本题配图…':'';
  }
  async function loadVisual(item){
    if(!imageRefs(item).length||!ready)return;
    const version=++visualRequest;
    try{const data=await request('/api/homework/items/'+encodeURIComponent(item.id)+'/visual-tutor');if(version!==visualRequest||current()?.id!==item.id)return;visualMessages.set(item.id,data.messages);renderVisual(item);}
    catch(error){if(current()?.id===item.id)$('hw-visual-status').textContent=error.message;}
  }
  async function sendVisual(message){
    const item=current();if(!item||visualBusy.has(item.id)||state.demo)return;
    message=(message||visualDrafts.get(item.id)||'').trim();if(!message){$('hw-visual-input').focus();return;}
    if(!await flush())return;
    visualBusy.add(item.id);visualDrafts.set(item.id,message);render();
    try{
      const data=await request('/api/homework/items/'+encodeURIComponent(item.id)+'/visual-tutor','POST',{message,request_id:uid()});
      const rows=visualMessages.get(item.id)||[];rows.push({role:'user',content:message},{role:'assistant',content:data.reply});visualMessages.set(item.id,rows);visualDrafts.delete(item.id);
    }catch(error){message=error.message;}
    finally{visualBusy.delete(item.id);render();if(current()?.id===item.id&&visualDrafts.has(item.id))$('hw-visual-status').textContent=message;}
  }
  $('hw-visual-input').oninput=()=>{if(current())visualDrafts.set(current().id,$('hw-visual-input').value);};
  $('hw-visual-send').onclick=()=>sendVisual();
  async function request(url, method='GET', body){
    const response=await fetch(url,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:response.status===404?'作业服务尚未加载，请重启服务后重试。':'请求未完成，请检查内容后重试。');error.status=response.status;throw error;}
    return data;
  }
  function renderReview(item){
    const working=!!item&&pending.has(item.id), analysis=item?.analysis;
    $('hw-save-answer').disabled=working||batching||state.demo||!ready;
    $('hw-save-answer').textContent=working?'正在解题并核对…':analysis?'重新核对本题':'提交本题 · AI 分析';
    $('hw-answer').disabled=working||batching;
    $('hw-skip').disabled=working||batching;
    $('hw-analysis').innerHTML=working?'<p role="status">老师正在检查你的答案和解题过程，请稍等…</p>':analysis?`<strong class="hw-verdict ${safe(analysis.verdict)}">${verdicts[analysis.verdict]||'分析结果'}</strong>${analysis.verification==='verified_geometry'?'<small class="hw-checked-label">已逐项核对翻折关系</small>':''}<p>${safe(analysis.feedback)}</p><details open><summary>看看思路</summary><p>${safe(analysis.explanation)}</p></details>`:'<p>提交答案后，这里会显示 AI 的分析。你也可以先记下自己的思考。</p>';
    $('hw-reflection-label').textContent=analysis?.reflection_prompt||'这道题，我学到了什么？';
    $('hw-reflection').value=item?.reflection||'';
    $('hw-in-notes').checked=!!item?.in_notes;
    $('hw-in-mistakes').checked=!!item?.in_mistakes;
    $('hw-save-reflection').disabled=working||state.demo||!!item?.savingReflection;
  }
  async function submitOne(item){
    if(!item||pending.has(item.id)||state.demo||!ready)return false;
    if(!item.answer?.trim()){message('先写下你的答案或思路吧。');$('hw-answer').focus();return false;}
    if(!await flush()){message('请先保存清单或处理多端更新，再提交分析。');return false;}
    const question=item.text,answer=item.answer;
    pending.add(item.id);render();
    try{
      const record=await request('/api/homework/reviews','POST',{item_id:item.id,title:state.title,assignment_date:state.date,question,answer,recheck:!!item.analysis});
      if(state.items.includes(item)&&item.text===question&&item.answer===answer){
        item.analysis=record.analysis;item.review_id=record.id;
        item.status={correct:'done',incorrect:'revision',uncertain:'uncertain'}[record.analysis.verdict];
        // Recover previously saved choices after an identical retry; preserve a new local reflection draft.
        if(!item.reflectionDirty){item.reflection=record.reflection;item.in_notes=record.in_notes;item.in_mistakes=record.in_mistakes;}
        save();
      }
      message(storageError||'分析已保存到学习档案。可以订正、写下反思，并选择是否收录。');
      return true;
    }catch(error){message(error.message);return false;}
    finally{pending.delete(item.id);render();}
  }
  $('hw-submit-all').onclick=async()=>{
    if(batching||pending.size||state.demo)return;
    const todo=state.items.filter(item=>item.answer?.trim()&&(!item.analysis||item.analysis.needs_reanalysis));
    if(!todo.length){message('没有待分析的答案。请先作答，或修改需要订正的答案后重新提交。');return;}
    batching=true;render();let successful=0;
    try{for(const item of todo){message(`正在分析第 ${state.items.indexOf(item)+1} 题…`);if(await submitOne(item))successful++;}}
    finally{batching=false;render();message(`本次已分析 ${successful}/${todo.length} 题。${successful<todo.length?'未完成分析的答案已保留，可重试。':''}未作答的题目仍在清单中。`);}
  };
  function reflectionDraft(){const item=current();if(!item)return;item.reflection=$('hw-reflection').value;item.in_notes=$('hw-in-notes').checked;item.in_mistakes=$('hw-in-mistakes').checked;item.reflectionDirty=true;save();}
  $('hw-reflection').oninput=reflectionDraft;
  $('hw-in-notes').onchange=$('hw-in-mistakes').onchange=reflectionDraft;
  $('hw-save-reflection').onclick=async()=>{
    const item=current();if(!item||item.savingReflection)return;reflectionDraft();
    if(!item.review_id){message(storageError||'反思草稿已保留。请先提交本题给 AI 分析，再保存到学习档案。');return;}
    const id=item.review_id, payload={reflection:item.reflection,in_notes:!!item.in_notes,in_mistakes:!!item.in_mistakes};
    item.savingReflection=true;renderReview(item);
    try{
      await request('/api/homework/reviews/'+encodeURIComponent(id),'PATCH',payload);
      if(item.review_id===id&&item.reflection===payload.reflection&&!!item.in_notes===payload.in_notes&&!!item.in_mistakes===payload.in_mistakes)item.reflectionDirty=false;
      message('反思和收录选择已保存，可在“学习档案”查看。');
    }catch(error){message(error.message);}
    finally{delete item.savingReflection;save();renderReview(current());}
  };
  function render(){
    const done=state.items.filter(item=>item.status==='done').length;
    $('hw-date-label').textContent=`${state.date} · ${state.demo?'示例作业':'本机作业'}`;
    $('hw-subtitle').textContent=state.items.length?`${state.title} · ${state.demo?'示例内容，仅供体验':'按自己的节奏，一次完成一小步。'}`:'把作业变成小清单，和星芽一起慢慢完成。';
    $('hw-total').textContent=state.items.length;$('hw-done').textContent=done;$('hw-remaining').textContent=state.items.length-done;
    $('hw-progress').max=state.items.length||1;$('hw-progress').value=done;
    $('hw-progress-text').textContent=state.items.length?`已完成 ${done} / ${state.items.length} 题`:'等待今天的第一道题';
    $('hw-empty').hidden=!!state.items.length;$('hw-study').hidden=!state.items.length;
    $('hw-count').textContent=`${state.items.length} 道题`;
    const item=current();
    $('hw-list').innerHTML=state.items.map((row,index)=>`<button class="hw-item" data-id="${safe(row.id)}" data-status="${row.status}" aria-current="${row.id===item?.id}"><span class="hw-item-number">${row.status==='done'?'✓':String(index+1).padStart(2,'0')}</span><span class="hw-item-text"><strong>${safe(row.text)}</strong><small>${labels[row.status]}</small></span></button>`).join('');
    if(item){
      $('hw-question-number').textContent=`第 ${state.items.indexOf(item)+1} 题 · 认真想一想`;
      $('hw-question').textContent=item.text;$('hw-question-status').textContent=labels[item.status];
      $('hw-answer').value=item.answer||'';
      $('hw-answer-note').textContent=item.analysis?'本次作答已分析；修改答案后可重新提交。':'草稿自动保留；提交后由 AI 分析。';
      $('hw-next').disabled=state.items.length<2;
      $('hw-tutor').disabled=state.demo;
      $('hw-teacher-copy').textContent=state.demo?'这是界面示例，可以试着写答案、跳题和切换清单。真实作业发布后，可转到 AI 老师辅导。':'先试着自己想一想。需要帮助时，可以把这道题带到 AI 老师那里。';
    }
    $('hw-parent-summary').hidden=!state.items.length;
    $('hw-parent-summary').textContent=`${state.demo?'示例清单':'已发布'} ${state.items.length} 道题 · AI 分析通过 ${done} 道 · 待订正 ${state.items.filter(row=>row.status==='revision').length} 道`;
    renderReview(item);
    $('hw-submit-all').hidden=!state.items.length;
    $('hw-submit-all').disabled=batching||pending.size>0||state.demo||!ready;
    $('hw-submit-all').textContent=batching?'正在逐题分析…':'提交作业 · AI 分析';
    $('hw-source-links').innerHTML=(item?.source_ids||[]).map((id,index)=>`<button class="hw-link" data-source="${safe(id)}">▧ 查看本题原图 ${index+1}</button>`).join('');
    $('hw-question-images').innerHTML=imageRefs(item).map((region,index)=>`<button class="hw-question-image" data-zoom-region="${index}" aria-label="放大本题配图${index+1}"><img src="${safe(cropUrl(region))}" alt="本题题干、选项和配图 ${index+1}"><span>本题截图 · 点击放大</span></button>`).join('');
    renderVisual(item);
    const visualKey=item?JSON.stringify([item.id,item.text,imageRefs(item)]):'';
    if(ready&&mode==='student'&&visualKey!==visualLoadedKey){visualLoadedKey=visualKey;loadVisual(item);}
    $('hw-new-assignment').disabled=busyAssignment()||!ready;
    $('hw-assignment-select').disabled=busyAssignment()||!ready;
  }
  function saveDraft(){state.draft={title:$('hw-title').value,date:$('hw-date').value,batch:$('hw-batch').value,items:edits,imported_source_ids:importedSources};save();}
  function editor(){
    $('hw-draft-count').textContent=`${edits.length} 道题`;
    $('hw-publish').disabled=!edits.length||busyAssignment()||!ready;
    $('hw-editor').innerHTML=edits.length?edits.map((row,index)=>`<article class="hw-edit-row" data-index="${index}"><header><b>第 ${index+1} 题</b>${(row.source_ids||[]).map(id=>`<button data-source="${safe(id)}" aria-label="查看第${index+1}题原图">原图</button>`).join('')}<button data-action="up" aria-label="第${index+1}题上移" ${index===0?'disabled':''}>↑</button><button data-action="down" aria-label="第${index+1}题下移" ${index===edits.length-1?'disabled':''}>↓</button><button data-action="remove" aria-label="删除第${index+1}题">删除</button></header><textarea aria-label="第${index+1}题题干" maxlength="2000" rows="2">${safe(row.text)}</textarea>${row.visual_suggestion?`<details class="hw-reading-suggestion" open><summary>看图转录建议 · 请校对</summary><p>${safe(row.visual_suggestion)}</p><button data-adopt-reading="${index}" class="hw-secondary">采用这段文字</button></details>`:''}${imageRefs(row).map((region,figure)=>`<div class="hw-editor-figure"><img src="${safe(cropUrl(region))}" alt="第${index+1}题配图${figure+1}"><button data-read-region="${index}" class="hw-link">看图转录题干</button><small>图形选项与阴影以配图为准，可点“原图”调整范围。</small></div>`).join('')}</article>`).join(''):'<div class="hw-empty"><span class="hw-empty-symbol">☷</span><p>整理后的题目会出现在这里。<br>也可以手动添加第一道题。</p></div>';
  }
  function setMode(next){
    mode=next;$('hw-student').hidden=mode!=='student';$('hw-parent').hidden=mode!=='parent';
    $('hw-student-mode').setAttribute('aria-pressed',String(mode==='student'));$('hw-parent-mode').setAttribute('aria-pressed',String(mode==='parent'));
    if(mode==='parent'){
      const draft=state.draft;
      edits=(draft?.items||state.items).map(row=>({...row}));
      importedSources=draft?.imported_source_ids||[...new Set(state.items.flatMap(row=>row.source_ids||[]))];
      $('hw-title').value=draft?.title??state.title;$('hw-date').value=draft?.date??state.date;$('hw-batch').value=draft?.batch||'';
      editor();
    }
    message(storageError);render();
  }
  nav.onclick=()=>window.MathGuideWorkspace.show('homework');
  $('hw-student-mode').onclick=()=>setMode('student');$('hw-parent-mode').onclick=$('hw-empty-create').onclick=()=>setMode('parent');
  $('hw-list').onclick=event=>{const button=event.target.closest('[data-id]');if(!button)return;state.active=button.dataset.id;save();render();message(storageError);};
  $('hw-answer').oninput=()=>{const item=current();if(!item)return;item.answer=$('hw-answer').value;item.status='todo';item.analysis=null;item.review_id=null;const saved=save();render();$('hw-question-status').textContent='答案编辑中';$('hw-answer-note').textContent=saved?'草稿已保留，写好后点击“提交本题 · AI 分析”。':'草稿尚未保存到浏览器，请勿关闭页面。';};
  $('hw-save-answer').onclick=()=>submitOne(current());
  $('hw-skip').onclick=()=>{const item=current();if(!item)return;if(item.analysis){message('这道题已经分析过，可以写下反思或修改答案后重试。');return;}item.status='skipped';save();render();message(storageError||'先把这道题放一放，准备好时随时回来。');};
  $('hw-next').onclick=()=>{const index=state.items.indexOf(current());state.active=state.items[(index+1)%state.items.length].id;save();render();message(storageError);};
  $('hw-tutor').onclick=async()=>{
    if(!await flush())return;
    const item=current();
    if(imageRefs(item).length){$('hw-visual-tutor').scrollIntoView({block:'center'});await loadVisual(item);if(!(visualMessages.get(item.id)||[]).length)await sendVisual('请先带我读懂这道题的图，不要直接给答案。');else $('hw-visual-input').focus();return;}
    try{
      // Another device may already have started a session for this question.
      const latest=await request('/api/homework/assignments/'+encodeURIComponent(state.id));
      item.tutor_session_id=latest.items.find(row=>row.id===item.id)?.tutor_session_id||item.tutor_session_id;
      if(!await window.MathGuideTutor?.openHomework(item)){message('老师正在回复，或题目辅导中还有一道单独的题。请先完成当前回复或结束单题辅导。');return;}
      showAlert(item.tutor_session_id?'已接上这道题的辅导。':'题目已带入，点击发送即可开始。');
    }catch(error){message(error.message);}
  };
  window.addEventListener('mathguide:homework-session',event=>{const item=state.items.find(row=>row.id===event.detail.itemId);if(item){item.tutor_session_id=event.detail.sessionId;cache();}});
  window.MathGuideHomework={async returnToItem(itemId){
    if(!state.items.some(row=>row.id===itemId)){
      if(busyAssignment()||!await flush())return;
      try{useAssignment(await request('/api/homework/items/'+encodeURIComponent(itemId)));await library();}
      catch(error){showAlert(error.message);return;}
    }
    state.active=itemId;save();setMode('student');window.MathGuideWorkspace.show('homework');$('hw-answer').focus();
  }};
  $('hw-split').onclick=()=>{
    const text=$('hw-batch').value.trim();if(!text){message('先输入需要整理的题目。');return;}
    const numbered=/^\s*(?:第\s*\d+\s*题[：:.、]?|\d+[、．.](?!\d)|\d+[)）])\s*/;
    const lines=text.split(/\r?\n/), hasNumbers=lines.some(line=>numbered.test(line));let parts=[];
    if(hasNumbers){for(const line of lines){if(numbered.test(line))parts.push(line.replace(numbered,''));else if(line.trim()){if(!parts.length)parts.push(line.trim());else parts[parts.length-1]+='\n'+line.trim();}}}
    else parts=text.split(/\n\s*\n/.test(text)?/\n\s*\n/:/\n/);
    parts=parts.map(part=>part.trim()).filter(Boolean);
    if(edits.length+parts.length>100){message('一份清单最多支持 100 道题，请分批安排。');return;}
    if(parts.some(part=>part.length>2000)){message('有题目超过 2000 字，请检查分题或手动拆分。');return;}
    edits.push(...parts.map(text=>({id:uid(),text,status:'todo',answer:''})));$('hw-batch').value='';saveDraft();editor();message(storageError||`已整理 ${parts.length} 道题。请核对题干，特别是共享条件和多行内容。`);
  };
  $('hw-editor').oninput=event=>{if(event.target.matches('textarea')){edits[Number(event.target.closest('[data-index]').dataset.index)].text=event.target.value;saveDraft();}};
  $('hw-editor').addEventListener('click',async event=>{
    const button=event.target.closest('[data-read-region]');if(!button)return;
    const item=edits[Number(button.dataset.readRegion)],region=imageRefs(item)[0],text=item.text;
    if(!region)return;button.disabled=true;button.textContent='正在看图转录…';
    try{
      const result=await request('/api/homework/vision/read','POST',region);
      if(!edits.includes(item)||item.text!==text){message('题目已被修改，本次转录没有覆盖你的编辑。');return;}
      item.visual_suggestion=result.text;item.visual_summary=result.visual_summary;saveDraft();editor();
      message(result.needs_review?'转录建议已生成，部分细节需要校对；原题文字已保留。':'已生成转录建议，请对照配图后点击采用。');
    }catch(error){message(error.message);button.disabled=false;button.textContent='看图转录题干';}
  });
  $('hw-editor').onclick=event=>{const button=event.target.closest('[data-action]');if(!button)return;const index=Number(button.closest('[data-index]').dataset.index), action=button.dataset.action;if(action==='remove')edits.splice(index,1);else{const other=index+(action==='up'?-1:1);if(other<0||other>=edits.length)return;[edits[index],edits[other]]=[edits[other],edits[index]];}saveDraft();editor();};
  $('hw-editor').addEventListener('click',event=>{const button=event.target.closest('[data-adopt-reading]');if(!button)return;const item=edits[Number(button.dataset.adoptReading)];item.text=item.visual_suggestion;item.visual_suggestion='';saveDraft();editor();});
  $('hw-add').onclick=()=>{if(edits.length>=100){message('一份清单最多支持 100 道题。');return;}edits.push({id:uid(),text:'',status:'todo',answer:''});saveDraft();editor();$('hw-editor').lastElementChild.querySelector('textarea').focus();};
  for(const id of ['hw-title','hw-date','hw-batch'])$(id).oninput=saveDraft;
  $('hw-publish').onclick=async()=>{
    if(busyAssignment()||!ready){message('请等待当前处理完成后再更新作业清单。');return;}
    if(!edits.length||edits.some(row=>!row.text.trim())){message('还有空白题目，请填写或删除后发布。');return;}
    if(!$('hw-date').value||!$('hw-date').checkValidity()){message('请选择有效的作业日期。');$('hw-date').focus();return;}
    state.items=edits.map(row=>{const old=state.items.find(item=>item.id===row.id);return {...row,text:row.text.trim(),...(old?.text===row.text.trim()&&JSON.stringify(imageRefs(old))===JSON.stringify(imageRefs(row))?old:{status:'todo',answer:old?.text===row.text.trim()?(old.answer||''):'',analysis:null,review_id:null,reflection:'',in_notes:false,in_mistakes:false})};});
    state.title=$('hw-title').value.trim()||'数学作业';state.date=$('hw-date').value;state.active=state.items[0].id;state.draft=null;
    save();setMode('student');if(state.demo){message('示例清单已更新。');return;}
    if(await flush()){await library();message('作业已发布并保存，从第一道题开始吧！');}
  };
  $('hw-open-records').onclick=async()=>{await window.MathGuideLearning.open();document.getElementById('homework-learning-section').scrollIntoView({block:'start'});};
  function source(photo){$('hw-photo-panel').hidden=!photo;$('hw-photo-tab').setAttribute('aria-pressed',String(photo));$('hw-text-tab').setAttribute('aria-pressed',String(!photo));}
  $('hw-text-tab').onclick=()=>source(false);$('hw-photo-tab').onclick=()=>source(true);$('hw-pick-photo').onclick=()=>$('hw-photos').click();
  function renderPhotos(){
    state.sources=photos;
    $('hw-photo-grid').innerHTML=photos.map((photo,index)=>`<figure class="hw-photo"><button class="hw-photo-open" data-source="${safe(photo.id)}" aria-label="查看作业照片${index+1}"><img src="${safe(photo.url)}" alt="作业照片 ${index+1}"></button><figcaption>${safe(photo.name)}</figcaption><p class="hw-help">${photo.result?`已识别 ${photo.result.questions.length} 题`:safe(photo.error||'等待识别')}</p><button class="hw-link" data-recognize="${safe(photo.id)}" ${photoBusy?'disabled':''}>${photo.result?.version===2?'识别完成':photo.result?'升级识别 · 保留配图':'识别 / 重试'}</button>${photo.result?`<button class="hw-link" data-import="${safe(photo.id)}">加入待校对清单</button>`:''}<button class="hw-link" data-photo="${index}" ${photoBusy?'disabled':''}>移除照片</button></figure>`).join('');
    $('hw-recognize-all').hidden=!photos.length;$('hw-recognize-all').disabled=photoBusy||uploading;
    $('hw-recognize-all').textContent=photoBusy?'正在按页识别…':'识别全部照片';
    $('hw-pick-photo').disabled=photoBusy||uploading||!ready||state.demo;
    $('hw-camera-button').disabled=$('hw-pick-photo').disabled;
  }
  $('hw-photos').onchange=async event=>{
    const files=Array.from(event.target.files||[]);event.target.value='';
    if(uploading||photoBusy||state.demo)return;
    if(files.length+photos.length>10){message('一份作业最多保存 10 张照片。');return;}
    if(files.some(file=>file.size>10*1024*1024||!['image/jpeg','image/png','image/bmp','image/x-ms-bmp'].includes(file.type))){message('请选择每张不超过 10 MB 的 JPG、PNG 或 BMP 图片。');return;}
    uploading=true;renderPhotos();render();const failures=[];
    try{
      for(const file of files){
        message('正在保存照片：'+file.name);const form=new FormData();form.append('image',file);
        try{
          const response=await fetch('/api/homework/sources',{method:'POST',body:form}),data=await response.json();
          if(!response.ok)throw new Error(data.detail||'上传失败');
          if(!photos.some(photo=>photo.id===data.id)){photos.push(data);state.source_ids=photos.map(photo=>photo.id);saveDraft();renderPhotos();}
        }catch(error){failures.push(file.name+'：'+error.message);}
      }
      if(!failures.length)message('照片已保存。点击“识别全部照片”，然后逐页加入清单并校对。');
      else message('其他照片已保留。未完成：'+failures.join('；'));
    }finally{uploading=false;renderPhotos();editor();render();}
  };
  $('hw-camera-button').onclick=()=>$('hw-camera').click();
  $('hw-camera').onchange=event=>$('hw-photos').onchange(event);
  async function recognizePhoto(photo){
    if(photo.result?.version===2)return;
    try{Object.assign(photo,await request('/api/homework/sources/'+encodeURIComponent(photo.id)+'/recognize','POST'));}
    catch(error){photo.error=error.message;}
    save();renderPhotos();
  }
  $('hw-recognize-all').onclick=async()=>{
    if(photoBusy||uploading)return;photoBusy=true;renderPhotos();render();editor();
    try{for(const photo of photos){message(`正在识别第 ${photos.indexOf(photo)+1}/${photos.length} 张照片…`);await recognizePhoto(photo);}}
    finally{photoBusy=false;renderPhotos();render();editor();message('识别处理结束。请将成功页面加入清单；失败页面可单独重试。');}
  };
  $('hw-photo-grid').onclick=async event=>{
    const button=event.target.closest('button');if(!button||photoBusy||uploading)return;
    if(button.dataset.recognize){const photo=photos.find(row=>row.id===button.dataset.recognize);photoBusy=true;renderPhotos();try{await recognizePhoto(photo);}finally{photoBusy=false;renderPhotos();}return;}
    if(button.dataset.import){
      const photo=photos.find(row=>row.id===button.dataset.import);
      if(importedSources.includes(photo.id)){message('这张照片已经加入过清单，请直接编辑已导入的题目。');return;}
      const questions=photo.result.questions;
      if(edits.length+questions.length>100||questions.some(row=>row.text.length>2000)){message('识别内容超过清单限制，请对照原图手动拆分录入。');return;}
      edits.push(...questions.map(row=>({id:uid(),text:row.text,status:'todo',answer:'',source_ids:[photo.id],source_regions:row.source_regions||[]})));
      importedSources.push(photo.id);saveDraft();editor();message(photo.result.warning+(questions.some(row=>row.low_confidence)?' 部分文字清晰度不足，请重点检查。':''));return;
    }
    if(button.dataset.photo!==undefined){
      const photo=photos[Number(button.dataset.photo)];
      if([...state.items,...edits].some(item=>item.source_ids?.includes(photo.id))){message('这张照片关联着题目，请先移除关联题目再移除照片。');return;}
      photos.splice(Number(button.dataset.photo),1);state.source_ids=photos.map(photo=>photo.id);saveDraft();renderPhotos();
    }
  };
  root.addEventListener('click',event=>{
    const button=event.target.closest('[data-source]');if(button){const row=button.closest('[data-index]');showSource(button.dataset.source,row?Number(row.dataset.index):null);}
    const zoom=event.target.closest('[data-zoom-region]');if(zoom){cropTarget=null;$('hw-crop-controls').hidden=true;const region=imageRefs(current())[Number(zoom.dataset.zoomRegion)];$('hw-source-image').innerHTML=`<img class="hw-zoomed-question" src="${safe(cropUrl(region))}" alt="放大的本题配图">`;$('hw-source-hint').textContent='本题截图包含原始图形与选项。';$('hw-source-dialog').showModal();}
  });
  function showSource(id,editIndex=null){
    const photo=photos.find(row=>row.id===id);if(!photo)return;
    const polygons=(photo.result?.lines||[]).map(line=>`<polygon points="${line.box.map(point=>point.join(',')).join(' ')}" class="${line.confidence<.85?'low':''}"/>`).join('');
    $('hw-source-image').innerHTML=`<div class="hw-source-stage"><img src="${safe(photo.url)}" alt="${safe(photo.name)}"><svg viewBox="0 0 ${photo.width} ${photo.height}" aria-hidden="true">${polygons}</svg></div>`;
    $('hw-source-hint').textContent='紫框是识别文字，橙框需要重点核对。'+(photo.result?.warning||'可先识别照片，再对照文字区域校对。');
    cropTarget=editIndex===null?null:{source_id:id,index:editIndex};$('hw-crop-controls').hidden=!cropTarget;
    if(cropTarget){const region=imageRefs(edits[editIndex]).find(row=>row.source_id===id)||{box:[0,0,1000,1000]};['left','top','right','bottom'].forEach((key,index)=>$('hw-crop-'+key).value=region.box[index]);}
    updateCropPreview();
    $('hw-source-dialog').showModal();
  }
  function updateCropPreview(){
    if(!cropTarget)return;const photo=photos.find(row=>row.id===cropTarget.source_id),svg=$('hw-source-image').querySelector('svg');if(!photo||!svg)return;
    let rectangle=svg.querySelector('.hw-crop-rect');if(!rectangle){rectangle=document.createElementNS('http://www.w3.org/2000/svg','rect');rectangle.setAttribute('class','hw-crop-rect');svg.append(rectangle);}
    const box=['left','top','right','bottom'].map(key=>Number($('hw-crop-'+key).value));
    Object.entries({x:box[0]*photo.width/1000,y:box[1]*photo.height/1000,width:Math.max(0,box[2]-box[0])*photo.width/1000,height:Math.max(0,box[3]-box[1])*photo.height/1000}).forEach(([key,value])=>rectangle.setAttribute(key,value));
  }
  for(const key of ['left','top','right','bottom'])$('hw-crop-'+key).oninput=updateCropPreview;
  $('hw-crop-apply').onclick=()=>{
    if(!cropTarget)return;const box=['left','top','right','bottom'].map(key=>Number($('hw-crop-'+key).value));
    if(!box.every(Number.isInteger)||box[0]<0||box[1]<0||box[2]>1000||box[3]>1000||box[0]>=box[2]||box[1]>=box[3]){message('配图范围无效，请检查上下左右边界。');return;}
    const item=edits[cropTarget.index];item.source_regions=imageRefs(item).filter(region=>region.source_id!==cropTarget.source_id);item.source_regions.push({source_id:cropTarget.source_id,box});
    item.analysis=null;item.review_id=null;saveDraft();editor();$('hw-source-dialog').close();message('已调整本题配图范围，发布后会用于看图分析。');
  };
  $('hw-source-close').onclick=()=>$('hw-source-dialog').close();
  $('hw-demo').onclick=()=>{
    if(state.items.length||state.draft){message('已有作业草稿，请先在家长视角检查，或新建作业后体验示例。');return;}
    state={...fresh(),demo:true,title:'星芽的数学练习 · 示例',items:['计算：36 ÷ 6 = ?','一个长方形长 8 厘米，宽 5 厘米，它的面积是多少平方厘米？','24 颗糖平均分给 6 个小朋友，每个小朋友分到几颗？','计算：125 + 276 = ?','一本故事书有 80 页，小明读了 35 页，还剩多少页？'].map(text=>({id:uid(),text,status:'todo',answer:''}))};
    state.active=state.items[0].id;save();render();message('正在体验示例，不会写入学习档案。点击“退出示例”后可录入真实作业。');
    renderDemoExit();
  };
  function renderDemoExit(){
    document.getElementById('hw-exit-demo')?.remove();if(!state.demo)return;
    const button=document.createElement('button');button.id='hw-exit-demo';button.className='hw-link';button.textContent='退出示例';
    button.onclick=()=>{state=fresh();photos=[];save();setMode('student');renderPhotos();renderDemoExit();};$('hw-scope').append(button);
  }
  window.addEventListener('storage',event=>{if(event.key===key)message('另一个标签页修改了作业。请刷新页面以读取最新清单。');});
  const archive=document.createElement('section');archive.id='homework-learning-section';archive.className='learning-section hw-archive';
  archive.innerHTML='<div class="learning-section-head"><div><p class="section-kicker">每一道题，留下自己的思考</p><h3>作业分析与反思</h3><p>查看每次提交的答案、AI 反馈和孩子的反思。正确与否以 AI 分析为参考。</p></div><button id="hw-record-refresh" class="learning-text-button">刷新记录</button></div><div class="hw-record-tabs" aria-label="作业记录分类"><button data-collection="all" aria-pressed="true">全部作业记录</button><button data-collection="notes" aria-pressed="false">学习笔记</button><button data-collection="mistakes" aria-pressed="false">错题集</button></div><p id="hw-record-status" role="status"></p><div id="hw-record-list"></div>';
  document.querySelector('#learning-view').append(archive);
  const shortcut=document.createElement('div');shortcut.className='hw-learning-shortcut';
  shortcut.innerHTML='<span>家庭作业的答案与反思</span><button data-homework-filter="all">查看作业记录 →</button><button data-homework-filter="notes">学习笔记</button><button data-homework-filter="mistakes">错题集</button>';
  document.querySelector('#learning-load-status').after(shortcut);
  for(const button of shortcut.querySelectorAll('[data-homework-filter]'))button.onclick=()=>{
    recordFilter=button.dataset.homeworkFilter;
    for(const tab of archive.querySelectorAll('[data-collection]'))tab.setAttribute('aria-pressed',String(tab.dataset.collection===recordFilter));
    loadRecords();loadSummary();archive.scrollIntoView({block:'start'});
  };
  archive.querySelector('.hw-record-tabs').insertAdjacentHTML('beforebegin',`<section class="hw-daily"><div class="hw-card-head"><h3>每日作业汇总</h3><label>日期 <input id="hw-summary-date" type="date" value="${today}" aria-label="学习汇总日期"></label></div><div id="hw-daily-content" role="status"></div></section><div class="hw-record-date"><label for="hw-record-date">筛选作业日期</label><input id="hw-record-date" type="date"><button id="hw-record-all-dates" class="learning-text-button">全部日期</button></div>`);
  let summaryRequest=0;
  async function loadSummary(){
    const day=archive.querySelector('#hw-summary-date').value;if(!day)return;
    const version=++summaryRequest,output=archive.querySelector('#hw-daily-content');
    output.textContent='正在汇总…';
    try{
      const data=await request('/api/homework/summary?date='+day);if(version!==summaryRequest)return;
      output.innerHTML=`<div class="hw-daily-metrics">${[[data.total,'布置题目'],[data.analyzed,'已分析'],[data.passed,'分析通过'],[data.revision,'待订正'],[data.uncertain,'待补充'],[data.remaining,'待提交']].map(([value,label])=>`<div><b>${value}</b><span>${label}</span></div>`).join('')}</div><p>已保存反思 ${data.reflections} 题 · 学习笔记 ${data.notes} 题 · 错题集 ${data.mistakes} 题</p><p>${data.topics.length?'值得回顾：'+safe(data.topics.join('、')):'按自己的节奏，一次完成一小步。'}</p>${data.pending.length?`<details><summary>看看还需要继续的 ${data.pending.length} 道题</summary><ul>${data.pending.map(item=>`<li>${safe(item.text)} <small>· ${labels[item.status]}</small></li>`).join('')}</ul></details>`:''}`;
    }catch(error){if(version===summaryRequest)output.textContent=error.message;}
  }
  async function loadRecords(){
    const version=++recordRequest, status=archive.querySelector('#hw-record-status'),list=archive.querySelector('#hw-record-list');
    status.textContent='正在读取作业学习记录…';
    try{
      const day=archive.querySelector('#hw-record-date').value;
      const rows=await request('/api/homework/reviews?collection='+recordFilter+(day?'&date='+day:''));
      if(version!==recordRequest)return;
      status.textContent=`${rows.length} 条提交记录 · 订正后的再次提交会保留之前的思考过程`;
      list.innerHTML=rows.length?rows.map(row=>`<details class="hw-record" data-review-id="${safe(row.id)}"><summary><span><strong>${safe(row.question)}</strong><small>${safe(row.assignment_date)} · ${safe(row.title)} · ${safe(row.analysis.knowledge_point)}</small></span><span class="hw-verdict ${safe(row.analysis.verdict)}">${verdicts[row.analysis.verdict]||'分析结果'}</span></summary><div class="hw-record-body"><div class="hw-record-images">${(row.attachments||[]).map(image=>`<a href="${safe(image.url)}" target="_blank" rel="noopener"><img src="${safe(image.url)}" alt="这次提交时的原题配图"></a>`).join('')}</div><h4>我的作答</h4><p>${safe(row.answer)}</p><h4>AI 分析</h4><p>${safe(row.analysis.feedback)}</p><p>${safe(row.analysis.explanation)}</p><h4>我的反思</h4><p>${safe(row.reflection||'还没有保存反思。')}</p><small>${row.in_notes?'✓ 已计入学习笔记　':''}${row.in_mistakes?'✓ 已加入错题集':''}</small><div class="hw-record-editor"><label>补充或修改反思<textarea data-record-reflection maxlength="2000" rows="2">${safe(row.reflection)}</textarea></label><div class="hw-collection-options"><label><input type="checkbox" data-record-notes ${row.in_notes?'checked':''}> 计入学习笔记</label><label><input type="checkbox" data-record-mistakes ${row.in_mistakes?'checked':''}> 加入错题集</label></div><button data-save-record="${safe(row.id)}" class="learning-text-button">保存修改</button><p class="hw-record-save-status" role="status"></p></div></div></details>`).join(''):'<div class="learning-empty">'+(recordFilter==='all'?'还没有提交的作业。做完一道题，提交给 AI 分析吧。':'还没有收录的题目。分析后可由学生自行选择是否加入。')+'</div>';
    }catch(error){if(version===recordRequest){status.textContent=error.message;list.replaceChildren();}}
  }
  archive.querySelector('#hw-record-refresh').onclick=()=>{loadRecords();loadSummary();};
  archive.querySelector('#hw-record-list').onclick=async event=>{
    const button=event.target.closest('[data-save-record]');if(!button)return;
    const panel=button.closest('.hw-record'),status=panel.querySelector('.hw-record-save-status');
    const payload={reflection:panel.querySelector('[data-record-reflection]').value,in_notes:panel.querySelector('[data-record-notes]').checked,in_mistakes:panel.querySelector('[data-record-mistakes]').checked};
    button.disabled=true;status.textContent='正在保存…';
    try{
      const record=await request('/api/homework/reviews/'+encodeURIComponent(button.dataset.saveRecord),'PATCH',payload);
      const item=state.items.find(row=>row.review_id===record.id);
      if(item&&!item.reflectionDirty){Object.assign(item,payload);save();}
      status.textContent='已保存；刷新分类即可看到最新收录。';loadSummary();
    }catch(error){status.textContent=error.message;}
    finally{button.disabled=false;}
  };
  archive.querySelector('#hw-summary-date').onchange=loadSummary;
  archive.querySelector('#hw-record-date').onchange=loadRecords;
  archive.querySelector('#hw-record-all-dates').onclick=()=>{archive.querySelector('#hw-record-date').value='';loadRecords();};
  for(const button of archive.querySelectorAll('[data-collection]'))button.onclick=()=>{
    recordFilter=button.dataset.collection;for(const tab of archive.querySelectorAll('[data-collection]'))tab.setAttribute('aria-pressed',String(tab===button));loadRecords();
  };
  window.addEventListener('mathguide:workspace',event=>{if(event.detail==='learning'){loadRecords();loadSummary();}});
  document.addEventListener('DOMContentLoaded',()=>{if(new URLSearchParams(location.search).get('view')==='learning'){loadRecords();loadSummary();}});
  document.addEventListener('DOMContentLoaded',()=>{if(new URLSearchParams(location.search).get('view')==='homework')window.MathGuideWorkspace.show('homework');});
  async function initialize(){
    root.inert=true;
    try{
      const rows=await library(), selected=new URLSearchParams(location.search).get('assignment');
      const localWork=state.items.length||state.draft||state.source_ids.length;
      if(state.demo){photos=[];syncStatus('正在体验示例');}
      else if(localWork&&(state.dirty||!rows.some(row=>row.id===state.id))){
        if(state.revision===0)state.dirty=true;
        syncStatus('本机草稿等待保存');
        photos=state.sources||[];
      }else{
        const id=selected||rows.find(row=>row.id===state.id)?.id||rows.find(row=>row.date===today&&!row.draft)?.id||rows[0]?.id;
        if(id)useAssignment(await request('/api/homework/assignments/'+encodeURIComponent(id)));
        else syncStatus('准备好录入第一份作业');
      }
    }catch(error){photos=state.sources||[];syncStatus(error.message+' · 可继续使用本机草稿');}
    finally{
      ready=true;root.inert=false;render();renderPhotos();renderDemoExit();if(mode==='parent')setMode('parent');
      if(state.dirty&&!conflict)await flush();
    }
  }
  window.addEventListener('online',()=>flush());
  window.addEventListener('pagehide',()=>{if(state.dirty&&!state.demo&&!conflict)fetch('/api/homework/assignments/'+encodeURIComponent(state.id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(state),keepalive:true}).catch(()=>{});});
  render();renderDemoExit();message(storageError);initialize();
})();
