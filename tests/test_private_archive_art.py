"""Private-server byte artwork must survive archive normalization."""
import sys
import unittest
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'MirrorOfSkin/Workbench'))
import mod_archive


class PrivateArchiveArt(unittest.TestCase):
    def test_decompressed_rar_and_7z_preserve_sprite_images(self):
        for name in ('Theme/CUSTOM_SPRITES/Sprite/miss.PNG', 'custom_sprites/缪开火SD.png'):
            self.assertTrue(mod_archive._supported_member(PurePosixPath(name)))
        for name in ('installer/icon.png', 'custom_sprites/run.exe', 'custom_sprites/readme.txt'):
            self.assertFalse(mod_archive._supported_member(PurePosixPath(name)))
