"""Exercise the final archive in a fresh add-on directory using its packaged modules."""
import json
import pathlib
import os
import subprocess
import sys
import tempfile
import struct
from urllib.request import build_opener, ProxyHandler, Request
import zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_link_release import VERSION, STORY_TIMINGS

archive, game = map(pathlib.Path, sys.argv[1:])
with tempfile.TemporaryDirectory() as temp:
    addon = pathlib.Path(temp) / 'addons' / 'persona-workbench'
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(addon)
    sys.path[:0] = [str(addon/'Workbench'),str(addon)]
    import release_compatibility
    import rulesets
    import schemes
    import workbench
    manifest = release_compatibility.validate(str(addon), str(game), [], 'SinnersNative-v64.dll')
    assert manifest['version'] == VERSION
    for flag in ('wedge-borrow-native.enable','wedge-component-borrow.enable'):
        assert (addon/flag).is_file()
    catalog = rulesets.catalog(addon)
    assert {'story_8380_SanchoAppearance','story_1318_Pinky_DiscipleAppearance'} <= set(catalog)
    clash_updates = json.loads(pathlib.Path(__file__).with_name('clash_catalog_repairs.json').read_bytes())
    assert len(set(clash_updates)) == 437
    assert all('clash' not in catalog[i].get('excluded_actions',[]) for i in clash_updates)
    assert catalog['story_1525_JeanneBlueprint_DefaultAppearance']['no_attack']
    for name in STORY_TIMINGS:
        contract = (addon/name).read_bytes()
        magic, version, slots, size = struct.unpack_from('<4sIII', contract)
        offset = 16 + slots * struct.calcsize('<iii128s')
        assert magic == b'SST1' and version == 1 and len(contract) == offset+size
        data = json.loads(contract[offset:])
        assert pathlib.Path(name).stem == 'story_'+data['AppearanceName']
    expected_keys = {'1450_Distorted_ChoiAppearance': 'SD_Abnormality',
                     '1501_4F_AlriuneAppearance': 'SD_Enemy'}
    for look, group in expected_keys.items():
        assert catalog['story_'+look]['asset_key'] == f'{group}/{look}.prefab'
    # Exercise the pool-preparation part of the actual launcher without starting a game.
    source = (addon/'scr.py').read_text('utf8')
    pool_scope = dict(ROOT=addon, struct=struct, json=json, pathlib=pathlib)
    exec(compile(source[source.index('ROW4 ='):source.index('def _delay_ready')], 'pool preparation', 'exec'), pool_scope)
    pool_scope['ensure_user_config']()
    pool_scope['prepare_native_pools']()
    bundled = addon/'Assets/runtime/story_defaults.zip'
    with zipfile.ZipFile(bundled) as defaults:
        assert len(defaults.namelist()) >= 509
        timings = addon/'Assets/runtime/story_native'
        assert all((timings/name).read_bytes()==defaults.read(name) for name in defaults.namelist())
        sample = timings/defaults.namelist()[0]
        original = sample.read_bytes()
        sample.write_bytes(b'local scan')
        pool_scope['_pool_workbench_module']('story_defaults').restore(addon)
        assert sample.read_bytes()==b'local scan'
        sample.write_bytes(original)
        assert all((timings/(entry['identity_id']+'.bin')).is_file() for entry in catalog.values()
                   if entry.get('story_metadata') and not entry.get('no_attack'))
    rows = pool_scope['_old_pool_rows']()
    repaired_rows = {r['identity_id']:r for r in rows if r['identity_id'] in clash_updates}
    assert len(repaired_rows)==len(clash_updates)
    assert all((r['_mask'] & 8)==0 and (r['_mask'] & 1) for r in repaired_rows.values())
    assert any(r['identity_id']=='story_1525_JeanneBlueprint_DefaultAppearance' and
               r['_mask'] & 0x40000000 for r in rows)
    assert {row['appearance_name'] for row in rows if row['appearance_name'] in expected_keys} == set(expected_keys)
    assert all(row['asset_key'] == expected_keys[row['appearance_name']]+'/'+row['appearance_name']+'.prefab'
               for row in rows if row['appearance_name'] in expected_keys)
    store = workbench.Store(addon)
    assert len(store.data()['catalog']) >= len(catalog)
    name = schemes.save(addon,'首次安装读写检查')
    assert schemes.get(addon,name)['schema']==3
    with subprocess.Popen(
        [sys.executable, '-B', str(addon/'Workbench/workbench.py'), '--addon', str(addon),
         '--no-browser', '--host-pid', str(os.getpid())],
        stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    ) as server:
        try:
            url = server.stdout.readline().strip()
            assert url.startswith('http://127.0.0.1:')
            local = build_opener(ProxyHandler({}))
            for route in ('', 'effect-editor'):
                with local.open(url+route, timeout=10) as page:
                    assert page.headers.get_content_type() == 'text/html' and len(page.read())>1000
            with local.open(url+'api/data', timeout=30) as reply:
                assert len(json.load(reply)['catalog'])>=len(catalog)
            with local.open(url+'api/schemes', timeout=30) as reply:
                profiles = json.load(reply)['chapter_nine']
            ids = {row['identity'] for row in profiles}
            assert len(ids) == len(profiles) == 10

            def post(route, data):
                request = Request(url+'api/'+route, data=json.dumps(data).encode(),
                                  headers={'X-Workbench': url.rstrip('/').rsplit('/',1)[1],
                                           'Content-Type': 'application/json'})
                with local.open(request, timeout=60) as reply:
                    return json.load(reply)

            def load_scheme(data):
                return post('scheme-load', data)['loaded']

            previous = schemes.capture(addon)
            assert '五指' in load_scheme({'builtin': 'chapter-nine'})
            backup = addon / schemes.DIR / (schemes.BACKUP + '.json')
            original_backup = backup.read_bytes()
            pool_scope['prepare_native_pools']()
            raw_pool = (addon / 'native_pools.bin').read_bytes()
            active_groups = set()
            for fields in pool_scope['ROW'].iter_unpack(raw_pool[16:]):
                if fields[1] and fields[4] > 0 and fields[9] == 1:
                    identity = fields[8].rstrip(b'\0').decode()
                    if identity in ids:
                        assert fields[0] == int(identity[:3])
                        active_groups.add((identity, fields[10].rstrip(b'\0').decode()))
            assert active_groups == {(i, 'ch9_' + i) for i in ids}
            members = {(r['base_identity'],r['identity_id']) for r in pool_scope['_old_pool_rows']()
                       if r['entry_kind']=='appearance'}
            for profile in profiles:
                assert all((profile['identity'],s['identity_id']) in members for s in profile['stages'])
            load_scheme({'builtin':'chapter-nine'})
            assert backup.read_bytes() == original_backup, 'Reactivating overwrote the pre-switch backup'
            assert load_scheme({'name': schemes.BACKUP}) == schemes.BACKUP
            restored = schemes.capture(addon)
            assert restored['rulesets'] == previous['rulesets']
            assert restored['stage_director'] == previous['stage_director']
            print('CHAPTER_SCHEME_HTTP_AND_NATIVE_POOL_PASS',len(profiles))
            def active_chapters():
                pool_scope['prepare_native_pools']()
                raw = (addon/'native_pools.bin').read_bytes()
                return {r[10].rstrip(b'\0').decode() for r in pool_scope['ROW'].iter_unpack(raw[16:])
                        if r[1] and r[4] > 0 and r[9] == 1}

            def chapter(route, identity):
                payload = post(route, {'rule':{'kind':'chapter','identity':identity}})
                return {i['identity'] for i in payload['rulesets'] if i['kind']=='chapter' and i['active']}

            personal = rulesets.identity_file(addon, '10314')
            rulesets.create_identity(addon,'103','10314',catalog)
            personal_bytes = personal.read_bytes()
            _, items=rulesets.list_rulesets(addon, lambda identity: False)
            regular = next(i for i in items if i['id']=='identity:10314')
            post('ruleset-activate',{'rule':regular})
            assert chapter('ruleset-activate','10314') == {'10314'}
            assert active_chapters() == {'ch9_10314'}
            assert chapter('ruleset-activate','10215') == {'10314','10215'}
            assert active_chapters() == {'ch9_10314','ch9_10215'}
            post('scheme-save', {'name':'双人格'})
            assert chapter('ruleset-deactivate','10314') == {'10215'}
            assert active_chapters() == {'ch9_10215'}
            assert chapter('ruleset-only','11115') == {'11115'}
            assert active_chapters() == {'ch9_11115'}
            assert personal.read_bytes() == personal_bytes
            load_scheme({'name':'双人格'})
            assert active_chapters() == {'ch9_10314','ch9_10215'}
            post('ruleset-activate',{'rule':regular})
            assert active_chapters() == {'ch9_10215'}
            # Legacy 0.77 selection remains individually switchable on upgrade.
            old = json.loads(personal_bytes)
            old['entries']=[{'entry_kind':'group','group_id':'ch9_10314','weight':1}]
            rulesets._write(personal, old)
            assert chapter('ruleset-deactivate','10314') == {'10215'}
            assert active_chapters() == {'ch9_10215'}
            print('CHAPTER_SINGLE_MIX_ONLY_SAVE_LEGACY_PASS')
            stop=Request(url+'api/instance-shutdown', data=b'{}',
                         headers={'X-Workbench':url.rstrip('/').rsplit('/',1)[1]})
            with local.open(stop,timeout=10) as reply:
                assert json.load(reply)['stopping']
            assert server.wait(timeout=15)==0
        finally:
            if server.poll() is None:
                server.kill()
    print('CLEAN_INSTALL_PASS',manifest['version'],len(catalog),'appearances')
