"""Durable homework lists, conservative page splitting, and daily summaries."""
import hashlib
import io
import json
import re
import tempfile
import threading
import uuid
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import db
import ocr
from review_quality import safe_analysis


class Region(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    box: list[int] = Field(min_length=4, max_length=4)

    @model_validator(mode='after')
    def valid_box(self):
        left, top, right, bottom = self.box
        if not (0 <= left < right <= 1000 and 0 <= top < bottom <= 1000):
            raise ValueError('配图范围需为0～1000内有效矩形')
        return self


class Item(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=2000)
    answer: str = Field(default='', max_length=2000)
    status: str = Field(default='todo', max_length=20)
    reflection: str = Field(default='', max_length=2000)
    reflectionDirty: bool = False
    in_notes: bool = False
    in_mistakes: bool = False
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    source_regions: list[Region] = Field(default_factory=list, max_length=4)
    visual_summary: str = Field(default='',max_length=1200)
    visual_suggestion: str = Field(default='',max_length=2000)


class Draft(BaseModel):
    title: str = Field(default='', max_length=60)
    date: str = Field(default='', max_length=10)
    batch: str = Field(default='', max_length=30000)
    items: list[Item] = Field(default_factory=list, max_length=100)
    imported_source_ids: list[str] = Field(default_factory=list, max_length=10)


class Assignment(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    revision: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=60)
    date: date
    items: list[Item] = Field(default_factory=list, max_length=100)
    active: str | None = Field(default=None, max_length=100)
    draft: Draft | None = None
    source_ids: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('items')
    @classmethod
    def published_items(cls, items):
        if any(not item.text for item in items):
            raise ValueError('发布的题目不能为空')
        if len({item.id for item in items}) != len(items):
            raise ValueError('题目编号重复')
        return items


def _snapshot(conn, row):
    data = json.loads(row['payload'])
    data.update(id=row['id'], revision=row['revision'], title=row['title'], date=row['assignment_date'])
    for item in (data.get('draft') or {}).get('items',[]):
        if item.get('source_ids') and not item.get('source_regions'):
            item['source_regions']=regions(item)
    for item in data['items']:
        if item.get('source_ids') and not item.get('source_regions'):
            item['source_regions'] = regions(item)
        session = conn.execute('SELECT session_id FROM homework_tutor_link WHERE item_id=? AND question=?',
                               (item['id'], item['text'])).fetchone()
        item['tutor_session_id'] = session['session_id'] if session else None
        item['status'] = 'skipped' if item.get('status') == 'skipped' else 'todo'
        record = conn.execute('SELECT * FROM homework_review WHERE item_id=? AND question=? AND answer=? '
                              'AND attachment_key=? '
                              'ORDER BY created_at DESC,rowid DESC LIMIT 1',
                              (item['id'], item['text'], item['answer'], attachment_key(item))).fetchone()
        if record:
            item.update(analysis=safe_analysis(json.loads(record['analysis'])), review_id=record['id'])
            item['status'] = {'correct':'done', 'incorrect':'revision', 'uncertain':'uncertain'}[item['analysis']['verdict']]
            if not item.get('reflectionDirty'):
                item.update(reflection=record['reflection'], in_notes=bool(record['in_notes']), in_mistakes=bool(record['in_mistakes']))
    data['sources'] = [source_info(conn, sid) for sid in data.get('source_ids', [])]
    return data


def get(assignment_id):
    with db._conn() as conn:
        row = conn.execute('SELECT * FROM homework_assignment WHERE id=?', (assignment_id,)).fetchone()
        if not row:
            raise LookupError('作业清单不存在')
        return _snapshot(conn, row)


def verify_item(item_id, question):
    with db._conn() as conn:
        owner = conn.execute('SELECT assignment_id FROM homework_item_owner WHERE item_id=?', (item_id,)).fetchone()
        row = conn.execute('SELECT payload FROM homework_assignment WHERE id=?', (owner['assignment_id'],)).fetchone() if owner else None
        if not row or not any(item['id'] == item_id and item['text'] == question for item in json.loads(row['payload'])['items']):
            raise ValueError('作业题目已更新，请载入最新清单后再开始辅导')


def item_assignment(item_id):
    with db._conn() as conn:
        row = conn.execute('SELECT assignment_id FROM homework_item_owner WHERE item_id=?', (item_id,)).fetchone()
        if not row:
            raise LookupError('这道作业题目不存在')
    return get(row['assignment_id'])


def link_session(item_id, question, session_id):
    with db._conn() as conn:
        conn.execute('INSERT INTO homework_tutor_link(item_id,question,session_id) VALUES (?,?,?) '
                     'ON CONFLICT(item_id) DO UPDATE SET question=excluded.question,session_id=excluded.session_id',
                     (item_id, question, session_id))


def save(assignment_id, payload):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', assignment_id):
        raise ValueError('作业编号无效')
    data = payload.model_dump(mode='json')
    with db._conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM homework_assignment WHERE id=?', (assignment_id,)).fetchone()
        if (row['revision'] if row else 0) != payload.revision:
            if row and json.loads(row['payload']) == data:
                return _snapshot(conn, row)  # A saved request may have lost its response during navigation.
            raise RuntimeError('另一台设备已经更新这份作业。请载入最新版本，再继续编辑。')
        all_items = data['items'] + (data['draft']['items'] if data['draft'] else [])
        source_ids = list(data['source_ids'])
        for item in all_items:
            source_ids.extend(item['source_ids'])
            source_ids.extend(region['source_id'] for region in item['source_regions'])
            owner = conn.execute('SELECT assignment_id FROM homework_item_owner WHERE item_id=?', (item['id'],)).fetchone()
            if owner and owner['assignment_id'] != assignment_id:
                raise ValueError('题目已属于另一份作业，请使用新的题目编号')
            conn.execute('INSERT OR IGNORE INTO homework_item_owner VALUES (?,?)', (item['id'], assignment_id))
        source_ids = list(dict.fromkeys(source_ids))
        for sid in source_ids:
            source_info(conn, sid)
        if len(source_ids) > 10:
            raise ValueError('一份作业最多保存 10 张来源照片')
        data['source_ids'] = source_ids
        conn.execute('INSERT INTO homework_assignment(id,revision,title,assignment_date,payload) VALUES (?,?,?,?,?) '
                     'ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,title=excluded.title,'
                     'assignment_date=excluded.assignment_date,payload=excluded.payload,'
                     "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')",
                     (assignment_id, payload.revision + 1, payload.title, data['date'], json.dumps(data, ensure_ascii=False)))
        return _snapshot(conn, conn.execute('SELECT * FROM homework_assignment WHERE id=?', (assignment_id,)).fetchone())


def listing(day=None):
    with db._conn() as conn:
        rows = conn.execute('SELECT * FROM homework_assignment' + (' WHERE assignment_date=?' if day else '') +
                            ' ORDER BY assignment_date DESC, updated_at DESC LIMIT 100', (day,) if day else ()).fetchall()
        result = []
        for row in rows:
            data = _snapshot(conn, row)
            items = data['items']
            result.append(dict(id=row['id'], date=data['date'], title=data['title'], revision=row['revision'],
                               total=len(items), done=sum(item['status']=='done' for item in items),
                               draft=not items, updated_at=row['updated_at']))
        return result


def summary(day):
    with db._conn() as conn:
        rows = conn.execute('SELECT * FROM homework_assignment WHERE assignment_date=?', (day,)).fetchall()
        items = [item for row in rows for item in _snapshot(conn, row)['items']]
        analyzed = [item for item in items if item.get('analysis')]
        topics = sorted({item['analysis']['knowledge_point'] for item in analyzed if item['status'] in ('revision','uncertain')})
        # Reflections and collections count saved records, never unsaved client checkboxes.
        ids = [item['review_id'] for item in analyzed]
        saved = [conn.execute('SELECT reflection,in_notes,in_mistakes FROM homework_review WHERE id=?', (rid,)).fetchone() for rid in ids]
        return dict(date=day, assignments=len(rows), total=len(items), analyzed=len(analyzed),
                    passed=sum(item['status']=='done' for item in items),
                    revision=sum(item['status']=='revision' for item in items),
                    uncertain=sum(item['status']=='uncertain' for item in items),
                    remaining=len(items)-len(analyzed), reflections=sum(bool(row['reflection']) for row in saved),
                    notes=sum(row['in_notes'] for row in saved), mistakes=sum(row['in_mistakes'] for row in saved),
                    topics=topics, pending=[dict(text=item['text'], status=item['status']) for item in items if item['status']!='done'])


def source_info(conn, sid):
    row = conn.execute('SELECT id,name,width,height,result,error FROM homework_source WHERE id=?', (sid,)).fetchone()
    if not row:
        raise LookupError('来源照片不存在，请重新上传')
    result = dict(row)
    result['result'] = json.loads(result['result']) if result['result'] else None
    result['url'] = '/api/homework/sources/' + sid + '/image'
    return result


def upload(content, name):
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in ('JPEG','PNG','BMP') or image.width * image.height > 20_000_000:
                raise ValueError('请选择不超过 2000 万像素的 JPG、PNG 或 BMP 图片')
            image = ImageOps.exif_transpose(image).convert('RGB')
            stream = io.BytesIO()
            image.save(stream, format='PNG')
            pixels = stream.getvalue()
            width, height = image.size
    except Exception as exc:
        raise ValueError('图片无法读取，请使用清晰的 JPG、PNG 或 BMP 照片（不超过2000万像素）') from exc
    if len(pixels) > 20 * 1024 * 1024:
        raise ValueError('图片展开后过大，请降低分辨率后上传')
    digest = hashlib.sha256(pixels).hexdigest()
    with db._conn() as conn:
        conn.execute('INSERT OR IGNORE INTO homework_source(id,digest,name,image,width,height) VALUES (?,?,?,?,?,?)',
                     (uuid.uuid4().hex, digest, name[:200], pixels, width, height))
        sid = conn.execute('SELECT id FROM homework_source WHERE digest=?', (digest,)).fetchone()['id']
        return source_info(conn, sid)


def image_bytes(sid):
    with db._conn() as conn:
        row = conn.execute('SELECT image FROM homework_source WHERE id=?', (sid,)).fetchone()
        if not row:
            raise LookupError('来源照片不存在')
        return row['image']


def regions(item):
    if item.get('source_regions'):
        return item['source_regions']
    result=[]
    for sid in item.get('source_ids',[])[:4]:
        with db._conn() as conn:
            source=source_info(conn,sid)
        old=source.get('result') or {}
        matches=[index for index,question in enumerate(old.get('questions',[])) if question.get('text')==item.get('text')]
        if len(matches)==1 and old.get('lines'):
            cropped=split_page(old['lines'],source['width'],source['height'],sid)
            if matches[0]<len(cropped):
                result.extend(cropped[matches[0]]['source_regions'])
                continue
        result.append(dict(source_id=sid,box=[0,0,1000,1000]))
    return result


def attachment_key(item):
    attachments = regions(item)
    return hashlib.sha256(json.dumps(attachments, sort_keys=True).encode()).hexdigest() if attachments else ''


def region_url(region):
    return '/api/homework/sources/' + region['source_id'] + '/image?box=' + ','.join(map(str,region['box']))


def crop_image(sid, box):
    region = Region(source_id=sid,box=box)
    with Image.open(io.BytesIO(image_bytes(sid))) as image:
        left,top,right,bottom = region.box
        image = image.crop((int(left*image.width/1000),int(top*image.height/1000),
                            max(int(right*image.width/1000),int(left*image.width/1000)+1),
                            max(int(bottom*image.height/1000),int(top*image.height/1000)+1)))
        stream=io.BytesIO()
        image.save(stream,format='PNG')
        return stream.getvalue()


def item_context(item_id):
    assignment = item_assignment(item_id)
    item = next((row for row in assignment['items'] if row['id']==item_id), None)
    if not item:
        raise LookupError('这道题已移出作业清单')
    return item


def image_context(item):
    attachments = [{**region,'url':region_url(region)} for region in regions(item)]
    return dict(key=attachment_key(item), attachments=attachments,
                images=[crop_image(region['source_id'], region['box']) for region in regions(item)])


_ocr_lock = threading.Lock()
NUMBERED = re.compile(r'^\s*(?:第\s*\d+\s*题[：:.、]?|\d+[、．.](?!\d)|\d+[)）])\s*')


def split_page(lines, width=None, height=None, source_id=None):
    groups, preamble, previous_number, section_tops = [], [], None, []
    for line in lines:
        marker = NUMBERED.match(line['text'])
        # OCR often removes the space in "3. 24颗糖". A consecutive number is
        # a useful boundary, but flag it for correction because decimals can look identical.
        compact = re.match(r'^\s*(\d+)[.．](\d)', line['text'])
        inferred = not marker and compact and previous_number is not None and int(compact[1]) == previous_number + 1
        if marker or inferred:
            number = re.match(r'^\s*(?:第\s*)?(\d+)', line['text'])
            previous_number = int(number[1]) if number else None
            groups.append([{**line, 'inferred_boundary': bool(inferred)}])
        elif re.match(r'^[一二三四五六七八九十]+[、.．]\s*(?:选择|填空|判断|计算|解答|应用)', line['text']):
            section_tops.append(min(point[1] for point in line['box']))
            continue
        elif groups:
            groups[-1].append(line)
        else:
            preamble.append(line)
    if not groups:
        groups, preamble = [preamble] if preamble else [], []
    if width and height:
        # Page titles are not shared mathematical conditions. Keep actual shared givens.
        preamble = [line for line in preamble if not re.search(r'学年|学期|作业|选择题|填空题', line['text'])]
    questions = [dict(text='\n'.join(line['text'] for line in preamble + group),
                 boxes=[line['box'] for line in preamble + group],
                 low_confidence=any(line['confidence'] < .85 or line.get('inferred_boundary') for line in preamble + group)) for group in groups]
    if width and height and source_id:
        for index,(question,group) in enumerate(zip(questions,groups)):
            top = max(0, min(point[1] for point in group[0]['box']) - 5)
            bottom = min(point[1] for point in groups[index+1][0]['box']) - 5 if index+1<len(groups) else height
            bottom=min([bottom]+[value-3 for value in section_tops if top<value<bottom])
            question['source_regions'] = [dict(source_id=source_id,box=[0,int(top*1000/height),1000,min(1000,int(bottom*1000/height))])]
            question['image_url'] = region_url(question['source_regions'][0])
    return questions


def recognize_source(sid):
    if not _ocr_lock.acquire(blocking=False):
        raise RuntimeError('正在识别另一张照片，请稍后重试这张')
    try:
        with db._conn() as conn:
            info = source_info(conn, sid)
        if info['result'] and info['result'].get('version') == 2:
            return info
        content = image_bytes(sid)
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as file:
                file.write(content)
                path = Path(file.name)
            lines = ocr.recognize_layout(str(path))
            if not lines:
                region=dict(source_id=sid,box=[0,0,1000,1000])
                result=dict(version=2,lines=[],questions=[dict(text='请根据配图作答（题干待看图转录）',boxes=[],low_confidence=True,source_regions=[region],image_url=region_url(region))],
                            warning='未识别到文字，已保留整张配图。可先加入清单，再点击“看图转录题干”或手动补充。')
            else:
                result = dict(version=2, lines=lines, questions=split_page(lines,info['width'],info['height'],sid),
                          warning='每题截图保留题干、选项和配图。文字是OCR辅助结果，请对照截图校对；范围不完整时可调整配图。')
            error = ''
        except Exception as exc:
            result = None
            error = str(exc) if isinstance(exc, ocr.OCRError) else '识别未完成，请重试或手动输入'
        finally:
            if path:
                path.unlink(missing_ok=True)
        with db._conn() as conn:
            conn.execute('UPDATE homework_source SET result=?,error=? WHERE id=?',
                         (json.dumps(result, ensure_ascii=False) if result else None, error, sid))
            return source_info(conn, sid)
    finally:
        _ocr_lock.release()
