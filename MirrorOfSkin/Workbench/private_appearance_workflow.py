"""Resolve each personality declaration independently within its author's package."""
from dataclasses import dataclass

from motion_bundle_recipe import read_motion_bundle_recipes
from private_server_appearance import read_declarations
from stock_coin_recipe import read_stock_coin_recipes


@dataclass
class PrivateAppearanceWorkflow:
    motions: list
    remaining: list
    coin_recipes: list

    @classmethod
    def discover(cls, archive, unity=None):
        declared = read_declarations(archive)
        motions = read_motion_bundle_recipes(archive, declarations=declared, unity=unity)
        # Motion recipes may enrich the declaration, so match its authored key.
        claimed = {(r.declaration.package_root, r.declaration.personality) for r in motions}
        remaining = [d for d in declared if (d.package_root, d.personality) not in claimed]
        coins = read_stock_coin_recipes(archive, declarations=remaining) if remaining else []
        return cls(motions, remaining, coins)

    def remaining_coins(self, selected):
        bound = {d for selections in selected.values() for d, _ in selections}
        return [(d, recipe) for d, recipe in self.coin_recipes if d not in bound]

    @staticmethod
    def missing_body(declarations):
        names = '、'.join(f'{d.personality}（{d.appearance}）' for d in declarations[:6])
        return ('已读取私服人格声明：' + names +
                '。未找到能与声明对应的作者身体、动作资源或逐币换形配置；人格池未添加条目。')
