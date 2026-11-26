"""Resolve standalone material references against the installed game's material data."""
from copy import copy
import hashlib
from pathlib import Path

BUILTIN_FILES = {
    'library/unity default resources',
    'resources/unity_builtin_extra',
}


def material_identity(tree):
    def normalize(value):
        if isinstance(value, dict):
            return {key: (bool(item['m_PathID']) if key == 'm_Texture' and isinstance(item, dict)
                          and 'm_FileID' in item and 'm_PathID' in item else normalize(item))
                    for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return tuple(normalize(item) for item in value)
        return value

    return normalize({key: value for key, value in tree.items() if key != 'm_Shader'})


def _stock_material_identity(tree):
    from skin_assets import _dicts

    identity = material_identity(tree)
    if any(node.get('m_PathID') for node in _dicts(identity) if 'm_FileID' in node):
        return None
    return identity


class StandaloneMaterials:
    def __init__(self, file, unity, *, progress=None):
        self.externals = []
        self.file_ids = {}
        self.shaders = {}
        self.shader_objects = {}
        self.shader_ids = {}
        self.preload_refs = {}
        self.material_segments = {}
        self.mounts = {}
        self.unity = unity
        self.progress = progress
        self.orphan_voice_tracks = {}
        for index, external in enumerate(file.externals, 1):
            if external.path.casefold() in BUILTIN_FILES:
                self.externals.append(external)
                self.file_ids[index] = len(self.externals)

        materials = {}
        for pid, obj in sorted(file.objects.items()):
            if obj.type.name != 'Material':
                continue
            tree = obj.read_typetree()
            shader = tree['m_Shader']
            file_id = shader['m_FileID']
            if 0 < file_id <= len(file.externals) and file_id not in self.file_ids and shader['m_PathID']:
                materials[pid] = tree
        if not materials:
            return

        from scan.resource_catalog import resolve_roots

        game = resolve_roots()['game_dir']
        if game is None:
            raise ValueError('此外观需要核对游戏材质，请用 LIMBUS_GAME_DIR 指定游戏目录。')
        data = Path(game) / 'LimbusCompany_Data'
        files = {}
        for name in ('globalgamemanagers.assets', 'resources.assets'):
            path = data / name
            if path.is_file():
                files[path.name.casefold()] = unity.load(str(path)).assets[0]
        names = {tree['m_Name'] for tree in materials.values()}
        stock = []
        for owner in list(files.values()):
            for obj in owner.objects.values():
                if obj.type.name != 'Material' or obj.peek_name() not in names:
                    continue
                tree = obj.read_typetree()
                ref = tree['m_Shader']
                donor = owner
                if ref['m_FileID']:
                    path = owner.externals[ref['m_FileID'] - 1].path
                    if path.casefold() not in BUILTIN_FILES:
                        continue
                    if path.casefold() not in files:
                        source = data / path
                        if not source.is_file():
                            continue
                        files[path.casefold()] = unity.load(str(source)).assets[0]
                    donor = files[path.casefold()]
                shader = donor.objects.get(ref['m_PathID'])
                if shader and shader.type.name == 'Shader' and donor._m_target_platform == file._m_target_platform:
                    from skin_assets import _dicts

                    shader_tree = shader.read_typetree()
                    # The game and the local workbench run the Windows player.
                    if (4 in shader_tree.get('platforms', ()) and
                            not any(node.get('m_PathID') for node in _dicts(shader_tree) if 'm_FileID' in node)):
                        identity = _stock_material_identity(tree)
                        if identity is not None:
                            stock.append((identity, shader))
        for pid, tree in materials.items():
            signature = _stock_material_identity(tree)
            matches = {shader.get_raw_data(): shader for identity, shader in stock if identity == signature}
            if len(matches) == 1:
                self.shaders[pid] = next(iter(matches.items()))

    def revision(self, original):
        if not self.shaders and not self.material_segments:
            return original
        digest = hashlib.sha256(('shader-cab/' + original).encode('ascii'))
        for pid, (raw, shader) in self.shaders.items():
            digest.update(str(pid).encode('ascii') + b'\0')
            digest.update(repr(self._file_schema(shader.assets_file)).encode('ascii') + b'\0')
            digest.update(shader.serialized_type.old_type_hash)
            digest.update(hashlib.sha256(raw).digest())
        for file_id, segment in sorted(self.material_segments.items()):
            digest.update(str(file_id).encode('ascii') + b'\0')
            segment.revision(digest)
        return digest.hexdigest()

    def prepare_materials(self, env, root):
        from addressable_materials import resolve_materials
        from orphan_voice_tracks import resolve_orphan_voice_tracks

        self.material_segments = resolve_materials(env, root, self.unity, self.file_ids, progress=self.progress)
        self.orphan_voice_tracks = resolve_orphan_voice_tracks(env, root, self.unity)

    def voice_warning(self):
        count = sum(map(len, self.orphan_voice_tracks.values()))
        return f'原包缺少 {count} 条原版语音轨道，仅保留压缩包内可读取的动作和音效。' if count else ''

    def _mount(self, kind):
        return self.mounts.setdefault(kind, len(self.externals) + len(self.mounts) + 1)

    def material_pointer(self, file_id, path_id):
        segment = self.material_segments.get(file_id)
        if segment is None or path_id not in segment.ids:
            return None
        after = (self._mount(file_id), path_id)
        self.preload_refs[file_id, path_id] = after
        return after

    def material_preloads(self):
        return {(self.mounts[file_id], path_id)
                for file_id, segment in self.material_segments.items() if file_id in self.mounts
                for path_id in segment.ids}

    def shader_pointer(self, material_id, original):
        _, source = self.shaders[material_id]
        key = (source.assets_file.name, source.path_id)
        if key not in self.shader_ids:
            path_id = source.path_id
            if path_id in self.shader_objects:
                path_id = -1
                while path_id in self.shader_objects:
                    path_id -= 1
            self.shader_ids[key] = path_id
            self.shader_objects[path_id] = source
        before = (original['m_FileID'], original['m_PathID'])
        after = (self._mount('shader'), self.shader_ids[key])
        if self.preload_refs.setdefault(before, after) != after:
            raise ValueError('同一个外观着色器引用匹配到多个游戏着色器')
        return dict(m_FileID=after[0], m_PathID=after[1])

    @staticmethod
    def _file_schema(file):
        return (file.unity_version, file.header.version, file.header.endian,
                file._m_target_platform, file._enable_type_tree)

    def shader_file(self, model, model_cab, shader_cab):
        if not self.shader_objects:
            return None

        first = next(iter(self.shader_objects.values()))
        shaders = copy(first.assets_file)
        shaders.name = shader_cab
        shaders.parent = model.parent
        shaders.flags = model.flags
        shaders.objects = {}
        shaders.types = []
        shaders.externals = []
        shaders.script_types = []
        shaders.ref_types = []
        source_schema = self._file_schema(shaders)
        for path_id, source in sorted(self.shader_objects.items()):
            serialized = source.serialized_type
            if (self._file_schema(source.assets_file) != source_schema or
                    serialized.script_type_index != -1 or serialized.type_dependencies):
                raise ValueError('游戏着色器不能合并到同一个独立资源段')
            if serialized not in shaders.types:
                shaders.types.append(serialized)
            obj = copy(source)
            obj.assets_file = shaders
            obj.path_id = path_id
            obj.type_id = shaders.types.index(serialized)
            shaders.objects[path_id] = obj

        original_file_id, _ = next(iter(self.preload_refs))
        external = copy(model.externals[original_file_id - 1])
        external.path = f'archive:/{model_cab}/{shader_cab}'
        external.temp_empty = ''
        external.guid = bytes(16)
        external.type = 0
        self.externals.append(external)
        return shaders

    def resource_files(self, model, cab):
        members = {}
        for kind in self.mounts:
            mount = 'CAB-' + hashlib.sha256(f'{cab}/{kind}'.encode('ascii')).hexdigest()[:32]
            if kind == 'shader':
                members[mount] = self.shader_file(model, cab, mount)
            else:
                members.update(self.material_segments[kind].pack(model, cab, mount))
                external = copy(model.externals[kind - 1])
                external.path = f'archive:/{cab}/{mount}'
                external.temp_empty, external.guid, external.type = '', bytes(16), 0
                self.externals.append(external)
        return members
