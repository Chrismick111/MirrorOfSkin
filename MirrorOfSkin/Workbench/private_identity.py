"""Assign imported appearance IDs from the author's scoped personality declaration."""

from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import NamedTuple


class RecipeIdentity(NamedTuple):
    look: str
    owner: dict
    uses_legacy: bool


def recipe_identities(declarations, kind, source, registered):
    """Retain old recipe IDs for their recorded owner and scope new IDs to the archive."""
    choices = []
    for declaration in declarations:
        root = declaration.package_root
        scope = str(root) if root.parts else Path(source).stem
        old_key = '/'.join((kind, scope.casefold(), declaration.personality))
        legacy = 'WBImp_' + sha256(old_key.encode('utf-8')).hexdigest()[:24]
        choices.append((declaration, legacy))
    ids = PrivateIdentities(choices, registered, source)
    result = {}
    for declaration, legacy in choices:
        look = ids.look(declaration, legacy)
        result[declaration] = RecipeIdentity(look, ids.owner(declaration), look == legacy)
    return result


class PrivateIdentities:
    def __init__(self, choices, registered, source):
        self.source = source.casefold()
        self.stem = Path(self.source).stem
        self.requests = Counter(legacy for _, legacy in choices)
        self.by_id = {entry['identity_id']: entry for entry in registered}
        self.by_owner = {}
        for entry in registered:
            owner = entry.get('private_declaration')
            if isinstance(owner, dict) and owner.get('source') == self.source:
                key = owner.get('root'), owner.get('personality')
                if all(isinstance(value, str) for value in key):
                    if key in self.by_owner:
                        raise ValueError('已导入外观的私服人格归属重复，请核对外观库')
                    self.by_owner[key] = entry['identity_id'][6:]

    def owner(self, declaration):
        root = str(declaration.package_root).casefold() if declaration.package_root.parts else ''
        return {'source': self.source, 'root': root, 'personality': declaration.personality}

    def look(self, declaration, legacy):
        owner = self.owner(declaration)
        key = owner['root'], owner['personality']
        if key in self.by_owner:
            return self.by_owner[key]
        old = self.by_id.get('story_' + legacy)
        if self.requests[legacy] == 1 and old and self.can_replace(old, owner, self.stem, legacy=True):
            return legacy
        key_bytes = '\0'.join(('private-declaration', self.source, *key)).encode('utf-8')
        return 'WBImp_' + sha256(key_bytes).hexdigest()[:24]

    @staticmethod
    def can_replace(current, owner, source_stem, *, legacy=False):
        bound = current.get('private_declaration')
        if bound is not None:
            return bound == owner
        return legacy and str(current.get('import_source', '')).casefold() == source_stem
