"""Import original Mod Spec v2 archives twice in a clean launcher profile.

Use a Python environment with UnityPy and Pillow available. Supply the plugin,
original appearance archives, and game installation through the CLI.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

def author_skins(path):
    expected = {}
    with ZipFile(path) as archive:
        for entry in archive.namelist():
            if PurePosixPath(entry).name != 'pack.json':
                continue
            pack = json.loads(archive.read(entry))
            for skin in pack['skins']:
                folder = PurePosixPath(entry).parent / 'skins' / skin
                manifest = json.loads(archive.read(str(folder / 'manifest.json')))
                label = manifest['meta']['display_name']
                assert label not in expected
                expected[label] = (str(folder).casefold(), manifest)
    assert expected, path
    return expected


def check_dialogue_files(archive_path, folder, declared, package_dir, look):
    owner = str(declared['target']['personality_id'])
    voice_prefix = folder + '/' + declared['voice']['dir'].casefold() + '/'
    locale_prefix = folder + '/' + declared['locale']['exclusive_dir'].casefold() + '/'
    sounds, text = {}, {}
    with ZipFile(archive_path) as source:
        for info in source.infolist():
            name = info.filename.casefold().replace('\\', '/')
            key = PurePosixPath(name).stem
            if name.startswith(voice_prefix) and name.endswith('.wav') and key.startswith('battle'):
                sounds[key] = sha256(source.read(info)).hexdigest() + '.wav'
            if name.startswith(locale_prefix) and '/battlespeechbubbletext/' in name and name.endswith('.json'):
                for event, row in json.loads(source.read(info)).items():
                    text[event.casefold()] = ' '.join(row['dlg'].split())
    actual = {}
    mapping = package_dir / (look + '.voice.tsv')
    if not sounds and not text:
        assert not mapping.exists() or not mapping.read_bytes()
        return set(), 0
    for line in mapping.read_text('utf8').splitlines():
        assigned_owner, event, wav, bubble = line.split('\t')
        assert assigned_owner == owner and event not in actual
        if wav:
            assert '/' not in wav and '\\' not in wav
            assert sha256((package_dir / wav).read_bytes()).hexdigest() + '.wav' == wav
        actual[event] = (wav, bubble)
    assert {k: w for k, (w, _) in actual.items() if w} == sounds, (look, 'WAV')
    assert {k: b for k, (_, b) in actual.items() if b} == text, (look, 'captions')
    return set(sounds.values()), len(text)


def verify_bundle(unity, model, address, look, personality):
    from roland_merge import Prefab
    from skin_assets import _roots

    env = unity.load(model.read_bytes())
    [(actual_address, root, _)] = _roots(env)
    assert actual_address == address
    prefab = Prefab.from_asset(env, root)
    assert prefab.objects[root].peek_name() == look
    renderer = prefab.tree(prefab.app['sprenderer_charactermotion']['m_PathID'])
    prefix = 'mos_frame_' + personality + '_'
    idle = prefab.objects[renderer['m_Sprite']['m_PathID']]
    assert idle.peek_name() in (prefix + 'default', prefix + 'idle'), idle.peek_name()
    referenced = set()
    for clip in prefab.objects.values():
        if clip.type.name == 'AnimationClip':
            constant = clip.read_typetree()['m_ClipBindingConstant']
            for p in constant['pptrCurveMapping']:
                if p['m_FileID'] == 0 and p['m_PathID'] in prefab.objects:
                    sprite = prefab.objects[p['m_PathID']]
                    if sprite.type.name == 'Sprite' and sprite.peek_name().startswith(prefix):
                        referenced.add(sprite.peek_name()[len(prefix):])
    for poses in ({'guard', 'gud'}, {'evade', 'miss'}):
        assert poses & referenced, (poses, referenced)
    assert len({pose for pose in referenced if pose.startswith('skill')}) >= 2, referenced
    texture = idle.read_typetree()['m_RD']['texture']
    image = prefab.objects[texture['m_PathID']].read().image
    assert image is not None and image.convert('RGBA').getchannel('A').getbbox()
    return len(referenced)


def release_links(path):
    """Expected URLs from the release list in the original Mod Spec v2 demo packs."""
    with ZipFile(path) as archive:
        readme, = [n for n in archive.namelist() if PurePosixPath(n).name.lower() == 'readme.md']
        lines = archive.read(readme).decode('utf-8-sig').splitlines()
    markers = ('实机战斗演示视频', 'GitHub 仓库', '夸克网盘分流', '百度网盘分流')
    links = set()
    for line in lines:
        if any(marker in line for marker in markers):
            links.update(re.findall(r'\]\((https?://[^)\s]+)\)', line))
    return links


def release_credit(path):
    """Independent check of the signed header in the four original release READMEs."""
    with ZipFile(path) as archive:
        readme, = [n for n in archive.namelist() if PurePosixPath(n).name.casefold() == 'readme.md']
        text = archive.read(readme).decode('utf-8-sig')
    credit, = re.findall(r'^> \*\*作者\*\*:\s*`([^`]+)`', text, re.M)
    return readme, credit


def verify(candidate, archives, game, index, upgrade_from=None, rebuilt_models=False, check_authors=False,
           check_links=False, readme_first=False):
    check_authors = check_authors or readme_first
    with TemporaryDirectory(prefix='verify-framepack-') as temp:
        scratch = Path(temp)
        addon = scratch / 'launcher/addons/MirrorOfSkin'
        data = scratch / 'profile/FaustLauncher/MOS_data'
        cache = scratch / 'index'
        cache.mkdir()
        if index is not None:
            shutil.copyfile(index, cache / 'resource-index.json')
        os.environ.update(APPDATA=str(scratch / 'profile'), FAUST_MOS_DATA_ROOT=str(data),
                          LIMBUS_GAME_DIR=str(game), LIMBUS_RESOURCE_INDEX=str(cache))
        prior_models = {}
        prior_playback = {}
        prior_weights = {}
        if upgrade_from:
            with ZipFile(upgrade_from) as installation:
                installation.extractall(addon.parent)
            env = os.environ.copy()
            for archive in archives:
                run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(addon / 'Workbench/skin_import.py'),
                                      str(archive), '--json'], capture_output=True, encoding='utf8', env=env)
                assert run.returncode == 0, run.stderr
                old = json.loads(run.stdout)
                assert all(r['status'] == 'added' for r in old)
                for row in old:
                    identity = row['identity_id']
                    loc = data / 'Assets/ImportedSkins' / (identity[6:] + '.loc')
                    model = addon / loc.read_text('utf8')
                    prior_models[identity] = (model, sha256(model.read_bytes()).hexdigest())
                    digest = prior_models[identity][1]
                    timing = loc.with_name(identity[6:] + '-' + digest + '.sst')
                    prior_playback[identity] = (row['actions'], timing.read_bytes(), row['dialogue_detection'])
            if check_authors:
                pool_path = data / 'Assets/runtime/all_sinners_pools.json'
                pools = json.loads(pool_path.read_bytes())
                for group in pools.values():
                    for entry in group['entries']:
                        identity = entry['identity_id']
                        if identity in prior_models:
                            entry['weight'] = 2 + len(prior_weights)
                            prior_weights[identity] = entry['weight']
                pool_path.write_text(json.dumps(pools, ensure_ascii=False), encoding='utf8')
        if candidate.is_dir():
            shutil.copytree(candidate, addon, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '外来外观'))
        else:
            with ZipFile(candidate) as installation:
                installation.extractall(addon.parent)
        sys.path.insert(0, str(addon / 'Workbench'))
        from skin_import import CATALOG, LOCAL, import_skin
        from imported_catalog import apply as open_catalog
        from imported_portraits import get
        import UnityPy

        snapshots = {}
        portrait_hashes = set()
        sound_sets = {}
        expected_authors = {}
        checked_links = {}
        for archive in archives:
            expected = author_skins(archive)
            urls = release_links(archive) if check_links else set()
            if readme_first:
                readme, release_author = release_credit(archive)
            for status in ('added', 'existing'):
                percentages = []
                rows = import_skin(archive, addon, unity=UnityPy,
                                   progress=lambda value, _: percentages.append(value))
                assert percentages[0] == 0 and percentages[-1] == 100
                assert sorted(row['name'] for row in rows) == sorted(expected)
                catalog = json.loads((data / CATALOG).read_bytes())
                entries = {e['identity_id']: e for group in catalog.values() for e in group['entries']}
                open_catalog(entries, data, addon)
                for row in rows:
                    label = row['name']
                    if prior_models and status == 'added':
                        updated_status = 'existing' if check_links and not urls and not readme_first else 'updated'
                        assert row['status'] == updated_status and row['identity_id'] in prior_models
                    else:
                        assert row['status'] == status, (label, status, row['status'])
                    folder, declared = expected[label]
                    identity = row['identity_id']
                    look = identity.removeprefix('story_')
                    if check_links:
                        links = entries[identity].get('author_links', [])
                        assert len(links) == len(urls) and {link['url'] for link in links} == urls, label
                        assert all(link['label'].strip() and '://' not in link['label'] for link in links), label
                        assert row.get('author_links', []) == links, label
                        checked_links[identity] = links
                    if check_authors:
                        author = release_author if readme_first else declared['meta']['author']
                        assert entries[identity].get('author') == author, (label, 'stored author', author)
                        if readme_first:
                            assert row.get('author') == author
                            assert entries[identity]['imported_author_source'] == readme, (label, 'README origin')
                        expected_authors[identity] = author
                        if identity in prior_weights:
                            assert entries[identity]['weight'] == prior_weights[identity], (label, 'saved weight')
                    owner = entries[identity]['private_declaration']
                    assert owner['root'] == folder and owner['personality'] == str(declared['target']['personality_id'])
                    cfg = (data / LOCAL / (look + '.cfg')).read_text('ascii').splitlines()
                    assert cfg[0] == 'WBMOD1' and cfg[1].endswith('/' + declared['private_server']['vanilla_appearance_id'] + '.prefab')
                    relative = (data / LOCAL / (look + '.loc')).read_text('utf8')
                    model = (addon / relative).resolve()
                    assert model.is_relative_to((addon / '外来外观').resolve())
                    digest = sha256(model.read_bytes()).hexdigest()
                    if prior_models:
                        if rebuilt_models:
                            old_model, old_digest = prior_models[identity]
                            assert old_model.parent == model.parent and old_digest != digest, (label, 'model revision')
                            timing = data / LOCAL / (look + '-' + digest + '.sst')
                            assert prior_playback[identity] == (row['actions'], timing.read_bytes(),
                                                               row['dialogue_detection']), (label, 'presentation')
                        else:
                            assert prior_models[identity] == (model, digest), (label, 'upgrade changed the model')
                    assert model.name == cfg[3] == digest + '.bundle'
                    assert (data / LOCAL / (look + '-' + digest + '.sst')).stat().st_size > 0
                    portrait = get(data, identity)
                    assert portrait and portrait.startswith(b'\x89PNG')
                    thumbnail = sha256(portrait).hexdigest()
                    if status == 'added':
                        assert identity not in snapshots and thumbnail not in portrait_hashes
                        portrait_hashes.add(thumbnail)
                        snapshots[identity] = (model, thumbnail)
                        count = verify_bundle(UnityPy, model, cfg[2], look, owner['personality'])
                        print('Read back', count, 'distinct authored poses from', label, flush=True)
                        if rebuilt_models:
                            from check_framepack_idle_pose import report_bundle
                            report_bundle(model)
                    assert snapshots[identity] == (model, thumbnail)
                    assert row['actions']['attack'] and row['actions']['defense'], label
                    if declared.get('voice') and declared.get('locale'):
                        sounds, n = check_dialogue_files(archive, folder, declared, model.parent, look)
                        assert row.get('voice_connected') == bool(sounds), label
                        states = row['dialogue_detection']
                        assert (states['voice'] == 'connected') == bool(sounds)
                        assert (states['bubble'] == 'connected') == bool(n)
                        assert entries[identity]['dialogue_detection'] == states
                        sound_sets[identity] = sounds
                        print(label, len(sounds), 'unique WAV files and', n, 'author captions', flush=True)
                    print(row['status'], label, digest, flush=True)
        assert len(set(addon.glob('外来外观/**/*.bundle'))) == len(snapshots)
        if prior_models:
            assert set(snapshots) == set(prior_models)
        assert not list(data.rglob('*.wav')), 'audio duplicated in roaming profile'
        if check_authors or check_links:
            from workbench import Store
            reopened = {row['identity_id']: row for row in Store(addon).data()['catalog']}
            for identity, author in expected_authors.items():
                assert reopened[identity].get('author') == author, (identity, 'workbench author', author)
                print('Workbench author:', reopened[identity]['name'], author, flush=True)
            for identity, links in checked_links.items():
                assert reopened[identity].get('author_links', []) == links, (identity, 'workbench links')
                print('Workbench link labels:', reopened[identity]['name'], [link['label'] for link in links])
            if check_links:
                assert any(checked_links.values()), 'include a real Mod Spec v2 archive with a release list'
        from imported_package_uninstall import delete_identity
        from file_lock import FileLock
        for identity, (model, _) in snapshots.items():
            delete_identity(data, addon, identity, lock_factory=FileLock)
            assert not (model.parent / (identity[6:] + '.voice.tsv')).exists()
            keep = set().union(*(files for other, files in sound_sets.items()
                                     if other != identity and snapshots[other][0].parent == model.parent))
            assert {p.name for p in model.parent.glob('*.wav')} == keep
            sound_sets.pop(identity, None)
        print('PASS verified', len(snapshots), 'distinct models, portraits, action maps and stable identities')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('archives', nargs='+', type=Path)
    parser.add_argument('--game', required=True, type=Path)
    parser.add_argument('--resource-index', type=Path)
    parser.add_argument('--upgrade-from', type=Path, help='seed the profile with a previous frame-pack plugin first')
    parser.add_argument('--rebuilt-models', action='store_true',
                        help='expect a new model revision with identical actions, timing and dialogue')
    parser.add_argument('--check-authors', action='store_true',
                        help='verify declared skin authors in the saved pool and reopened workbench')
    parser.add_argument('--check-release-links', action='store_true',
                        help='verify links from the original demo video, repository and mirror list')
    parser.add_argument('--check-readme-author', action='store_true',
                        help='use the release README author and its source path as the expected credit')
    args = parser.parse_args()
    verify(args.candidate.resolve(), [p.resolve() for p in args.archives], args.game.resolve(), args.resource_index,
           args.upgrade_from, args.rebuilt_models, args.check_authors, args.check_release_links,
           args.check_readme_author)
