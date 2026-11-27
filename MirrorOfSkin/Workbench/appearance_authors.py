"""Read explicit author credits from the selected appearance and its package."""
from collections import defaultdict
from ipaddress import IPv6Address
import json
from pathlib import PurePosixPath
import re
import stat
from unicodedata import category
from urllib.parse import urlsplit
from zipfile import BadZipFile


MAX_METADATA = 1024 * 1024
_DOC_NAMES = {'manifest', 'package', 'pack', 'mod', 'modinfo', 'mod_info', 'metadata', 'info', 'mos-skin',
              'mirrorofskin-migration', 'readme', 'read me', 'credits', 'credit', 'author', 'authors',
              '说明', '作者', '作者说明', '著者'}
_EXTENSIONS = {'.json', '.md', '.markdown', '.txt', '.yaml', '.yml', '.toml', '.ini'}
_LINK_DOCUMENTS = {'links', 'link', 'video', 'videos', 'showcase', 'homepage', 'release',
                   '链接', '相关链接', '模组链接', '视频', '演示视频', '实机演示', '发布页', '发布链接',
                   '项目主页', '作者主页', '作者页', '下载链接'}
_AUTHOR_NAMES = r'original authors?|mod authors?|authors?|mod creators?|creators?|原作者|作者|模组作者|製作者|제작자|著者'
_AUTHOR_LINE = re.compile(r'^\s*(?:>\s*)?(?:[-*+]\s+)?(?:#{1,6}\s+)?(?:\||\s*)'
                          r'\s*[*_]*(?:' + _AUTHOR_NAMES + r')[*_]*\s*(?:[：:=]|\|)[*_]*\s*(.+)$', re.I)
_PACKAGE_MARKERS = {'assets', 'custom_appearance', 'custom_bundles', 'installation'}
_AUTHOR_PLACEHOLDERS = {'unknown', 'none', 'null', 'n/a', 'tbd', 'your name', '未填写', '未知', '无', '佚名'}
_LINK_LABELS = {
    '演示视频': ('video', 'videos', 'videourl', 'demovideo', 'demourl', 'showcase', 'trailer',
                'bilibili', 'youtube', 'vimeo', 'b站', '视频', '演示视频'),
    '发布页': ('release', 'releases', 'releaseurl', 'releasepage', 'publication', '发布页', '发布链接'),
    '项目主页': ('homepage', 'website', 'site', 'project', 'projecturl', 'modpage', '主页', '项目主页', '官网'),
    '项目仓库': ('repository', 'repo', 'repositoryurl', 'source', 'sourceurl', 'github', 'gitlab', '源码', '仓库'),
    '作者主页': ('authorurl', 'authorpage', 'profile', 'profileurl', '作者主页', '作者页'),
    '下载': ('download', 'downloads', 'downloadurl', 'mirror', 'mirrors', '下载', '下载链接'),
    '相关链接': ('url', 'urls', 'link', 'links', 'href', '链接', '相关链接'),
}
_LINK_FIELDS = {key: label for label, keys in _LINK_LABELS.items() for key in keys}
LINK_METADATA_FIELDS = set(_LINK_FIELDS) | {'video_url', 'videoUrl', 'release_url', 'releaseUrl', 'author_url',
                                          'authorUrl', 'project_url', 'projectUrl', 'repository_url',
                                          'repositoryUrl', 'download_url', 'downloadUrl'}
_LINK_CONTEXT = (
    ('演示视频', r'视频|演示|预告|\b(?:video|trailer|showcase|gameplay)\b'),
    ('项目仓库', r'仓库|源码|\b(?:repo(?:sitory)?|github|gitlab|source code)\b'),
    ('发布页', r'发布页|发布链接|\breleases?\b'),
    ('作者主页', r'作者(?:页|主页|空间)|\bauthor(?:\s+[\w-]+)?\s+(?:page|profile|website)\b'),
    ('项目主页', r'(?:项目|模组|外观|MOD)(?:页面|网页|主页|链接)|官网|\b(?:home\s?page|official\s+site|project\s+(?:site|page)|mod\s+page)\b'),
    ('下载', r'网盘|分流|下载镜像|模组下载|外观下载|\b(?:mod\s+download|download\s+mirror)\b'),
)
_EXTERNAL = re.compile(r'依赖|致谢|感谢|第三方|版权|许可|免责|原作|参考资料|'
                       r'\b(?:dependenc(?:y|ies)|prerequisites?|credits?|thanks|third.party|copyright|'
                       r'licenses?|disclaimer|asset sources?)\b', re.I)
_MD_DESTINATION = r'(?:<(https?://[^\s<>]+)>|(https?://[^\s<>)]+))'
_MD_TITLE = r'(?:\s+["\'][^\n]{0,256}?["\'])?'
_MARKDOWN_LINK = re.compile(
    r'(!?)\[([^\[\]\n]{1,256})\](?:\(\s*' + _MD_DESTINATION + _MD_TITLE
    + r'\s*\)|\[([^\[\]\n]{0,256})\])?|<(https?://[^\s<>]+)>', re.I)
_MARKDOWN_REFERENCE = re.compile(r'^\s{0,3}\[([^\[\]\n]{1,256})\]:\s*'
                                 + _MD_DESTINATION + _MD_TITLE + r'\s*$', re.I)
_PLAIN_URL = re.compile(r'https?://[^\s<>()`\[\]{}"\'，。；）【】]+', re.I)
_HEADING = re.compile(r'^(#{1,6})\s+(.+)')
_MAX_LINKS = 12


def metadata_member(path):
    name, extension = path.stem.casefold(), path.suffix.casefold()
    return (_readme_rank(path) is not None or name in _DOC_NAMES and extension in _EXTENSIONS | {''}
            or name in _LINK_DOCUMENTS and extension in _EXTENSIONS | {'', '.url'})


def _readme_rank(path):
    extension = path.suffix.casefold()
    if extension not in {'', '.md', '.markdown', '.txt'}:
        return None
    stem = path.stem.casefold()
    markdown = extension in {'.md', '.markdown'}
    if stem in {'readme', 'read me'}:
        return 0 if markdown else 2
    if re.fullmatch(r'read ?me[._-][a-z]{2,3}(?:[_-][a-z]{2,8})?', stem):
        return 1 if markdown else 3
    if stem == '说明':
        return 3
    return None


def _path(value):
    return PurePosixPath(str(value).replace('\\', '/'))


def _parts(path):
    return tuple(part.casefold() for part in path.parts)


def _package_root(member):
    parts = _parts(member)
    for index, part in enumerate(parts[:-1]):
        if part in _PACKAGE_MARKERS:
            return parts[:index]
    return parts[:-1]


def _clean_name(value):
    if not isinstance(value, str):
        return ''
    value = value.strip().strip('`*_\"\'').strip()
    value = re.sub(r'^\[([^\]]+)\]\(https?://[^)]+\)$', r'\1', value).strip()
    if (not 0 < len(value) <= 128 or value.casefold() in _AUTHOR_PLACEHOLDERS or
            re.search(r'https?://|[<>|]', value, re.I) or not any(ch.isalnum() for ch in value)
            or any(category(ch).startswith('C') for ch in value)):
        return ''
    return ' '.join(value.split())


def _names(value):
    values = value if isinstance(value, list) else [value]
    result = {}
    for item in values[:32]:
        if isinstance(item, dict):
            item = item.get('name')
        if isinstance(item, str):
            for part in re.split(r'[,，、;；]|\s+(?:&|and)\s+', item, flags=re.I):
                name = _clean_name(part)
                if name:
                    result.setdefault(name.casefold(), name)
    return list(result.values())


def _fields(data):
    if not isinstance(data, dict):
        return []
    return _names(data.get('authors')) or _names(data.get('author'))


def _json_names(data):
    return (_fields(data.get('meta')) or _fields(data.get('metadata')) or _fields(data)
            if isinstance(data, dict) else [])


def _prefab_data(data, address):
    appearances = data.get('appearances') if isinstance(data, dict) else None
    if isinstance(appearances, dict):
        return next((policy for key, policy in appearances.items() if key.casefold() == address), None)
    return None


def _prose_lines(text):
    fence = ''
    for line in text.splitlines():
        stripped = line.lstrip(' >')
        if stripped.startswith(('```', '~~~')):
            mark = stripped[:3]
            fence = '' if fence == mark else fence or mark
            continue
        if not fence and len(line) <= 8192:
            yield line


def _reference_key(value):
    return ' '.join(value.casefold().split())


def _document_lines(text):
    references, lines = {}, []
    for line in _prose_lines(text):
        definition = _MARKDOWN_REFERENCE.fullmatch(line)
        if definition:
            key, angled, plain = definition.groups()
            key, url = _reference_key(key), angled or plain
            previous = references.setdefault(key, url)
            if previous != url:
                references[key] = None
        else:
            lines.append(line)
    return lines, references


def _markdown_links(line, references):
    for match in _MARKDOWN_LINK.finditer(line):
        image, label, angled, inline, reference, auto = match.groups()
        url = angled or inline or auto or references.get(_reference_key(reference or label))
        if url:
            yield match, label or '', url, bool(image)


def _linked_author(value, references):
    for match, label, _, image in reversed(list(_markdown_links(value, references))):
        if not image and label:
            value = value[:match.start()] + label + value[match.end():]
    return value


def _relevant_lines(lines, references):
    blocked_level = None
    section_label = ''
    for line in lines:
        heading = _HEADING.match(line.lstrip())
        if heading:
            level = len(heading[1])
            if blocked_level is None or level <= blocked_level:
                blocked_level = level if _EXTERNAL.search(heading[2]) else None
                section_label = _context_label(heading[2])
        if blocked_level is not None:
            continue
        links = list(_markdown_links(line, references))
        prose = line
        for match, label, _, image in reversed(links):
            prose = prose[:match.start()] + ('' if image else label) + prose[match.end():]
        prose = _PLAIN_URL.sub('', prose)
        if not _EXTERNAL.search(prose):
            yield line, prose, links, section_label


def _text_names(path, text, lines, references):
    found = {}
    for line, _, _, _ in _relevant_lines(lines, references):
        match = _AUTHOR_LINE.match(line)
        if match:
            value = match[1].split('|', 1)[0].strip()
            value = _linked_author(value, references)
            if value.startswith('['):
                try:
                    value = json.loads(value)
                except ValueError:
                    continue
            for name in _names(value):
                found.setdefault(name.casefold(), name)
    if not found and path.stem.casefold() in {'author', 'authors', '作者', '著者'}:
        lines = [line.strip().removeprefix('- ') for line in text.splitlines() if line.strip()]
        if len(lines) <= 16 and all(not re.search(r'[:：=]', line) for line in lines):
            return _names(lines)
    return list(found.values())


def _safe_url(value):
    if not isinstance(value, str) or not 0 < len(value) <= 2048:
        return None
    if (any(ch.isspace() or category(ch).startswith('C') or ch in '\\<>"`' for ch in value)
            or re.search(r'%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)', value, re.I)):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        if (parts.scheme not in ('http', 'https') or not host or '@' in parts.netloc
                or '%' in parts.netloc or parts.netloc.endswith(':')):
            return None
        if ':' in host:
            if not re.fullmatch(r'\[[^\]]+\](?::[0-9]+)?', parts.netloc):
                return None
            host = '[' + str(IPv6Address(host)) + ']'
        else:
            host = host.encode('idna').decode('ascii').casefold().rstrip('.')
            if not all(re.fullmatch(r'(?!-)[a-z0-9-]{1,63}(?<!-)', part) for part in host.split('.')):
                return None
        port = parts.port
        if port is not None and port != (443 if parts.scheme == 'https' else 80):
            host = f'{host}:{port}'
    except (ValueError, UnicodeError):
        return None
    return parts._replace(netloc=host, path=parts.path or '/').geturl()


def _clean_label(value):
    if not isinstance(value, str) or any(category(ch).startswith('C') for ch in value):
        return ''
    value = value.strip(' `*_#▶️')
    if not 0 < len(value) <= 80 or re.search(r'https?://|[<>]', value, re.I):
        return ''
    return value


def _context_label(value):
    simple = _clean_label(value).casefold()
    if simple in {'links', 'related links', '链接', '相关链接'}:
        return '相关链接'
    if simple in {'download', 'downloads', '下载', '模组下载', '外观下载'}:
        return '下载'
    return next((label for label, pattern in _LINK_CONTEXT if re.search(pattern, value, re.I)), '')


def _video_link(url):
    if _safe_url(url) is None:
        return False
    parts = urlsplit(url)
    host = parts.hostname.casefold().removeprefix('www.').removeprefix('m.')
    if host in {'bilibili.com', 'youtube.com', 'vimeo.com'}:
        return bool(re.match(r'^/(?:video/|shorts/|watch$|[0-9]+/?$)', parts.path))
    return host in {'youtu.be', 'b23.tv'} and parts.path not in ('', '/')


def _json_links(data, *, include_meta=True, include_author=True):
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        field = re.sub(r'[_ -]', '', key.casefold())
        default = _LINK_FIELDS.get(field)
        if default:
            yield from _link_values(value, default)
        elif include_meta and field in {'meta', 'metadata'}:
            yield from _json_links(value, include_meta=False)
    if include_author:
        for key in ('author', 'authors'):
            value = data.get(key)
            authors = value if isinstance(value, list) else [value]
            for author in authors[:32]:
                yield from _json_links(author, include_meta=False, include_author=False)


def _link_values(value, default, depth=0):
    if depth >= 3:
        return
    if isinstance(value, str):
        yield value, default, default
    elif isinstance(value, list):
        for item in value[:32]:
            yield from _link_values(item, default, depth + 1)
    elif isinstance(value, dict):
        direct = value.get('url') or value.get('href')
        if isinstance(direct, str):
            label = _clean_label(value.get('label') or value.get('title') or value.get('name'))
            if not _EXTERNAL.search(label):
                yield direct, label or default, default
        else:
            for key, item in value.items():
                label = _LINK_FIELDS.get(re.sub(r'[_ -]', '', key.casefold())) or _context_label(key)
                if label and not _EXTERNAL.search(key):
                    yield from _link_values(item, label, depth + 1)


def _text_links(path, lines, references):
    document_label = (_LINK_FIELDS.get(path.stem.casefold()) or _context_label(path.stem)
                      or '相关链接') if path.stem.casefold() in _LINK_DOCUMENTS else ''
    if path.suffix.casefold() == '.url':
        for line in lines:
            key, separator, url = line.partition('=')
            if separator and key.strip().casefold() == 'url':
                yield url.strip(' '), document_label, document_label
        return
    for line, prose, links, section_label in _relevant_lines(lines, references):
        context = '作者主页' if _AUTHOR_LINE.match(prose) else _context_label(prose)
        prefix = _clean_label(re.split(r'[：:=]\s*(?!//)', prose, 1)[0].lstrip(' >*-#'))
        context_text = prefix if prefix and _context_label(prefix) else ''
        for match, text_label, url, image in links:
            if image:
                continue
            standalone = line.strip(' >*-+\t') == match[0]
            kind = context or document_label or (section_label if standalone else '')
            kind = kind or ('演示视频' if standalone and _video_link(url) else '')
            if kind:
                label = _clean_label(text_label)
                if kind in {'作者主页', '演示视频'} and not _context_label(label):
                    label = ''
                yield url, context_text or label or kind, kind
        uncovered = line
        for match, _, _, _ in reversed(links):
            uncovered = uncovered[:match.start()] + uncovered[match.end():]
        for match in _PLAIN_URL.finditer(uncovered):
            url = match[0].rstrip('.,;!?')
            standalone = uncovered.strip(' >*-+<\t`') == url
            kind = context or document_label or (section_label if standalone else '')
            kind = kind or ('演示视频' if standalone and _video_link(url) else '')
            if kind:
                yield url, context_text or kind, kind


def _unique_links(candidates):
    links = {}
    for url, label, kind in candidates:
        key = _safe_url(url)
        if key is not None and key not in links:
            links[key] = (url, label, kind)
            if len(links) == _MAX_LINKS:
                break
    return list(links.values())


def _read(archive, info, path):
    if (not 0 < info.file_size <= MAX_METADATA or
            stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)):
        return None
    try:
        raw = archive.read(info)
        if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
            text = raw.decode('utf-16')
        else:
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw.decode('gb18030')
        return json.loads(text) if path.suffix.casefold() == '.json' else text
    except (OSError, ValueError, RecursionError, RuntimeError, NotImplementedError, BadZipFile):
        return None


def _one_credit(claims):
    """Conflicting files at one priority level do not establish a credit."""
    if not claims:
        return None
    comparable = {frozenset(name.casefold() for name in names) for names, _ in claims}
    if len(comparable) != 1:
        return None
    names, path = min(claims, key=lambda claim: str(claim[1]).casefold())
    return '、'.join(names), str(path)


def read_authors(archive, records, *, expanded_members=None):
    """Retain the credit-only API for callers that do not need links."""
    return [(item['author'], item['imported_author_source']) if 'author' in item else None
            for item in read_attribution(archive, records, expanded_members=expanded_members)]


def read_attribution(archive, records, *, expanded_members=None):
    docs, declared = defaultdict(list), defaultdict(list)
    expanded_members = expanded_members or {}
    scopes = []
    for record in records:
        owner = record.get('entry', {}).get('private_declaration', {})
        member = record.get('_source_member')
        if owner:
            scope = _parts(_path(owner['root']))
        elif member is not None:
            member = expanded_members.get(str(member).casefold(), member)
            path = _path(member)
            scope = _parts(path.parent) if path.suffix.casefold() == '.carra2' else _package_root(path)
        else:
            scope = ()
        frame = len(scope) >= 2 and scope[-2] == 'skins' and bool(owner)
        scopes.append((scope, scope[:-2] if frame else scope, frame, owner.get('personality')))

    locations = {scope[:i] for scope, _, _, _ in scopes for i in range(len(scope) + 1)}
    seen = set()
    duplicates = set()
    entries = []
    for info in archive.infolist():
        path = _path(info.filename)
        key = _parts(path)
        if info.is_dir() or path.is_absolute() or '..' in path.parts or ':' in str(path):
            continue
        personality_path = (path.suffix.casefold() == '.json' and
                            key[-3:-1] == ('custom_limbus_data', 'personality'))
        root = key[:-3] if personality_path else key[:-1]
        rank = _readme_rank(path)
        if root and root[-1] == 'docs' and rank is not None:
            root, rank = root[:-1], rank + 4
        if root not in locations or not (personality_path or metadata_member(path)):
            continue
        if key in seen:
            duplicates.add(key)
        else:
            seen.add(key)
            entries.append((info, path, key, root, personality_path, rank))
    remaining = 16 * MAX_METADATA
    for info, path, key, root, personality_path, rank in entries:
        if key in duplicates or not 0 < info.file_size <= min(remaining, MAX_METADATA):
            continue
        remaining -= info.file_size
        data = _read(archive, info, path)
        if personality_path:
            rows = data.get('list') if isinstance(data, dict) else data
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and 'id' in row:
                        declared[root, str(row['id'])].append((path, row))
        elif data is not None:
            if isinstance(data, str):
                lines, references = _document_lines(data)
                names = _text_names(path, data, lines, references)
                links = _unique_links(_text_links(path, lines, references))
            else:
                names, links = _json_names(data), _unique_links(_json_links(data))
            docs[root].append((path, data, names, links, rank))

    package_scopes = {package for _, package, _, _ in scopes}
    addresses = defaultdict(int)
    for record in records:
        addresses[record.get('_source_address', '').casefold()] += 1
    result = []
    for record, (scope, package, frame, personality) in zip(records, scopes):
        specific = [(path, data, _fields(data)) for path, data in declared[scope, personality]]
        address = record.get('_source_address', '').casefold()
        for path, data, names, _, _ in docs[scope]:
            if frame and path.name.casefold() == 'manifest.json':
                specific.append((path, data, names))
            elif address and path.name.casefold() == 'mos-skin.json':
                policy = _prefab_data(data, address)
                if policy is not None:
                    specific.append((path, policy, _fields(policy)))
        # A root-level action manifest is tied to the matched prefab address,
        # even when that prefab's model resides in a wrapped package.
        if address and scope and addresses[address] == 1:
            for path, data, _, _, _ in docs[()]:
                if path.name.casefold() == 'mos-skin.json':
                    policy = _prefab_data(data, address)
                    if policy is not None:
                        specific.append((path, policy, _fields(policy)))

        specific_claims = [(names, path) for path, _, names in specific if names]
        specific_credit = _one_credit(specific_claims)
        # Conflicting specific declarations cannot establish associated links.
        fallback_links = [link for _, data, names in specific if specific_credit or not names
                          for link in _json_links(data)]
        fallback_claims = specific_claims
        readme_claims, readme_links = [], []
        for depth in range(len(scope), -1, -1):
            root = scope[:depth]
            if frame and depth < len(package):
                break
            if root != scope and any(other != package and other[:depth] == root
                                     for other in package_scopes):
                break
            structured, signed, readmes = [], [], defaultdict(list)
            for path, data, names, links, rank in docs[root]:
                if frame and root == scope and path.name.casefold() == 'manifest.json':
                    continue
                if rank is not None:
                    readmes[rank].append((path, names, links))
                    continue
                if names:
                    (signed if isinstance(data, str) else structured).append((names, path))
                fallback_links.extend(links)
            if not fallback_claims:
                fallback_claims = structured or signed
            covered_categories = set()
            for rank in sorted(readmes):
                tier = sorted(readmes[rank], key=lambda item: str(item[0]).casefold())
                if not readme_claims:
                    readme_claims = [(names, path) for path, names, _ in tier if names]
                links = [link for _, _, document_links in tier for link in document_links
                         if link[2] not in covered_categories]
                readme_links.extend(links)
                covered_categories.update(kind for _, _, kind in links)

        credit = _one_credit(readme_claims or fallback_claims)
        readme_categories = {kind for _, _, kind in readme_links}
        links = _unique_links([*readme_links, *(link for link in fallback_links if link[2] not in readme_categories)])
        row = dict(zip(('author', 'imported_author_source'), credit)) if credit else {}
        if links:
            row['author_links'] = [{'url': url, 'label': label} for url, label, _ in links]
        result.append(row)
    return result
