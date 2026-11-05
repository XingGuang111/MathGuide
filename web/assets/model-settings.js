(() => {
  const $ = id => document.getElementById(id);
  const dialog = $('model-settings-dialog'), form = $('model-settings-form');
  const service = $('model-service'), address = $('model-base-url'), key = $('model-api-key');
  const active = $('model-active'), note = $('model-list-note'), status = $('model-settings-status');
  const presets = {
    ollama: {url: 'http://127.0.0.1:11434', docs: 'https://ollama.com/library'},
    deepseek: {url: 'https://api.deepseek.com/v1', docs: 'https://api-docs.deepseek.com/'},
    qwen: {url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', docs: 'https://help.aliyun.com/zh/model-studio/models'},
    lmstudio: {url: 'http://localhost:1234/v1', docs: 'https://lmstudio.ai/docs/developer/openai-compat'}
  };
  let draft, saved, catalogs, pending = false, loaded = false;
  const local = () => draft.provider === 'ollama';
  const namesField = () => local() ? 'ollama_models' : 'online_models';
  const modelField = () => local() ? 'ollama_model' : 'online_model';
  const urlField = () => local() ? 'ollama_url' : 'base_url';
  function message(text, state = '') { status.textContent = text; status.dataset.state = state; }
  function detectService() {
    if (local()) return 'ollama';
    try {
      const url = new URL(draft.base_url);
      if (url.hostname === 'api.deepseek.com') return 'deepseek';
      if (url.hostname === 'dashscope.aliyuncs.com') return 'qwen';
      if (['localhost', '127.0.0.1'].includes(url.hostname) && url.port === '1234') return 'lmstudio';
    } catch {}
    return 'custom';
  }
  function renderAddress() {
    address.value = draft[urlField()];
    $('model-address-preview').textContent = address.value;
    $('model-key-section').hidden = local();
    $('model-sharing-note').hidden = local() || service.value === 'lmstudio';
    $('model-clear-label').hidden = local();
    const docs = presets[service.value]?.docs;
    $('model-official-link').hidden = !docs;
    $('model-official-link').href = docs || '#';
    key.placeholder = saved.has_api_key && draft.base_url === saved.base_url
      ? '已保存密钥，留空保持不变' : (service.value === 'lmstudio' ? '未开启认证时可留空' : '输入服务商提供的密钥');
  }
  function renderModels() {
    const names = draft[namesField()];
    const current = draft[modelField()];
    active.replaceChildren(new Option('请选择模型', ''));
    for (const name of names) active.add(new Option(name, name));
    active.value = current;
    $('model-count').textContent = names.length ? `· ${names.length}` : '';
    const list = $('model-list'); list.replaceChildren();
    for (const name of new Set([...names, ...catalogs[draft.provider]])) {
      const label = document.createElement('label'), checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.checked = names.includes(name);
      checkbox.onchange = () => {
        if (checkbox.checked && names.length >= 100) { checkbox.checked = false; note.textContent = '最多保存 100 个常用模型。'; return; }
        draft[namesField()] = checkbox.checked ? [...names, name] : names.filter(item => item !== name);
        if (!draft[namesField()].includes(current)) draft[modelField()] = draft[namesField()][0] || '';
        renderModels(); message('');
      };
      label.append(checkbox, document.createTextNode(name)); list.append(label);
    }
  }
  function fill(data) {
    saved = {...data};
    draft = {...data, ollama_models: [...(data.ollama_models || [data.ollama_model])], online_models: [...(data.online_models || [data.online_model])]};
    catalogs = {ollama: [], compatible: []};
    key.value = ''; $('model-clear-key').checked = false;
    service.value = detectService();
    $('model-address-editor').hidden = service.value !== 'custom';
    $('model-vision-note').textContent = `看图分析使用本地模型 ${data.vision_model}。`;
    note.textContent = '';
    renderAddress(); renderModels();
  }
  function setAddress(url) {
    url = url.trim().replace(/\/+$/, '');
    if (draft[urlField()] !== url) {
      draft[urlField()] = url;
      draft[namesField()] = []; draft[modelField()] = ''; catalogs[draft.provider] = [];
      if (!local()) { key.value = ''; $('model-clear-key').checked = false; }
      note.textContent = '地址已更改，请重新获取模型列表。';
    }
    renderAddress(); renderModels(); message('');
  }
  service.onchange = () => {
    draft.provider = service.value === 'ollama' ? 'ollama' : 'compatible';
    if (presets[service.value] && service.value !== 'ollama') setAddress(presets[service.value].url);
    renderAddress(); renderModels(); message('');
    $('model-address-editor').hidden = service.value !== 'custom';
    if (service.value === 'custom') address.focus();
  };
  $('model-address-edit').onclick = () => { $('model-address-editor').hidden = false; address.focus(); };
  address.onchange = () => {
    setAddress(address.value);
    service.value = detectService(); renderAddress();
  };
  active.onchange = () => { draft[modelField()] = active.value; message(''); };
  function payload() {
    const data = {};
    for (const name of ['provider', 'ollama_url', 'base_url', 'ollama_model', 'online_model', 'ollama_models', 'online_models']) data[name] = draft[name];
    // Inactive model names are required by the persisted profile but are not sent to the active service.
    for (const name of ['ollama_model', 'online_model']) if (!data[name]) data[name] = saved[name];
    data.api_key = key.value.trim(); data.clear_api_key = $('model-clear-key').checked;
    return data;
  }
  async function request(url, options = {}) {
    let response;
    try { response = await fetch(url, options); }
    catch { throw new Error('未能连接 MathGuide 网页服务，请确认服务正在运行后重试。'); }
    const data = await response.json().catch(() => { throw new Error(`网页服务返回异常（HTTP ${response.status}），请稍后重试。`); });
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请检查服务地址和模型配置。');
    return data;
  }
  function lock(value) {
    pending = value;
    for (const el of form.querySelectorAll('input, select, button')) el.disabled = value || (!loaded && el.id !== 'model-settings-close');
  }
  $('model-settings-open').onclick = async () => {
    dialog.showModal(); $('model-manage').open = false; $('model-advanced').open = false;
    loaded = false; lock(true); message('正在读取设置…');
    try { fill(await request('/api/model-settings')); loaded = true; message(''); }
    catch (error) { message(error.message, 'error'); }
    finally { lock(false); }
  };
  $('model-settings-close').onclick = () => dialog.close();
  dialog.addEventListener('cancel', event => { if (pending) event.preventDefault(); });
  dialog.addEventListener('close', () => { key.value = ''; });
  $('model-list-fetch').onclick = async () => {
    if (pending || !loaded) return;
    lock(true); note.textContent = '正在获取模型…'; message('');
    try {
      const data = await request('/api/model-settings/models', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload())});
      catalogs[draft.provider] = data.models;
      if (!draft[namesField()].length && data.models.length) { draft[namesField()] = [data.models[0]]; draft[modelField()] = data.models[0]; }
      renderModels(); $('model-manage').open = true;
      note.textContent = data.models.length ? `已获取 ${data.models.length} 个模型，可在下方多选。` : '没有可用模型，可从官网查询后手动添加。';
    } catch (error) { note.textContent = error.message; $('model-manage').open = true; }
    finally { lock(false); }
  };
  $('model-list-add').onclick = () => {
    const name = $('model-manual-name').value.trim(), names = draft[namesField()];
    if (!name) { $('model-manual-name').focus(); return; }
    if (names.length >= 100 && !names.includes(name)) { note.textContent = '最多保存 100 个模型。'; return; }
    if (!names.includes(name)) names.push(name);
    draft[modelField()] = name; $('model-manual-name').value = ''; renderModels(); message('');
  };
  async function submit(test) {
    if (pending || !loaded) return;
    if (!draft[modelField()]) { message('请先获取模型列表或手动添加一个模型。', 'error'); $('model-manage').open = true; return; }
    if (!address.checkValidity()) { $('model-address-editor').hidden = false; address.reportValidity(); return; }
    lock(true); message(test ? '正在测试连接…' : '正在保存…');
    try {
      const data = await request('/api/model-settings' + (test ? '/test' : ''), {method: test ? 'POST' : 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload())});
      if (test) message(data.message, data.ok ? 'success' : 'error');
      else {
        fill(data); message('已保存，下次对话开始生效。', 'success');
        $('health').textContent = '● 已切换模型'; $('health').title = draft[modelField()]; $('health').style.color = '#2365d3';
      }
    } catch (error) { message(error.message, 'error'); }
    finally { lock(false); }
  }
  form.onsubmit = event => { event.preventDefault(); };
  $('model-settings-test').onclick = () => submit(true);
  $('model-settings-save').onclick = () => submit(false);
})();
