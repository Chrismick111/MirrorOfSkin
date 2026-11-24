"""Discover chapter cards from downloaded chapter text and exact local art names."""
import json
import os
import pathlib
import re
import time

# Verified game chapter ids and illustration filenames for named interludes.
INTERLUDES = {
    '9103': ('interlude_3_5', 'hells-chicken.png'),
    '9104': ('interlude_4_5', 'chapter-umida.png'),
    '9105': ('interlude_5_5_wonder', 'chapter5.5_miracle.png'),
    '9107': ('interlude_5_5_ycgd', 'chapter5.5_ycgd.png'),
    '9109': ('interlude_6_5_tkt', 'chapter6.5_tkt.png'),
    '9110': ('interlude_6_5_mowe', 'chapter6.5_mowe.png'),
    '9114': ('interlude_7_5_checkup', 'chapter7.5_LCBCheckUp.png'),
    '9116': ('interlude_7_5_cleanup', 'chapter7.5_NightSweep.png'),
    '9119': ('interlude_8_5_cultivation', 'chapter8.5_Cultivation.png'),
    '9120': ('interlude_8_5_pilgrimage', 'Canto_Pilgrimage.png'),
    '9125': ('interlude_9_5_twth', 'chapter9.5_TwiningThreads.png'),
    '9127': ('interlude_9_5_exme', 'chapter9.5_RecordMemory.png'),
}
INTERLUDE_TITLES = {
    'interlude_3_5':'地狱鸡', 'interlude_4_5':'去·海·边',
    'interlude_5_5_wonder':'20区的奇迹', 'interlude_5_5_ycgd':'肉斩骨断',
    'interlude_6_5_tkt':'时间杀人时间', 'interlude_6_5_mowe':'WARP快车谋杀案',
    'interlude_7_5_checkup':'LCB定期体检', 'interlude_7_5_cleanup':'深夜清扫',
    'interlude_8_5_cultivation':'切磋琢春', 'interlude_8_5_pilgrimage':'善意的巡礼',
    'interlude_9_5_twth':'绞丝结线', 'interlude_9_5_exme':'经验记忆',
}


def read(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return {}
    return value if isinstance(value, dict) else {}


def save(path, data):
    if path.is_file() and read(path) == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.%d.tmp' % os.getpid())
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(6):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.02 * (attempt + 1))


def main_key(number):
    return 'chapter_%d' % number if number else 'prologue'


def detect(game, image_names, errors):
    cards = {}
    images = {name.casefold(): name for name in image_names}
    for key, asset in INTERLUDES.values():
        if asset.casefold() in images:
            label = INTERLUDE_TITLES[key]
            cards[key] = dict(chapter='间章', title=label, rank=20000, asset=asset)
    if 'banner_dawn_en.png' in images:
        cards['walpurgis_10'] = dict(chapter='第10次', title='瓦尔普吉斯之夜', rank=1050,
                                     asset='banner_Dawn_en.png')
    # Numeric filenames identify a chapter even without a language pack.
    for name in image_names:
        match = re.fullmatch(r'chapter(\d+)\.png', name, re.I)
        if match:
            n = int(match[1])
            label = '第%d章' % n if n else '序章'
            cards[main_key(n)] = dict(chapter=label, title=label, rank=n*100, asset=name)
    if not game:
        return cards
    lang = pathlib.Path(game) / 'LimbusCompany_Data/Lang'
    folders = sorted(lang.glob('*/StageChapterText*.json'),
                     key=lambda p: (p.parent.name != 'LLC_zh-CN', p.name != 'StageChapterText.json', str(p)))
    localized = set()
    unmatched_by_number = {}
    for path in folders:
        try:
            rows = read(path).get('dataList', [])
            for row in rows:
                if not isinstance(row, dict):
                    continue
                number = str(row.get('chapterNumber') or '').strip()
                match = re.fullmatch(r'chapter_\w+_(\d+)', str(row.get('id') or ''))
                if not match:
                    continue
                title = str(row.get('chaptertitle') or '').strip()
                event = re.fullmatch(r'第\s*(\d+)\s*次\s*瓦尔普吉斯之夜', title)
                if event:
                    key = 'walpurgis_' + event[1]
                    asset = 'stage-node-id_910603.png' if event[1] == '2' else None
                    cards.setdefault(key, dict(chapter='第%s次' % event[1], title='瓦尔普吉斯之夜',
                                              timeline=str(row.get('timeline') or ''), rank=20000, asset=asset))
                    continue
                if not re.fullmatch(r'\d+(?:\.\d+)?', number):
                    continue
                if number.isdigit():
                    n = int(number)
                    key, asset = main_key(n), 'chapter%d.png' % n
                else:
                    key, asset = INTERLUDES.get(match[1], ('interlude_id_' + match[1], None))
                    if not asset:
                        asset = images.get((row['id']+'.png').casefold())
                if key in localized:
                    continue
                label = str(row.get('chapter') or number)
                if not title:
                    continue
                cards[key] = dict(chapter=label, title=title, timeline=str(row.get('timeline') or ''),
                                  rank=round(float(number)*100), asset=asset)
                if not asset:
                    unmatched_by_number.setdefault(number, []).append(key)
                localized.add(key)
        except (ValueError, OSError) as exc:
            errors.append({'file': path.name, 'error': str(exc)[:200]})
    # Some interlude illustrations have a chapter number and an internal English
    # name. Link by number only when exactly one chapter and one cover remain.
    claimed = {row['asset'].casefold() for row in cards.values() if row.get('asset')}
    for number, keys in unmatched_by_number.items():
        pattern = r'chapter' + re.escape(number) + r'(?:_[^/]+)?\.png'
        choices = [name for name in images if name not in claimed and
                   re.fullmatch(pattern, name, re.I) and not re.search(r'_before(?:_|\.)', name)]
        if len(keys) == 1 and len(choices) == 1:
            cards[keys[0]]['asset'] = images[choices[0]]
    return cards
