/* Saved learning evidence, rendered without inventing mastery probabilities. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const state = {rows: [], stats: [], filter: 'all', search: '', expanded: false, dialogRows: [], active: null, request: 0, dialogRequest: 0};
  const safe = value => {const el = document.createElement('span'); el.textContent = value ?? ''; return el.innerHTML;};
  async function get(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error('学习档案暂时无法读取，请稍后重试。');
    return response.json();
  }
  function statusFor(row) {
    if ((row.streak || 0) >= 3) return {label: '初步巩固', tone: 'green', kind: 'is-consolidated'};
    if ((row.weak_score || 0) >= 4) return {label: '优先复习', tone: '', kind: 'is-priority'};
    if ((row.weak_score || 0) > 0) return {label: '正在巩固', tone: 'blue', kind: ''};
    return {label: '保持练习', tone: 'blue', kind: ''};
  }
  const badge = (text, tone = '') => `<span class="learning-badge ${tone}">${safe(text)}</span>`;
  const solvedBadge = row => badge(row.understood ? '独立解出' : '讲解后复习', row.understood ? 'green' : '');
  const dateText = date => /^\d{4}-\d{2}-\d{2}$/.test(date || '') ? `${Number(date.slice(5, 7))}月${Number(date.slice(8, 10))}日` : '日期未记录';
  const studentTurns = row => (row.dialogue || []).filter(message => message.role === 'student' || message.role === 'user').length;
  const types = {'计算题': ['÷', 0], '几何应用题': ['△', 1], '百分数应用题': ['%', 2], '行程应用题': ['↗', 0], '单位换算题': ['⇄', 3], '平均数应用题': ['≋', 2]};

  function renderMetrics() {
    const solved = state.rows.filter(row => row.understood).length;
    const review = state.stats.filter(row => row.weak_score > 0).length;
    const days = new Set(state.rows.map(row => row.record_date)).size;
    const metrics = [[state.rows.length, '道', '留下思考的题目', '▤', ''], [solved, '道', '已独立解出的题目', '✓', 'green'],
                     [review, '个', '值得再练的知识点', '↗', 'amber'], [days, '天', '有学习记录的日子', '◷', 'rose']];
    $('#learning-metrics').innerHTML = metrics.map(([value, unit, label, icon, tone]) => `<article class="learning-metric"><span class="metric-icon ${tone}" aria-hidden="true">${icon}</span><div><div class="metric-value">${value}<small>${unit}</small></div><div class="metric-label">${label}</div></div></article>`).join('');
    const dates = state.rows.map(row => row.record_date).filter(Boolean).sort();
    $('#learning-range').textContent = dates.length ? `${dateText(dates[0])} — ${dateText(dates.at(-1))} · ${state.rows.length} 次辅导记录` : '从第一道题开始，积累属于你的学习足迹。';
    const consolidated = state.stats.filter(row => row.streak >= 3);
    $('#learning-highlight-text').textContent = consolidated.length ? `${consolidated.length} 个知识点，已经初步巩固。` : solved ? `你已经独立完成了 ${solved} 道题。` : '慢慢想，也是一种进步。';
    $('#learning-highlight-note').textContent = consolidated.length ? `${consolidated.slice(0, 2).map(row => row.knowledge_point).join('、')}，继续保持。` : '不用一次全会，每次弄懂一点点就很好。';
  }

  function renderStats() {
    $('#stats').innerHTML = state.stats.length ? state.stats.slice(0, 3).map(row => {
      const status = statusFor(row);
      return `<li><span class="compact-topic">${safe(row.knowledge_point)}<small>练习独立答对 ${row.independent_correct || 0}/${row.practice_total || 0} 题</small></span>${badge(status.label, status.tone)}</li>`;
    }).join('') : '<li class="muted">做完第一道题后，一起发现值得练习的地方。</li>';
    $('#learning-weaknesses').innerHTML = state.stats.length ? state.stats.slice(0, 6).map((row, index) => {
      const status = statusFor(row), streak = Math.min(3, row.streak || 0);
      const history = row.total ? `辅导中 <strong>${row.not_understood}/${row.total}</strong> 次需要讲解` : '已经开始专项练习';
      return `<article class="weakness-card ${status.kind}" data-knowledge-id="${safe(row.knowledge_id || '')}"><div class="weakness-card-head"><span class="weakness-number">FOCUS ${String(index + 1).padStart(2, '0')}</span>${badge(status.label, status.tone)}</div><h4>${safe(row.knowledge_point)}</h4><p class="weakness-description">${history}<br>练习独立答对 <strong>${row.independent_correct || 0}/${row.practice_total || 0}</strong> 题</p><div class="streak-label"><span>连续独立答对</span><b>${streak}/3 题</b></div><div class="streak-track" aria-label="连续独立答对${streak}题，目标3题">${[1, 2, 3].map(i => `<i class="${i <= streak ? 'done' : ''}"></i>`).join('')}</div><div class="weakness-card-footer"><small>${status.kind === 'is-consolidated' ? '偶尔回顾，让思路更牢' : '下一小步，从一道题开始'}</small>${row.knowledge_id ? `<button type="button" data-practice-topic="${row.knowledge_id}">练一题 <span aria-hidden="true">↗</span></button>` : '<small>可回看辅导记录</small>'}</div></article>`;
    }).join('') : '<div class="learning-empty">还没有需要复习的知识点。<br>先来完成一道题，我们会帮你记住每一次进步。</div>';
    for (const button of document.querySelectorAll('[data-practice-topic]')) button.onclick = () => openRelatedPractice(Number(button.dataset.practiceTopic));
    renderMetrics();
  }

  function renderActivity() {
    const today = new Date(), dates = [];
    for (let i = 6; i >= 0; i--) {
      const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
      const rows = state.rows.filter(row => row.record_date === key);
      dates.push({date, key, total: rows.length, solved: rows.filter(row => row.understood).length});
    }
    const max = Math.max(1, ...dates.map(day => day.total));
    $('#learning-activity-chart').innerHTML = dates.map((day, index) => {
      const height = day.total ? Math.round(day.total / max * 86) : 3;
      return `<div class="activity-day ${index === 6 ? 'today' : ''}" aria-label="${dateText(day.key)}，辅导${day.total}题，独立解出${day.solved}题"><span class="activity-count">${day.total ? day.total + ' 题' : '—'}</span><div class="activity-column" style="height:${height}px"><i class="review" style="flex:${day.total - day.solved}"></i><i class="solved" style="flex:${day.solved}"></i></div><span class="activity-label">${index === 6 ? '今天' : `${day.date.getMonth() + 1}.${String(day.date.getDate()).padStart(2, '0')}`}</span></div>`;
    }).join('');
  }

  function filteredRows() {
    return state.rows.filter(row => (state.filter === 'all' || (state.filter === 'solved' ? Boolean(row.understood) : !row.understood))
      && `${row.question_text} ${row.knowledge_point} ${row.question_type}`.toLowerCase().includes(state.search.toLowerCase()));
  }
  function renderRecords() {
    const all = filteredRows(), visible = state.expanded ? all : all.slice(0, 6);
    $('#learning-record-count').textContent = all.length;
    $('#learning-record-list').innerHTML = visible.length ? visible.map(row => {
      const [icon, tone] = types[row.question_type] || ['▤', 0];
      return `<article class="learning-record-row" data-record-id="${row.id}"><span class="record-topic-icon tone-${tone}" aria-hidden="true">${icon}</span><div class="record-row-main"><div class="record-row-top"><span>${dateText(row.record_date)}</span><span>·</span><span class="topic-type">${safe(row.question_type)}</span></div><h4>${safe(row.question_text)}</h4><div class="record-row-meta"><span>${safe(row.knowledge_point)}</span><span>${studentTurns(row)} 次学生作答</span></div></div><div class="record-row-action">${solvedBadge(row)}<button type="button" data-view-record="${row.id}" aria-label="查看学习过程：${safe(row.question_text)}">查看学习过程 <span aria-hidden="true">↗</span></button></div></article>`;
    }).join('') : '<div class="learning-empty">没有找到符合条件的记录。<br>试试其他关键词，或从第一道题开始。</div>';
    $('#learning-more').hidden = all.length <= 6;
    $('#learning-more').textContent = state.expanded ? '收起部分记录 ↑' : `查看其余 ${all.length - 6} 条记录 ↓`;
    for (const button of document.querySelectorAll('[data-view-record]')) button.onclick = () => openRecord(Number(button.dataset.viewRecord));
  }

  async function refresh() {
    const version = ++state.request;
    $('#learning-load-status').textContent = '正在整理学习记录…';
    try {
      const [rows, stats] = await Promise.all([get('/api/history'), get('/api/stats')]);
      if (version !== state.request) return;
      state.rows = rows; state.stats = stats;
      renderStats(); renderActivity(); renderRecords();
      $('#learning-load-status').textContent = '';
    } catch (error) { if (version === state.request) $('#learning-load-status').textContent = error.message; }
  }

  async function open(section) {
    window.MathGuideWorkspace.show('learning');
    await refresh();
    if (section === 'records') $('#learning-records-section').scrollIntoView({block: 'start'});
    else if (section === 'weaknesses') $('#learning-weakness-section').scrollIntoView({block: 'start'});
    else window.scrollTo(0, 0);
  }

  function renderDetail(row) {
    state.active = row.id;
    for (const button of document.querySelectorAll('.record-select')) {
      const selected = Number(button.dataset.record) === row.id;
      button.classList.toggle('is-selected', selected); button.setAttribute('aria-pressed', String(selected));
    }
    $('#record-detail').innerHTML = `<div class="record-detail-meta"><span>${dateText(row.record_date)}</span><span>·</span><span>${safe(row.question_type)}</span>${solvedBadge(row)}</div><h3>${safe(row.question_text)}</h3><div class="record-knowledge-card"><strong>${safe(row.knowledge_point)}</strong>${safe(row.formula)}</div><div class="record-conversation-title">完整辅导过程 · ${studentTurns(row)} 次学生作答</div>${(row.dialogue || []).map(message => {
      const student = message.role === 'student' || message.role === 'user';
      return `<div class="record-message ${student ? 'student-turn' : ''}"><span class="record-speaker">${student ? '我' : '师'}</span><div class="record-message-text">${safe(message.content)}</div></div>`;
    }).join('')}<div class="record-result-note ${row.understood ? '' : 'needs-review'}">${row.understood ? '✓ 已记录本题独立解出。把思路记住，再用一道同类题巩固。' : '◷ 这次看过讲解，尚未独立掌握。留给下一次练习，慢慢弄懂。'}</div>`;
    $('#record-detail').scrollTop = 0;
  }
  function renderDialogRows(rows, active) {
    state.dialogRows = rows;
    $('#record-status').textContent = rows.length ? `共 ${rows.length} 条记录 · 点击题目回看完整过程` : '没有找到相关记录。';
    $('#record-list').innerHTML = rows.map(row => `<button type="button" class="record-select" data-record="${row.id}" aria-pressed="false"><small>${dateText(row.record_date)} · ${safe(row.knowledge_point)}</small><strong>${safe(row.question_text)}</strong>${solvedBadge(row)}</button>`).join('');
    for (const button of document.querySelectorAll('.record-select')) button.onclick = () => renderDetail(rows.find(row => row.id === Number(button.dataset.record)));
    if (rows.length) renderDetail(rows.find(row => row.id === active) || rows[0]);
    else $('#record-detail').innerHTML = '<div class="learning-empty">这个筛选条件下还没有学习记录。</div>';
  }
  async function loadDialogRecords() {
    const version = ++state.dialogRequest;
    const params = new URLSearchParams();
    if ($('#record-date').value) params.set('date', $('#record-date').value);
    if ($('#record-type').value) params.set('qtype', $('#record-type').value);
    $('#record-status').textContent = '正在查询…';
    try {
      const rows = await get('/api/history?' + params);
      if (version === state.dialogRequest) renderDialogRows(rows, state.active);
    } catch (error) { if (version === state.dialogRequest) $('#record-status').textContent = error.message; }
  }
  function openRecord(id) {
    state.dialogRequest++;
    $('#record-date').value = ''; $('#record-type').value = '';
    renderDialogRows(state.rows, id);
    if (!$('#records').open) $('#records').showModal();
  }

  $('#learning-tab').onclick = () => open();
  $('#weakness-link').onclick = () => open('weaknesses');
  $('#tutor-tab').onclick = () => {
    window.MathGuideWorkspace.show('tutor');
  };
  $('#learning-practice').onclick = () => $('#practice').click();
  $('#learning-refresh').onclick = refresh;
  $('#learning-search').oninput = event => {state.search = event.target.value.trim(); state.expanded = false; renderRecords();};
  $('#learning-more').onclick = () => {state.expanded = !state.expanded; renderRecords();};
  for (const button of document.querySelectorAll('[data-record-state]')) button.onclick = () => {
    state.filter = button.dataset.recordState; state.expanded = false;
    for (const tab of document.querySelectorAll('[data-record-state]')) {
      const selected = tab === button; tab.classList.toggle('is-active', selected); tab.setAttribute('aria-pressed', String(selected));
    }
    renderRecords();
  };
  window.MathGuideLearning = {open, refresh, loadDialogRecords, updateStats(rows) {state.stats = rows; renderStats();}};
  document.addEventListener('DOMContentLoaded', () => {
    if (new URLSearchParams(location.search).get('view') === 'learning') open();
  });
})();
