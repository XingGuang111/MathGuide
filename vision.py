"""Local multimodal inference. Images stay on the configured local Ollama service."""
import io
import json
import time

import ollama
from PIL import Image

import config
import llm


_client = ollama.Client(timeout=config.VISION_TIMEOUT_SECONDS)
_capabilities = {'time': 0, 'model': None, 'ready': False}


def status():
    model = config.VISION_MODEL_NAME
    if _capabilities['model'] == model and time.monotonic()-_capabilities['time'] < 30:
        return dict(ok=_capabilities['ready'], model=model)
    try:
        ready = 'vision' in _client.show(model)['capabilities']
    except Exception:
        ready = False
    _capabilities.update(time=time.monotonic(), model=model, ready=ready)
    return dict(ok=ready, model=model)


def _prepare(image):
    # Small worksheet crops need sufficient rendering resolution; never invent detail.
    with Image.open(io.BytesIO(image)) as opened:
        opened = opened.convert('RGB')
        scale = min(3, 1200 / max(opened.size))
        if scale != 1:
            opened = opened.resize((max(1,round(opened.width*scale)), max(1,round(opened.height*scale))), Image.Resampling.LANCZOS)
        stream = io.BytesIO()
        opened.save(stream, format='PNG')
        return stream.getvalue()


def json_reply(system, payload, images, schema, history=None, tokens=1600):
    if not images:
        raise llm.LLMError('这道题还没有关联配图，请先检查题目截图。')
    if not status()['ok']:
        raise llm.LLMError(f'本地看图模型未就绪，请先运行 ollama pull {config.VISION_MODEL_NAME}。题目与作答已保留。')
    messages = [{'role':'system','content':system}]
    messages.extend(history or [])
    messages.append({'role':'user', 'content':json.dumps(payload,ensure_ascii=False), 'images':[_prepare(item) for item in images[:4]]})
    try:
        response = _client.chat(model=config.VISION_MODEL_NAME, messages=messages, format=schema,
                                options={'temperature':0,'num_predict':tokens,'num_ctx':8192})
        data = json.loads(response['message']['content'])
        if not isinstance(data,dict):
            raise ValueError('不是对象')
        return data
    except Exception as exc:
        raise llm.LLMError('看图分析未完成，请稍后重试。题目配图与作答已保留。') from exc
