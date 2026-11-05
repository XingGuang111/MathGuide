/* MathGuide's web companion; animation provenance lives in assets/pet/SOURCES.md. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const root = $('#pet-card');
  const avatar = $('#pet-avatar');
  const video = $('#pet-video');
  const fallback = $('#pet-fallback');
  const catalog = $('#pet-dialog');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const clips = new Set(['idle', 'touch', 'wave', 'drag', 'eat', 'play', 'think', 'celebrate', 'sleep',
    'stretch', 'giggle', 'bubbles', 'scout', 'busy', 'sort', 'token', 'yawn', 'sigh']);
  const feelings = {
    smile: {label:'微笑陪伴', animation:'idle', message:'我会陪你慢慢想，每一小步都算进步。'},
    thinking: {label:'认真思考', animation:'think', message:'先读清题目，我和你一起找线索。'},
    concerned: {label:'有点担心', animation:'idle', message:'这题有点绕，我们先找出一个已知条件，好吗？'},
    crying: {label:'泪汪汪', animation:'idle', message:'呜，这题把我也绕晕啦。我们一起拆成一小步，慢慢来。'},
    laugh: {label:'开心大笑', animation:'idle', message:'哈哈，你认真思考的样子太棒啦！'},
    coax: {label:'撒娇催学', animation:'idle', message:'再陪我做一道题嘛，做完我们再一起玩呀。'}
  };
  let currentFeeling = {name:'smile', ...feelings.smile}, emotionTimer;
  let profileId, state = null, actionBusy = false, learning = false, collapsed = false;
  let itemFilter = 'all';
  let animation = '', timer, messageTimer, sleepTimer, drag = null, floating = false;
  let rewardQueue = [], rewardRunning = false, clipToken = 0;
  let hatTracks = {}, hatFrame = 0;
  let chatBusy = false;
  let energyUntil = 0, energyWasActive = false, energyWarned = false, stateEpoch = 0, syncingEnergy = false;
  let historyLoaded = false;
  // A manual popover lives above native dialogs. Reparent into the active modal
  // so the browser's inert rules still allow pet interaction there.
  const overlay = document.createElement('div'); overlay.id = 'pet-overlay';
  overlay.setAttribute('popover', 'manual');
  const floater = document.createElement('div'); floater.className = 'pet-floater';
  const tools = document.createElement('div'); tools.className = 'pet-floating-tools';
  const chatToggle = document.createElement('button'); chatToggle.id = 'pet-floating-chat-toggle';
  chatToggle.type = 'button'; chatToggle.textContent = '💬 对话'; chatToggle.setAttribute('aria-expanded', 'false');
  const dock = document.createElement('button'); dock.type = 'button'; dock.textContent = '重置位置'; dock.id = 'pet-floating-home';
  const menuToggle = document.createElement('button'); menuToggle.id = 'pet-menu-toggle'; menuToggle.type = 'button';
  menuToggle.textContent = '菜单'; menuToggle.setAttribute('aria-haspopup', 'dialog'); menuToggle.setAttribute('aria-expanded', 'false');
  tools.append(chatToggle, menuToggle, dock); floater.append(avatar, tools); overlay.append(floater);
  const floatingChat = document.createElement('form'); floatingChat.id = 'pet-floating-chat'; floatingChat.hidden = true;
  const floatingInput = document.createElement('input'); floatingInput.maxLength = 800; floatingInput.required = true;
  floatingInput.placeholder = '和星芽说句话…'; floatingInput.setAttribute('aria-label', '与学习伙伴对话');
  const floatingSend = document.createElement('button'); floatingSend.type = 'submit'; floatingSend.textContent = '发送';
  const floatingClose = document.createElement('button'); floatingClose.type = 'button'; floatingClose.textContent = '收起';
  floatingChat.append(floatingInput, floatingSend, floatingClose); overlay.append(floatingChat);
  const petMenu = document.createElement('section'); petMenu.id = 'pet-context-menu'; petMenu.hidden = true;
  petMenu.setAttribute('role', 'dialog'); petMenu.setAttribute('aria-label', '星芽互动菜单');
  overlay.append(petMenu);
  let menuAnchor = null;
  document.body.append(overlay);
  let overlayFrame = 0;
  function positionPet() {
    overlayFrame = 0;
    if (collapsed) return;
    if (!floating) {
      const compact = innerWidth < 600;
      floater.style.left = `${compact ? innerWidth - 118 : Math.max(8, innerWidth - 202)}px`;
      floater.style.top = `${compact ? (overlay.parentElement.tagName === 'DIALOG' ? 12 : Math.max(80, innerHeight - 155)) : Math.max(80, innerHeight - 225)}px`;
    } else {
      // Keep the user's placement across actions and workspace resize events.
      const box = floater.getBoundingClientRect();
      floater.style.left = `${Math.max(8, Math.min(innerWidth - box.width - 8, box.left))}px`;
      floater.style.top = `${Math.max(8, Math.min(innerHeight - box.height - 35, box.top))}px`;
    }
    overlay.dataset.compact = String(innerWidth < 600);
    const box = floater.getBoundingClientRect(), bubble = $('#pet-message');
    const shift = Math.max(12 - (box.left + 95 - bubble.offsetWidth / 2),
      Math.min(0, innerWidth - 12 - (box.left + 95 + bubble.offsetWidth / 2)));
    bubble.style.setProperty('--bubble-shift', `${shift}px`);
    bubble.classList.toggle('below', box.top < bubble.offsetHeight + 30);
    floatingChat.style.left = `${Math.max(10, Math.min(innerWidth - 290, box.left - 280))}px`;
    floatingChat.style.top = `${Math.max(12, Math.min(innerHeight - 100, box.top + 40))}px`;
    if (!petMenu.hidden) {
      petMenu.style.left = `${Math.max(8, Math.min(innerWidth - petMenu.offsetWidth - 8, menuAnchor?.x ?? box.left - 230))}px`;
      petMenu.style.top = `${Math.max(8, Math.min(innerHeight - petMenu.offsetHeight - 8, menuAnchor?.y ?? box.top))}px`;
    }
  }
  function schedulePosition() { if (!overlayFrame) overlayFrame = requestAnimationFrame(positionPet); }
  function raisePet() {
    const modal = [...document.querySelectorAll('dialog[open]')].filter(node => node.matches(':modal')).at(-1);
    const parent = modal || document.body;
    if (overlay.parentElement !== parent) {
      if (overlay.matches(':popover-open')) overlay.hidePopover();
      parent.append(overlay);
    }
    if (overlay.showPopover && !overlay.matches(':popover-open')) overlay.showPopover();
    schedulePosition();
  }
  new MutationObserver(raisePet).observe(document.body, {attributes:true, attributeFilter:['open'], subtree:true});
  new ResizeObserver(schedulePosition).observe($('#pet-message'));
  window.addEventListener('scroll', schedulePosition, {capture:true, passive:true});
  window.addEventListener('resize', schedulePosition);
  chatToggle.onclick = () => {
    floatingChat.hidden = !floatingChat.hidden; chatToggle.setAttribute('aria-expanded', String(!floatingChat.hidden));
    schedulePosition(); if (!floatingChat.hidden) floatingInput.focus();
  };
  floatingClose.onclick = () => { floatingChat.hidden = true; chatToggle.setAttribute('aria-expanded', 'false'); chatToggle.focus(); };
  floatingChat.onsubmit = async event => {
    event.preventDefault(); if (chatBusy) return;
    const text = floatingInput.value.trim(); if (!text) return;
    floatingSend.disabled = true; floatingInput.value = '';
    await sendChat(text); floatingSend.disabled = false;
    if ($('#pet-chat-input').value) floatingInput.value = text;
  };
  dock.onclick = () => { home(); rest(); message('就在这里，继续陪你学习。'); };
  function closePetMenu() { petMenu.hidden = true; menuToggle.setAttribute('aria-expanded', 'false'); }
  function menuButton(label, handler, disabled = false) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = label; button.disabled = disabled;
    button.onclick = () => { closePetMenu(); handler(); }; return button;
  }
  function renderPetMenu() {
    if (!state) return;
    const header = document.createElement('div'); header.className = 'pet-menu-heading';
    const title = document.createElement('strong'); title.textContent = `星芽 · ${state.coins} ⭐`;
    header.append(title, menuButton('关闭', () => menuToggle.focus()));
    petMenu.replaceChildren(header);
    petMenu.append(menuButton(canPlay() ? '玩耍时间进行中' : '⚡ 开启玩耍时间', startPlay, actionBusy || canPlay()));
    const group = (label, buttons) => {
      const heading = document.createElement('p'); heading.textContent = label;
      const row = document.createElement('div'); row.className = 'pet-menu-options'; row.append(...buttons);
      petMenu.append(heading, row);
    };
    group('陪伴互动', [menuButton('💬 和星芽说话', () => { floatingChat.hidden = false; chatToggle.setAttribute('aria-expanded', 'true'); schedulePosition(); floatingInput.focus(); }),
      menuButton('摸摸头', touch, actionBusy), menuButton('重置位置', () => { home(); rest(); })]);
    const learned = state.actions.filter(item => item.learned);
    group(canPlay() ? '学会的动作 · 自由表演' : '学会的动作 · 开启玩耍时间后表演', [
      ...learned.map(item => menuButton(item.emoji + ' ' + item.name, () => collectionAct('perform', item), actionBusy)),
      menuButton('✨ 学习更多动作', () => openShop('actions'))]);
    const food = state.shop.filter(item => item.kind === 'food' && state.inventory[item.id]);
    group('喂食', [...food.map(item => menuButton(`${item.name} ×${state.inventory[item.id]}`, () => act('interact', item), actionBusy)),
      menuButton('🍪 买食物', () => openShop('food'))]);
    const toys = state.shop.filter(item => item.kind === 'toy' && state.inventory[item.id]);
    group('玩具', [...toys.map(item => menuButton(item.name, () => act('interact', item), actionBusy)),
      menuButton('🎈 买玩具', () => openShop())]);
    group('穿戴装扮', [...state.hats.filter(item => item.owned).map(item => menuButton(
      (item.equipped ? '摘下 ' : '戴上 ') + item.name, () => collectionAct('equip', item), actionBusy)),
      menuButton('🎀 买帽子', () => openShop('hats'))]);
  }
  function openPetMenu(anchor = null) {
    if (!state || collapsed) return;
    menuAnchor = anchor; renderPetMenu(); petMenu.hidden = false;
    menuToggle.setAttribute('aria-expanded', 'true'); positionPet();
    petMenu.querySelector('button').focus();
  }
  avatar.oncontextmenu = event => { event.preventDefault(); openPetMenu({x:event.clientX, y:event.clientY}); };
  menuToggle.onclick = () => petMenu.hidden ? openPetMenu() : closePetMenu();
  document.addEventListener('pointerdown', event => { if (!petMenu.hidden && !petMenu.contains(event.target) && event.target !== menuToggle) closePetMenu(); }, true);
  overlay.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !petMenu.hidden) { event.preventDefault(); event.stopPropagation(); closePetMenu(); menuToggle.focus(); }
  });
  const energyFloating = document.createElement('button'); energyFloating.id = 'pet-energy-floating'; energyFloating.type = 'button'; energyFloating.textContent = '⚡ 活力'; energyFloating.onclick = () => canPlay() ? message('玩耍时间正在进行中。') : startPlay(); tools.append(energyFloating);
  raisePet();
  const studyContext = () => ({session_id: read('mathguide.session', null),
    exercise_id: document.querySelector('#practice-dialog')?.open ? read('mathguide.practice', null) : null});

  // A blocked storage policy should not prevent the math tutor from starting.
  function read(key, fallbackValue) {
    try { return localStorage.getItem(key) ?? fallbackValue; } catch { return fallbackValue; }
  }
  function write(key, value) {
    try { localStorage.setItem(key, value); } catch { /* session-only when unavailable */ }
  }
  let entertainmentProfile = null;
  try { entertainmentProfile = sessionStorage.getItem('mathguide.entertainmentProfile'); } catch {}
  const testMode = Boolean(entertainmentProfile);
  const pendingKey = testMode ? 'mathguide.petEntertainmentPending' : 'mathguide.petPending';
  profileId = entertainmentProfile || read('mathguide.petProfile', null) || `pet-${crypto.randomUUID?.() || Date.now() + '-' + Math.random().toString(36).slice(2)}`;
  if (!testMode) write('mathguide.petProfile', profileId);
  const entertainmentButton = $('#pet-entertainment-open');
  const entertainmentDialog = $('#pet-entertainment-dialog');
  entertainmentButton.onclick = () => {
    if (testMode) { window.MathGuideWorkspace.show('shop'); return; }
    $('#pet-entertainment-error').textContent = ''; $('#pet-entertainment-password').value = '';
    entertainmentDialog.showModal(); $('#pet-entertainment-password').focus();
  };
  $('#pet-entertainment-cancel').onclick = () => entertainmentDialog.close();
  $('#pet-entertainment-form').onsubmit = async event => {
    event.preventDefault(); const submit = $('#pet-entertainment-submit'); submit.disabled = true;
    try {
      const response = await fetch('/api/pet/entertainment/unlock', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({password:$('#pet-entertainment-password').value})});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '暂时无法进入，请稍后重试');
      sessionStorage.setItem('mathguide.entertainmentProfile', data.pet.profile_id);
      const url = new URL(location.href); url.searchParams.delete('pet_test'); url.searchParams.delete('entertainment'); url.searchParams.set('view','shop'); location.assign(url);
    } catch (error) { $('#pet-entertainment-error').textContent = error.message; }
    finally { submit.disabled = false; }
  };
  if (testMode) {
    entertainmentButton.textContent = '🎈 娱乐模式中';
    const banner = document.createElement('div'); banner.id = 'pet-entertainment-banner'; banner.className = 'pet-test-banner';
    const label = document.createElement('span'); label.textContent = '娱乐模式 · 全部道具、动作和帽子已开放 · 食物无限使用';
    const exit = document.createElement('button'); exit.type = 'button'; exit.textContent = '退出娱乐模式';
    exit.onclick = () => { sessionStorage.removeItem('mathguide.entertainmentProfile'); location.reload(); };
    banner.append(label, exit); document.querySelector('main').prepend(banner);
  }
  try { rewardQueue = JSON.parse(read(pendingKey, '[]')); } catch { rewardQueue = []; }
  if (!Array.isArray(rewardQueue)) rewardQueue = [];
  rewardQueue = rewardQueue.filter(value => typeof value === 'string').slice(-30);

  async function request(path, payload = {}) {
    const response = await fetch('/api/pet' + path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: profileId, ...payload })
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : '学习伙伴暂时无法连接，请稍后重试');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function message(text) {
    clearTimeout(messageTimer);
    $('#pet-message').textContent = text;
    schedulePosition();
    messageTimer = setTimeout(() => {
      $('#pet-message').textContent = learning ? '我安静地陪你一起想。' : currentFeeling.message;
    }, 6500);
  }

  function rest() {
    clearTimeout(timer);
    if (!actionBusy && !drag) play(learning || chatBusy ? 'think' : currentFeeling.animation, true);
    clearTimeout(sleepTimer);
    sleepTimer = setTimeout(() => {
      if (!actionBusy && !learning && !chatBusy && !drag) play('sleep', true);
    }, 90000);
  }

  function play(name, loop = false) {
    if (!clips.has(name)) return;
    if (!canPlay() && !['idle','think','celebrate','sleep'].includes(name)) name = 'idle';
    clearTimeout(timer);
    const token = ++clipToken;
    avatar.dataset.animation = name;
    avatar.dataset.expression = name === 'idle' ? currentFeeling.name : '';
    avatar.dataset.clip = name;
    video.loop = loop;
    if (animation !== name || !loop) {
      animation = name;
      video.src = `/assets/pet/${name}.webm`;
      video.load();
    }
    if (collapsed || document.hidden || reducedMotion.matches) {
      video.pause();
    } else {
      video.play().then(() => {
        if (token === clipToken) {
          fallback.hidden = true; video.hidden = false;
          if (name === 'idle') { video.currentTime = .05; video.pause(); }
        }
      }).catch(() => {
        if (token === clipToken) message('动画已暂停；点击伙伴可继续播放。');
      });
    }
    if (!loop) timer = setTimeout(rest, 14000); // includes a network/decode timeout
    syncPracticeVideo(name, loop);
    animateHat();
  }
  fetch('/assets/pet/hat-tracks.json').then(response => response.json()).then(data => { hatTracks = data; animateHat(); }).catch(() => {});
  function animateHat() {
    if (hatFrame) return;
    const update = () => {
      hatFrame = 0;
      const track = hatTracks[animation];
      let dx = 0, dy = 0;
      if (track && !video.hidden) {
        const progress = video.currentTime / track.interval;
        const index = Math.min(track.points.length - 1, Math.floor(progress));
        const a = track.points[index], b = track.points[Math.min(index + 1, track.points.length - 1)];
        if (a && b) { const f = progress - Math.floor(progress); dx = a[0] + (b[0] - a[0]) * f; dy = a[1] + (b[1] - a[1]) * f; }
      }
      for (const [selector, scale] of [['#pet-hat', 360/640], ['#practice-pet-hat', 160/640]]) {
        const image = $(selector);
        image.style.setProperty('--hat-x', `${dx * scale}px`);
        image.style.setProperty('--hat-y', `${dy * scale}px`);
      }
      $('#pet-message').style.setProperty('--head-offset', `${Math.min(0, dy * (360/640) * (state?.level ? [.82,.91,.98,1.05][state.level-1] : .82))}px`);
      if (!document.hidden && !collapsed && !video.paused && state?.equipped_hat && !reducedMotion.matches) hatFrame = requestAnimationFrame(update);
    };
    hatFrame = requestAnimationFrame(update);
  }
  video.addEventListener('playing', animateHat);
  function syncPracticeVideo(name, loop = true) {
    const mini = $('#practice-pet-video');
    if (!$('#practice-dialog')?.open) { mini?.pause(); return; }
    mini.loop = loop;
    mini.closest('.practice-pet-portrait').dataset.clip = name;
    $('#practice-pet-reaction').dataset.expression = name === 'idle' ? currentFeeling.name : '';
    if (mini.dataset.clip !== name) { mini.dataset.clip = name; mini.src = `/assets/pet/${name}.webm`; mini.load(); }
    if (document.hidden || reducedMotion.matches) mini.pause();
    else mini.play().then(() => { if (name === 'idle' && mini.dataset.clip === name) { mini.currentTime=.05; mini.pause(); } }).catch(() => {});
  }
  function setFeeling(value, {speak = true, animate = true, transient = true} = {}) {
    const originalName = typeof value === 'string' ? value : value?.name;
    const name = originalName === 'pout' ? 'coax' : originalName;
    if (originalName === 'pout') value = 'coax';
    if (!Object.hasOwn(feelings, name)) return;
    currentFeeling = {name, ...feelings[name], ...(typeof value === 'object' ? value : {})};
    root.dataset.emotion = name; avatar.dataset.emotion = name;
    $('#pet-emotion').textContent = currentFeeling.label;
    $('#practice-pet-reaction').dataset.emotion = name;
    $('#practice-pet-emotion').textContent = '星芽 · ' + currentFeeling.label;
    $('#practice-pet-message').textContent = currentFeeling.message;
    clearTimeout(emotionTimer);
    if (animate) play(currentFeeling.animation);
    if (speak) message(currentFeeling.message);
    if (transient && !['smile', 'coax'].includes(name)) {
      emotionTimer = setTimeout(() => {
        if (chatBusy || learning || drag) return;
        setFeeling('smile', {speak:false, transient:false});
      }, 12000);
    }
  }
  video.onended = rest;
  video.onerror = () => {
    video.hidden = true; fallback.hidden = false;
    avatar.dataset.expression = '';
    message('动画暂时无法播放，仍然可以照顾伙伴。');
  };

  function render(data) {
    state = data;
    if (data.entertainment_mode) {
      $('#shop-items-panel .pet-dialog-note').textContent = '全部食物和玩具已开放，食物可无限喂养，点击即可播放对应互动。';
      $('#shop-actions-panel .pet-dialog-note').textContent = '全部动作已学会，可以连续免费表演。';
      $('#shop-hats-panel .pet-dialog-note').textContent = '全部帽子已拥有，随时戴上、摘下或换一顶。';
    }
    data.shop.forEach(item => clips.add(item.animation));
    data.actions.forEach(item => clips.add(item.animation));
    stateEpoch++;
    energyUntil = performance.now() + (data.energy?.remaining_seconds || 0) * 1000;
    updateEnergy();
    setFeeling(data.feeling || 'smile', {speak:false, animate:false});
    root.dataset.level = data.level;
    const scales = [0.82, 0.91, 0.98, 1.05];
    avatar.style.setProperty('--pet-scale', scales[data.level - 1] || 1);
    $('#pet-message').style.setProperty('--bubble-lift', `${Math.max(0, (scales[data.level - 1] - .82) * 130)
      + (data.equipped_hat ? (data.equipped_hat.id === 'hat_wizard' ? 30 : 12) : 0)}px`);
    $('#pet-stage').textContent = `Lv.${data.level} · ${data.stage}`;
    $('#pet-coins').textContent = `⭐ ${data.coins}`;
    $('#pet-mood').textContent = `心情 ${data.mood}/100`;
    $('#pet-crown').hidden = data.level < 4 || Boolean(data.equipped_hat);
    for (const image of [$('#pet-hat'), $('#practice-pet-hat')]) {
      image.hidden = !data.equipped_hat;
      if (data.equipped_hat) {
        image.src = data.equipped_hat.overlay; image.alt = data.equipped_hat.name;
      } else { image.removeAttribute('src'); image.alt = ''; }
    }
    animateHat();
    $('#pet-action-count').textContent = `${data.actions.filter(item => item.learned).length}/${data.actions.length}`;
    $('#pet-wardrobe').title = data.equipped_hat ? `正在戴：${data.equipped_hat.name}` : '选择一顶帽子';
    const current = data.stages[data.level - 1].xp;
    const pct = data.next_xp ? 100 * (data.xp - current) / (data.next_xp - current) : 100;
    $('#pet-xp-bar').style.width = `${Math.min(100, Math.max(0, pct))}%`;
    $('#pet-progress').setAttribute('aria-valuenow', String(Math.round(pct)));
    $('#pet-xp-text').textContent = data.next_xp
      ? `成长值 ${data.xp} · 再积累 ${data.next_xp - data.xp} 进阶`
      : `成长值 ${data.xp} · 星光伙伴已达成`;
    $('#pet-timeline').replaceChildren(...data.stages.map(stage => {
      const node = document.createElement('span');
      node.className = stage.level <= data.level ? 'on' : '';
      node.textContent = stage.name;
      node.title = `${stage.xp} 成长值解锁`;
      if (stage.level === data.level) node.setAttribute('aria-current', 'step');
      return node;
    }));
    for (const selector of ['#pet-shop', '#pet-feed', '#pet-play']) $(selector).disabled = false;
    renderItems();
  }

  function canPlay() {
    return Boolean(state?.energy?.unlimited || (state?.energy?.active && performance.now() < energyUntil));
  }
  function updateEnergy() {
    const e = state?.energy;
    if (!e) return;
    const seconds = Math.max(0, Math.ceil((energyUntil-performance.now())/1000));
    const active = canPlay();
    const time = `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
    const exhausted = !e.unlimited && e.available_seconds < e.session_seconds;
    $('#pet-energy-value').textContent = e.unlimited ? '娱乐模式 · 自由互动' : `今日活力 ${e.balance} / ${e.capacity}`;
    $('#pet-energy-status').textContent = e.unlimited ? e.message : active ? `玩耍剩余 ${time}` : exhausted ? '今日玩耍已结束，星芽继续安静陪学。' : e.balance >= e.cost ? '活力准备好了，随时开启玩耍。' : '安静陪学中 · 完成小任务获得活力';
    $('#pet-energy-quota').textContent = `每日玩耍额度 ${e.daily_limit_seconds/60} 分钟；今日还可开启 ${Math.floor(e.available_seconds/60)} 分钟。倒计时开始后，关闭页面也会继续计时。`;
    const button = $('#pet-energy-start');
    button.textContent = active ? (e.unlimited ? '自由互动已开启' : `正在玩耍 ${time}`) : `${e.cost} 活力 · 玩 ${e.session_seconds/60} 分钟`;
    button.disabled = actionBusy || active || exhausted || e.balance < e.cost;
    energyFloating.textContent = active ? (e.unlimited ? '⚡ 自由玩耍' : `⚡ ${time}`) : `⚡ ${e.balance}/${e.cost}`;
    energyFloating.title = active ? '玩耍时间正在进行中' : e.message;
    energyFloating.disabled = actionBusy;
    if (energyWasActive && !active) {
      clearTimeout(timer); clearTimeout(emotionTimer); $('#pet-prop').hidden = true;
      play('idle', true);
      message('这段玩耍时间结束啦，我安静陪你继续学，也可以先休息一下。');
      energyWarned = false;
    }
    if (active && !e.unlimited && seconds <= 15 && !energyWarned) {
      energyWarned = true; message('还有一小会儿，玩完这次我们就一起回到学习吧。');
    }
    if (active && !energyWasActive) energyWarned = false;
    energyWasActive = active;
  }
  function showEnergyReminder(text) {
    message(text || (state?.energy?.active && !canPlay() ? '这段玩耍时间结束啦，我安静陪你继续学。' : state?.energy?.message) || '完成学习小任务，就能获得玩耍活力。');
    $('#shop-status').textContent = state?.energy?.balance >= (state?.energy?.cost || 20)
      ? '点击“开启玩耍”或活力按钮，开始一段玩耍时间。' : '已拥有的道具会保留，先完成学习小任务攒活力吧。';
    syncEnergy();
  }
  async function startPlay() {
    if (!state || actionBusy || canPlay()) return;
    actionBusy = true; updateEnergy();
    try {
      const result = await request('/play/start', {}); render(result.pet);
      message(result.started ? '玩耍时间开始啦！可以摸摸、喂食、玩玩具和表演。' : result.pet.energy.message);
    } catch (error) { message(error.message); }
    finally { actionBusy = false; updateEnergy(); renderItems(); }
  }
  async function syncEnergy() {
    if (document.hidden || syncingEnergy || actionBusy || chatBusy || rewardRunning) return;
    syncingEnergy = true;
    const epoch = stateEpoch;
    try { const result = await request(''); if (stateEpoch === epoch) render(result); } catch {}
    finally { syncingEnergy = false; }
  }
  $('#pet-energy-start').onclick = startPlay;
  $('#pet-energy-study').onclick = () => $('#pet-study').click();
  setInterval(updateEnergy, 250);
  setInterval(syncEnergy, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) syncEnergy(); });
  window.addEventListener('focus', syncEnergy);

  function itemCard(item) {
    const card = document.createElement('article'); card.className = 'shop-item';
    card.dataset.item = item.id;
    if (item.embedded_prop) card.classList.add('shop-animated-item');
    const image = document.createElement('img'); image.src = item.image; image.alt = item.name;
    image.width = 64; image.height = 64;
    image.loading = 'lazy';
    const name = document.createElement('strong'); name.textContent = item.name;
    const description = document.createElement('p'); description.textContent = item.description;
    const count = state.inventory[item.id] || 0;
    const label = document.createElement('small');
    label.textContent = state.entertainment_mode ? '娱乐模式 · 无限使用' : item.kind === 'toy' ? (count ? '已拥有 · 可反复玩' : `${item.price} 星星 · 永久玩具`) : `${item.price} 星星 / 份 · 背包 ${count}`;
    const controls = document.createElement('div'); controls.className = 'item-actions';
    const buy = document.createElement('button'); buy.type = 'button';
    buy.dataset.buy = item.id;
    buy.textContent = item.kind === 'toy' && count ? '已拥有' : `购买 ${item.price} ⭐`;
    buy.disabled = actionBusy || state.coins < item.price || (item.kind === 'toy' && count > 0);
    buy.onclick = () => act('purchase', item);
    buy.hidden = Boolean(state.entertainment_mode);
    const use = document.createElement('button'); use.type = 'button'; use.className = 'secondary';
    use.dataset.use = item.id;
    use.textContent = item.kind === 'food' ? '喂给伙伴' : '一起玩';
    use.disabled = actionBusy || count < 1;
    use.onclick = () => act('interact', item);
    controls.append(buy, use); card.append(image, name);
    if (item.embedded_prop) {
      const badge = document.createElement('span'); badge.className = 'shop-animation-badge'; badge.textContent = '专属动作';
      card.append(badge);
    }
    card.append(description, label, controls);
    return card;
  }

  function renderItems() {
    if (!state) return;
    $('#shop-balance').textContent = `我的星星 ${state.coins} ⭐`;
    const items = state.shop.filter(item => itemFilter === 'all'
      || (itemFilter === 'food' && item.kind === 'food' && item.category !== 'festival')
      || (itemFilter === 'festival' && item.category === 'festival')
      || (itemFilter === 'toy' && item.kind === 'toy')
      || (itemFilter === 'owned' && state.inventory[item.id] > 0));
    $('#shop-grid').replaceChildren(...['food', 'toy'].map(kind => {
      const section = document.createElement('section'); section.className = 'shop-category';
      section.dataset.category = kind;
      const title = document.createElement('h3'); title.id = `shop-${kind}-title`;
      const categoryItems = items.filter(item => item.kind === kind);
      title.textContent = `${kind === 'food' ? '🍱 食物' : '🧸 玩具'} · ${categoryItems.length}`;
      section.setAttribute('aria-labelledby', title.id);
      const grid = document.createElement('div'); grid.className = 'shop-category-grid';
      grid.replaceChildren(...categoryItems.map(itemCard));
      if (!categoryItems.length) {
        const empty = document.createElement('p'); empty.className = 'shop-empty';
        empty.textContent = '当前筛选下没有商品'; grid.append(empty);
      }
      section.append(title, grid); return section;
    }));
    document.querySelectorAll('[data-item-filter]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.itemFilter === itemFilter)));
    $('#pet-lessons-grid').replaceChildren(...state.actions.map(collectionCard));
    $('#pet-hats-grid').replaceChildren(...state.hats.map(collectionCard));
    if (!petMenu.hidden) { renderPetMenu(); schedulePosition(); }
    $('#pet-inventory').replaceChildren(...state.shop.filter((item, index) => index < 4 || state.inventory[item.id] > 0).map(item => {
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'inventory-item'; button.disabled = actionBusy;
      const image = document.createElement('img'); image.src = item.image; image.alt = '';
      const count = state.inventory[item.id] || 0;
      const text = document.createElement('span'); text.textContent = state.entertainment_mode && item.kind === 'food' ? '∞' : item.kind === 'toy' && count ? '已拥有' : `×${count}`;
      button.title = `${item.name}：${count ? (item.kind === 'food' ? '点击喂食' : '点击玩耍') : '去商店购买'}`;
      button.setAttribute('aria-label', button.title);
      button.onclick = () => count ? act('interact', item) : openShop();
      button.append(image, text); return button;
    }));
  }

  document.querySelectorAll('[data-item-filter]').forEach(button => {
    button.onclick = () => { itemFilter = button.dataset.itemFilter; renderItems(); };
  });

  function collectionCard(item) {
    const card = document.createElement('article'); card.className = 'shop-item';
    card.dataset.collection = item.id;
    const art = document.createElement(item.kind === 'hat' ? 'img' : 'span');
    if (item.kind === 'hat') { art.src = item.image; art.alt = item.name; art.width = 64; art.height = 64; }
    else { art.className = 'pet-trick-icon'; art.textContent = item.emoji; art.setAttribute('aria-hidden', 'true'); }
    const name = document.createElement('strong'); name.textContent = item.name;
    const description = document.createElement('p'); description.textContent = item.description;
    const owned = item.kind === 'hat' ? item.owned : item.learned;
    const label = document.createElement('small');
    label.textContent = owned ? (item.kind === 'hat' ? (item.equipped ? '正在戴 · 已拥有' : '已拥有 · 随时换戴') : '已学会 · 表演免费')
      : `${item.price} 星星 · ${item.kind === 'hat' ? '永久拥有' : '永久学会'}`;
    const controls = document.createElement('div'); controls.className = 'item-actions';
    const button = document.createElement('button'); button.type = 'button';
    button.dataset[owned ? (item.kind === 'hat' ? 'equip' : 'perform') : (item.kind === 'hat' ? 'hatBuy' : 'learn')] = item.id;
    button.textContent = owned ? (item.kind === 'hat' ? (item.equipped ? '摘下帽子' : '戴上帽子') : '表演一下')
      : `${item.kind === 'hat' ? '购买' : '学习'} ${item.price} ⭐`;
    button.disabled = actionBusy || (!owned && state.coins < item.price);
    button.onclick = () => collectionAct(owned ? (item.kind === 'hat' ? 'equip' : 'perform') : (item.kind === 'hat' ? 'purchase' : 'learn'), item);
    if (!owned && state.coins < item.price) label.textContent += ` · 还差 ${item.price - state.coins} ⭐`;
    controls.append(button); card.append(art, name, description, label, controls);
    return card;
  }

  async function collectionAct(action, item) {
    if (actionBusy) return;
    if (action === 'perform' && !canPlay()) { showEnergyReminder(); return; }
    actionBusy = true; renderItems();
    $('#shop-status').textContent = '正在保存…';
    const payload = action === 'equip' ? {hat_id: item.equipped ? null : item.id}
      : action === 'purchase' ? {item_id: item.id} : {action_id: item.id};
    try {
      const result = await request('/' + action, payload);
      render(result.pet);
      if (action === 'perform') {
        if (!result.performed) { showEnergyReminder(result.reply); return; }
        clearTimeout(emotionTimer);
        play(item.animation);
        message(`看，我学会的${item.name}！表演不再花星星哦。`);
      } else if (action === 'equip') {
        play('idle', true);
        message(item.equipped ? '摘下帽子啦，随时可以换一顶。' : `戴上${item.name}，陪你继续学习！`);
      } else {
        const text = action === 'learn' ? `星芽学会了${item.name}！点击“表演一下”就能看。`
          : `${item.name}已放进衣橱，点击“戴上帽子”试试吧。`;
        $('#shop-status').textContent = text; message(text);
      }
    } catch (error) { $('#shop-status').textContent = error.message; message(error.message); }
    finally { actionBusy = false; renderItems(); if (rewardQueue.length) flushRewards(); }
  }

  const shopSections = ['items', 'actions', 'hats'];
  function selectShop(section, focus = false) {
    for (const key of shopSections) {
      const selected = key === section, tab = $(`#pet-tab-${key}`);
      tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
      $(`#shop-${key}-panel`).hidden = !selected;
      if (selected && focus) tab.focus();
    }
  }
  for (const [index, key] of shopSections.entries()) {
    const tab = $(`#pet-tab-${key}`);
    tab.onclick = () => { selectShop(key); $('#shop-status').textContent = ''; };
    tab.onkeydown = event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % 3;
      if (event.key === 'ArrowLeft') next = (index + 2) % 3;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = 2;
      if (next !== undefined) { event.preventDefault(); selectShop(shopSections[next], true); $('#shop-status').textContent = ''; }
    };
  }

  async function act(action, item) {
    if (actionBusy) return;
    if (action === 'interact' && !canPlay()) { showEnergyReminder(); return; }
    actionBusy = true; renderItems();
    $('#shop-status').textContent = action === 'purchase' ? '正在购买…' : '正在取出道具…';
    try {
      const data = await request('/' + action, { item_id: item.id });
      render(data.pet);
      if (data.interacted === false) { showEnergyReminder(data.reply); return; }
      if (action === 'purchase') {
        $('#shop-status').textContent = `已购买${item.name}，可以点击${item.kind === 'food' ? '“喂给伙伴”' : '“一起玩”'}。`;
        message(`${item.name}已经放进背包啦。`);
      } else {
        clearTimeout(emotionTimer);
        const usedItem = data.item;
        const prop = $('#pet-prop'); prop.src = usedItem.image; prop.alt = usedItem.name;
        prop.hidden = Boolean(usedItem.embedded_prop);
        play(usedItem.animation);
        setFeeling('smile', {speak:false, animate:false});
        $('#shop-status').textContent = '';
        message(item.kind === 'food' ? `谢谢你的${item.name}，好好吃！` : `一起玩${item.name}，休息一下吧！`);
        setTimeout(() => { prop.hidden = true; }, 3500);
      }
    } catch (error) {
      $('#shop-status').textContent = error.message;
      message(error.message);
    } finally {
      actionBusy = false; renderItems();
      if (rewardQueue.length) flushRewards();
    }
  }

  function openShop(kind) {
    window.MathGuideWorkspace.show('shop');
    if (!state) { message('正在连接学习伙伴，请稍后再试。'); return; }
    selectShop(kind === 'actions' || kind === 'hats' ? kind : 'items');
    itemFilter = kind === 'food' ? 'food' : kind === 'toy' ? 'toy' : 'all';
    renderItems(); $('#shop-status').textContent = state.entertainment_mode ? '娱乐模式：所有道具均已开放，尽情和星芽互动吧！' : kind === 'food' ? '选择背包里的食物喂给伙伴，或先购买一份。'
      : kind === 'toy' ? '玩具购买后可反复使用，点击“一起玩”即可。' : '做完一题辅导 +20 星星；练习独立答对 +10 星星。';
    if (kind === 'toy') catalog.querySelector('[data-buy="ball"]').focus();
  }

  function home() {
    if (drag && avatar.hasPointerCapture(drag.id)) avatar.releasePointerCapture(drag.id);
    drag = null; floating = false;
    avatar.classList.remove('floating', 'dragging');
    floater.style.removeProperty('left'); floater.style.removeProperty('top');
    $('#pet-home').hidden = true;
    schedulePosition();
  }
  async function touch() {
    if (collapsed || actionBusy || chatBusy) return;
    // Touches outside a play window remain a short, quiet acknowledgement.
    actionBusy = true;
    try {
      const result = await request('/touch', {session_id: studyContext().session_id});
      render(result.pet);
      if (result.playful && canPlay()) play(Math.random() < .5 ? 'touch' : 'wave');
      else play('idle', true);
      message(result.reply);
    } catch { message('我在这里陪着你。连接恢复后再一起玩。'); }
    finally { actionBusy = false; renderItems(); }
  }

  function addChat(text, role) {
    const log = $('#pet-chat-log'), line = document.createElement('div');
    line.className = 'pet-chat-line' + (role === 'user' ? ' student' : '');
    line.textContent = text; log.append(line);
    while (log.children.length > 12) log.firstChild.remove();
    log.scrollTop = log.scrollHeight;
  }
  async function openChat() {
    const panel = $('#pet-chat-panel'); panel.hidden = !panel.hidden;
    $('#pet-chat-toggle').setAttribute('aria-expanded', String(!panel.hidden));
    if (panel.hidden) return;
    if (!historyLoaded) {
      try {
        const data = await request('/chat/history');
        if (!$('#pet-chat-log').children.length) data.messages.forEach(row => addChat(row.content, row.role));
        historyLoaded = true;
      } catch { $('#pet-chat-status').textContent = '历史对话暂时无法读取，仍可发送新消息。'; }
    }
    $('#pet-chat-input').focus();
  }
  async function sendChat(text) {
    text = text.trim(); if (!text || chatBusy) return;
    chatBusy = true; $('#pet-chat-send').disabled = true;
    document.querySelectorAll('[data-pet-say]').forEach(button => { button.disabled = true; });
    $('#pet-chat-input').value = ''; addChat(text, 'user');
    $('#pet-chat-status').textContent = '星芽正在认真听你说…'; play('think', true);
    try {
      const result = await request('/chat', {message: text, ...studyContext()});
      render(result.pet); addChat(result.reply, 'assistant'); message(result.reply);
      $('#pet-chat-status').textContent = result.source === 'fallback'
        ? 'AI 模型暂时未连接，星芽使用备用鼓励回复。' : '由所选 AI 模型回复';
      setFeeling(result.pet.feeling || 'smile', {speak:false});
    } catch (error) {
      $('#pet-chat-status').textContent = error.message + '，内容已保留，可以重试。';
      $('#pet-chat-input').value = text;
    } finally {
      chatBusy = false; $('#pet-chat-send').disabled = false;
      document.querySelectorAll('[data-pet-say]').forEach(button => { button.disabled = false; });
      if (animation === 'think') rest();
    }
  }
  $('#pet-chat-toggle').onclick = openChat;
  $('#pet-chat-form').onsubmit = event => { event.preventDefault(); sendChat($('#pet-chat-input').value); };
  document.querySelectorAll('[data-pet-say]').forEach(button => { button.onclick = () => sendChat(button.dataset.petSay); });
  $('#pet-study').onclick = () => {
    window.MathGuideWorkspace.show('tutor');
    if ($('#pet-chat-panel')) { $('#pet-chat-panel').hidden = true; $('#pet-chat-toggle').setAttribute('aria-expanded', 'false'); }
    if (read('mathguide.session', null)) { document.querySelector('#input').focus(); document.querySelector('#input').scrollIntoView({block: 'center'}); }
    else document.querySelector('#practice').click();
  };
  avatar.onpointerdown = event => {
    if (event.button !== 0 || actionBusy) return;
    const box = avatar.getBoundingClientRect();
    drag = { id: event.pointerId, startX: event.clientX, startY: event.clientY,
      x: box.left, y: box.top, wasFloating: floating, moved: false };
    avatar.setPointerCapture(event.pointerId);
  };
  avatar.onpointermove = event => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.startX, dy = event.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) < 6) return;
    if (!drag.moved) { drag.moved = true; play(canPlay() ? 'drag' : 'idle', true); }
    floating = true; avatar.classList.add('floating', 'dragging');
    const currentBox = avatar.getBoundingClientRect();
    const maxX = Math.max(8, innerWidth - currentBox.width - 8);
    const maxY = Math.max(8, innerHeight - currentBox.height - 35);
    floater.style.left = `${Math.max(8, Math.min(maxX, drag.x + dx))}px`;
    floater.style.top = `${Math.max(8, Math.min(maxY, drag.y + dy))}px`;
    schedulePosition();
  };
  avatar.onpointerup = event => {
    if (!drag || drag.id !== event.pointerId) return;
    const moved = drag.moved; drag = null;
    if (avatar.hasPointerCapture(event.pointerId)) avatar.releasePointerCapture(event.pointerId);
    avatar.classList.remove('dragging');
    if (moved) {
      $('#pet-home').hidden = false;
      touch();
      message('这里也能陪你！点“重置位置”就能回到页面角落。');
    } else touch();
  };
  avatar.onpointercancel = () => { home(); rest(); };
  avatar.onlostpointercapture = () => { if (drag) { home(); rest(); } };
  avatar.onkeydown = event => {
    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
      event.preventDefault(); openPetMenu(); return;
    }
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); touch(); }
    if (event.key === 'Escape') { home(); rest(); }
  };
  $('#pet-home').onclick = () => { home(); rest(); message('就在这里，继续陪你学习。'); };
  $('#pet-shop').onclick = () => openShop();
  $('#pet-feed').onclick = () => openShop('food');
  $('#pet-play').onclick = () => openShop('toy');
  $('#pet-lessons').onclick = () => openShop('actions');
  $('#pet-wardrobe').onclick = () => openShop('hats');
  $('#pet-touch').onclick = touch;
  $('#pet-dialog-close').onclick = () => { window.MathGuideWorkspace.show('tutor'); window.scrollTo(0, 0); };
  $('#pet-collapse').onclick = () => {
    collapsed = !collapsed;
    if (collapsed) home();
    $('#pet-message').hidden = collapsed;
    floater.hidden = collapsed;
    if (collapsed) { floatingChat.hidden = true; chatToggle.setAttribute('aria-expanded', 'false'); }
    if (collapsed) closePetMenu();
    else schedulePosition();
    $('#pet-collapse').textContent = collapsed ? '显示星芽' : '隐藏星芽';
    $('#pet-collapse').setAttribute('aria-expanded', String(!collapsed));
    collapsed ? video.pause() : rest();
  };
  window.addEventListener('blur', () => { if (drag) { home(); rest(); } });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { video.pause(); $('#practice-pet-video').pause(); }
    else { if (!collapsed && !reducedMotion.matches && animation !== 'idle') video.play().catch(() => {}); syncPracticeVideo(animation, true); }
  });
  $('#practice-dialog').addEventListener('close', () => $('#practice-pet-video').pause());
  reducedMotion.addEventListener('change', rest);

  async function flushRewards() {
    if (rewardRunning || actionBusy) return;
    rewardRunning = true;
    try {
      while (rewardQueue.length) {
        const eventId = rewardQueue[0];
        try {
          const before = state?.level || 1;
          const result = await request('/reward', { event_id: eventId });
          render(result.pet);
          if (result.awarded) {
            setFeeling(result.pet.feeling || 'smile', {speak:false});
            const reaction = result.pet.feeling?.message || '谢谢你陪我成长。';
            const energyNote = result.energy_awarded ? ` +${result.energy_awarded} 活力！` : '';
            if (!result.points) { message(`完成学习小步骤，${energyNote || '进步已经记下啦。'}`); }
            else {
            message(result.pet.level > before ? `伙伴进阶啦！${result.pet.stage} · +${result.points} 星星\n${reaction}`
              : `任务完成，+${result.points} 星星！${energyNote}${reaction}`);
            }
          }
        } catch (error) {
          if (error.status !== 422 && error.status !== 404) {
            message('奖励已记下，连接恢复后会再领取。');
            break;
          }
        }
        rewardQueue.shift(); write(pendingKey, JSON.stringify(rewardQueue));
      }
    } finally { rewardRunning = false; }
  }
  window.MathGuidePet = {
    openShop,
    setLearning(value) {
      learning = value;
      if (value && !chatBusy && !actionBusy && !drag) setFeeling('thinking');
      if (!value && currentFeeling.name === 'thinking') setFeeling('smile', {speak:false});
    },
    react(value) { setFeeling(value); },
    claimReward(eventId) {
      if (testMode) return Promise.resolve();
      if (!rewardQueue.includes(eventId)) rewardQueue.push(eventId);
      write(pendingKey, JSON.stringify(rewardQueue));
      return flushRewards();
    },
    encourage() { message('没关系，我们再看看解题思路。'); }
  };
  window.addEventListener('online', flushRewards);
  async function load() {
    try { render(await request('')); rest(); flushRewards(); }
    catch (error) { message(error.message); $('#pet-stage').textContent = '暂时离线'; }
  }
  $('#pet-retry').onclick = load;
  load();
  if (!testMode && new URLSearchParams(location.search).get('entertainment') === '1') entertainmentButton.click();
})();
