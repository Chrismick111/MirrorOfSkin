"""Register only the motion-bundle appearances selected by personality declarations."""
from pathlib import PurePosixPath

from import_progress import progress_range
from imported_catalog import display_name
from private_identity import recipe_identities


def describe_unbound_package_resources(archive, package_root):
    root = tuple(part.casefold() for part in package_root.parts)
    audio = assistants = False
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename.replace('\\', '/'))
        parts = tuple(part.casefold() for part in path.parts)
        if parts[:len(root)] != root:
            continue
        suffix = parts[len(root):]
        if (suffix[:1] == ('custom_sounds',) and len(suffix) > 1
                and path.suffix.casefold() in ('.json', '.wav', '.ogg', '.mp3', '.bank')):
            audio = True
        if suffix[:2] == ('custom_limbus_data', 'assistant') and path.suffix.casefold() == '.json':
            assistants = True
    warnings = []
    if audio:
        warnings.append('独立音频的私服运行时触发未接通')
    if assistants:
        warnings.append('召唤物的私服运行时触发未接通')
    return warnings


def describe_unbound_frames(archive, recipe):
    from authored_frame_motion import match_frame_coins, read_frame_motions

    directory = PurePosixPath(recipe.bundle.filename.replace('\\', '/')).parent
    try:
        motions = read_frame_motions(archive, directory)
    except (OSError, ValueError) as error:
        return '附带的散帧格式未通过验证：' + str(error)
    if not motions:
        return ''
    groups = []
    for role, action in sorted(recipe.actions.items()):
        clips = match_frame_coins(motions, role, action)
        if clips:
            groups.append(f'{role}（{len(clips)} 段）')
    if groups:
        return '已核对但未绑定到游戏动作槽的散帧：' + '、'.join(groups)
    return '附带的散帧没有可核实的逐币动作对应，未绑定'


def build_motion_records(archive, recipes, work, unity, name, archive_name, report, *, source, registered):
    from motion_bundle_model import build_motion_model
    from skin_assets import _catalog_keys, _dependency
    from stock_coin_import import _locate

    keys = _catalog_keys()
    ids = recipe_identities((r.declaration for r in recipes), 'motion-bundle', source, registered)
    base_keys = {key.rsplit('/', 1)[-1].removesuffix('.prefab') for key in keys}
    names = {}
    for recipe in recipes:
        matches = {key for key in base_keys if key.casefold() == recipe.base.casefold()}
        if len(matches) > 1:
            raise ValueError('动作外观的基础模型有多个匹配项：' + recipe.base)
        names[recipe.base] = next(iter(matches), recipe.base)
    bases = _locate(set(names.values()), unity, progress_range(report, 0, 22))
    for index, recipe in enumerate(recipes):
        declaration = recipe.declaration
        identity = ids[declaration]
        look = identity.look
        fallback = declaration.appearance if recipe.stock_override else declaration.appearance[9:]
        label = display_name(name or declaration.label or fallback, archive_name)
        if name and len(recipes) > 1:
            label += ' · ' + (declaration.label or fallback)
        unit_report = progress_range(report, 22 + 78 * index // len(recipes),
                                     22 + 78 * (index + 1) // len(recipes))
        unit_report(0, '正在读取动作外观：' + label)
        base = bases[names[recipe.base]]
        dependency = _dependency(names[recipe.base], base[1], keys)
        encoded, address, layout, entry, timing, actions = build_motion_model(
            archive.read(recipe.bundle), base, look, unity, recipe.actions, progress=unit_report,
            stock_override=recipe.stock_override)
        warnings = actions.pop('presentation_warnings', [])
        if recipe.extra_resources:
            detail = describe_unbound_frames(archive, recipe)
            if detail:
                warnings.append(detail)
            warnings.append('外观包中的其他附属呈现资源未绑定')
        warnings.extend(describe_unbound_package_resources(archive, declaration.package_root))
        entry['name'] = label
        entry['private_declaration'] = identity.owner
        bundle = work / (look + '.bundle')
        work.mkdir(parents=True, exist_ok=True)
        bundle.write_bytes(encoded)
        yield dict(look=look, name=label, asset=address, layout=layout, dependency=dependency,
                   bundle=bundle, entry=entry, timing=timing, actions=actions,
                   model_voice_evidence=actions.pop('model_voice_evidence', dict(state='unknown', count=0)),
                   presentation_warning='；'.join(warnings),
                   _uses_legacy_private_id=identity.uses_legacy)
