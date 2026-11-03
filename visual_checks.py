"""Conservative pixel/geometry checks for well-identified elementary diagrams.

These checks return no answer when segmentation or the geometry is ambiguous.
They do not contain worksheet IDs, image coordinates, or expected option letters.
"""
import io
from pathlib import Path
import re
import tempfile
import unicodedata

import cv2
import numpy as np
from PIL import Image

import ocr


def layout(image):
    path=None
    try:
        with tempfile.NamedTemporaryFile(suffix='.png',delete=False) as file:
            file.write(image);path=Path(file.name)
        return ocr.recognize_layout(str(path))
    finally:
        if path:path.unlink(missing_ok=True)


def _bounds(line):
    points=line['box']
    return min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)


def option_labels(lines):
    result={}
    for line in lines:
        match=re.match(r'^\s*([A-D])\s*[.．、:：\s]',line['text'],re.I)
        if match:
            letter=match[1].upper()
            if letter in result:return {}
            result[letter]=line
    return result if len(result)==4 else {}


def _figure_band(lines,labels,width):
    option_top=float(np.median([_bounds(line)[1] for line in labels.values()]))
    candidates=[_bounds(line)[3] for line in lines if _bounds(line)[2]-_bounds(line)[0]>.4*width and _bounds(line)[1]<option_top-3]
    return max(candidates)+1 if candidates else None


def _iou(a,b):
    a=cv2.resize(a.astype('uint8'),(64,64),interpolation=cv2.INTER_NEAREST)>0
    b=cv2.resize(b.astype('uint8'),(64,64),interpolation=cv2.INTER_NEAREST)>0
    return float((a&b).sum()/max(1,(a|b).sum()))


def _variants(mask):
    for k in range(4):
        rotated=np.rot90(mask,k)
        yield rotated
        yield np.fliplr(rotated)


def reflection_options(question,image,lines=None):
    """Check separated, congruent halves by reflecting actual component silhouettes."""
    if not ('轴对称' in question and '一半' in question and re.search(r'补全.{0,8}另一半',question) and '不可能' in question):
        return None
    lines=layout(image) if lines is None else lines
    labels=option_labels(lines)
    if not labels:return None
    gray=np.array(Image.open(io.BytesIO(image)).convert('L'))
    height,width=gray.shape
    top=_figure_band(lines,labels,width)
    if top is None:return None
    ordered=sorted(labels.items(),key=lambda pair:_bounds(pair[1])[0])
    font_height=float(np.median([_bounds(line)[3]-_bounds(line)[1] for line in labels.values()]))
    all_glyphs=[];evidence=[]
    for index,(letter,line) in enumerate(ordered):
        left,y,right,bottom=_bounds(line)
        left=int(left+font_height*.85)
        right=int(_bounds(ordered[index+1][1])[0]-4) if index+1<len(ordered) else width
        bottom=min(height,int(max(_bounds(row)[3] for row in labels.values())+2))
        if right<=left or bottom<=top:return None
        mask=(gray[int(top):bottom,left:right]<128).astype('uint8')
        n,components,stats,centers=cv2.connectedComponentsWithStats(mask,8)
        ids=sorted([i for i in range(1,n) if stats[i,4]>=max(5,(font_height*.13)**2)],key=lambda i:stats[i,4],reverse=True)
        if len(ids)<2 or sum(stats[i,4] for i in ids[2:])>.08*sum(stats[i,4] for i in ids[:2]):return None
        ids=ids[:2];glyphs=[]
        for component in ids:
            x,y,w,h,_=stats[component]
            if min(w,h)<3:return None
            glyphs.append((components[y:y+h,x:x+w]==component).astype('uint8'))
        a,b=glyphs;dx,dy=centers[ids[1]]-centers[ids[0]]
        # Reflection preserves size; resizing below only tolerates raster/font variation.
        if not .8<=max(a.shape)/max(b.shape)<=1.25 or not .7<=float(a.sum())/max(1,float(b.sum()))<=1.43:return None
        if abs(dy)<.3*abs(dx):
            reflected=np.fliplr(a);axis='两半之间的竖直线'
        elif abs(dx)<.3*abs(dy):
            reflected=np.flipud(a);axis='两半之间的水平线'
        elif abs(abs(dx)-abs(dy))<.3*max(abs(dx),abs(dy)):
            reflected=a.T if dx*dy<0 else np.flipud(np.fliplr(a.T))
            axis='从左上到右下的斜线' if dx*dy<0 else '从左下到右上的斜线'
        else:return None
        score=_iou(reflected,b)
        if score>=.84:
            possible=True;reason=f'沿{axis}翻折，一半能与另一半重合。'
        elif score<=.7:
            possible=False;reason=f'沿{axis}翻折后，朝向与另一半不一致，不能重合。'
        else:return None
        evidence.append(dict(label=letter,possible=possible,axis=axis,reason=reason,match_score=round(score,4)))
        all_glyphs.extend(glyphs)
    # Every option must consist of the same primitive half, up to rigid orientation.
    reference=all_glyphs[0]
    if any(max(_iou(variant,glyph) for variant in _variants(reference))<.82 for glyph in all_glyphs[1:]):return None
    impossible=[row['label'] for row in evidence if not row['possible']]
    if len(impossible)!=1:return None
    answer=impossible[0]
    return dict(kind='reflection_completion',readable=True,answer=answer,options=evidence,
                explanation='题目给的是一个完整的半边，要检查能否翻折补出另一半。\n'+
                            '\n'.join(f"{row['label']}：{row['reason']}" for row in evidence)+f'\n因此，不可能的一项是{answer}。')


def grid_quality(question,image,lines=None):
    """Reject a shading count when the stated shaded cells cannot be distinguished."""
    if not ('方格' in question and '涂色' in question):return None
    size=re.search(r'([2-9])\s*[xX×*]\s*([2-9])',unicodedata.normalize('NFKC',question))
    count=re.search(r'已[^。；]{0,50}?([一二三四五六七八九十\d]+)个小正方形涂色',question)
    if not size or not count:return None
    numbers={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
    expected=int(count[1]) if count[1].isdigit() else numbers.get(count[1])
    if not expected:return None
    rows,cols=map(int,size.groups())
    lines=layout(image) if lines is None else lines
    labels=option_labels(lines)
    if not labels:return None
    gray=np.array(Image.open(io.BytesIO(image)).convert('L'));height,width=gray.shape
    top=_figure_band(lines,labels,width)
    bottom=int(min(_bounds(line)[1] for line in labels.values())-3)
    if top is None or bottom<=top:return None
    band=gray[int(top):bottom]
    ys,xs=np.where(band<160)
    if not len(xs):return _unclear_grid(rows,cols,expected)
    x0,x1,y0,y1=int(xs.min()),int(xs.max()+1),int(ys.min()),int(ys.max()+1)
    if min(x1-x0,y1-y0)<20 or abs((x1-x0)/(y1-y0)-cols/rows)>.2:return None
    values=[]
    for r in range(rows):
        for c in range(cols):
            left=x0+(c+.23)*(x1-x0)/cols;right=x0+(c+.77)*(x1-x0)/cols
            upper=y0+(r+.23)*(y1-y0)/rows;lower=y0+(r+.77)*(y1-y0)/rows
            values.append(float(np.median(band[int(upper):int(lower),int(left):int(right)])))
    ordered=sorted(values)
    if expected>=len(values) or ordered[expected]-ordered[expected-1]<18:
        return _unclear_grid(rows,cols,expected)
    # Recognizable shading is left to the general solver until exact grid enumeration is available.
    return None


def _unclear_grid(rows,cols,expected):
    return dict(kind='unreadable_shading',readable=False,answer=None,options=[],
                explanation=f'我能看到{rows}×{cols}网格，但当前图片里无法可靠区分题目所说的{expected}个涂色格，暂时不能判定选项。请补拍涂色区域，或说明这些格子分别在第几行、第几列。')


def check(question,images):
    if len(images)!=1:return None
    if '轴对称' not in question:return None
    try:
        lines=layout(images[0])
        return reflection_options(question,images[0],lines) or grid_quality(question,images[0],lines)
    except Exception:
        return None
