from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin/Workbench'))


class AppearanceAuthorsTest(unittest.TestCase):
    def read(self, files, records, *, include_links=False, **options):
        from appearance_authors import read_attribution, read_authors

        buffer = BytesIO()
        with ZipFile(buffer, 'w') as archive:
            for path, content in files.items():
                archive.writestr(path, json.dumps(content) if isinstance(content, dict) else content)
        with ZipFile(buffer) as archive:
            read = read_attribution if include_links else read_authors
            return read(archive, records, **options)

    def test_readme_links_precede_manifest_fallback_by_category_and_stay_scoped(self):
        path = 'Collection/A/skins/one/manifest.json'
        first = {'entry': {'private_declaration': {'root': 'collection/a/skins/one', 'personality': '1'}}}
        second = {'entry': {'private_declaration': {'root': 'collection/a/skins/two', 'personality': '2'}}}
        third = {'entry': {}, '_source_member': 'Collection/B/custom_appearance/body.bundle'}
        found = self.read({
            path: {'meta': {'author': {'name': 'One', 'homepage': 'https://one.example/author'},
                            'video': 'https://video.example/one'}},
            'Collection/A/pack.json': {'links': {'release': 'https://a.example/releases',
                                                 'video': 'https://video.example/one'}},
            'Collection/A/README.md': '演示视频：[预告片](https://video.example/trailer)\n'
                                      '依赖下载：[Demo](https://dependency.example/demo)',
            'Collection/README.md': '项目主页：https://curator.example/project',
            'Collection/B/README.md': 'https://www.bilibili.com/video/BV1abcdef',
        }, [first, second, third], include_links=True)
        urls = [[link['url'] for link in item['author_links']] for item in found]
        self.assertEqual(urls, [['https://video.example/trailer', 'https://one.example/author',
                                 'https://a.example/releases'],
                                ['https://video.example/trailer', 'https://a.example/releases'],
                                ['https://www.bilibili.com/video/BV1abcdef']])
        self.assertNotIn('author', found[2])
        self.assertEqual(found[0]['author'], 'One')

    def test_links_require_safe_urls_and_exclude_unrelated_markdown(self):
        path = 'custom_appearance/body.bundle'
        found = self.read({
            'pack.json': {'links': {'repository': {'url': 'https://source.example/repo', 'label': '源码'},
                                    'dependencyDownload': 'https://unrelated.example/download',
                                    'video': ['javascript:alert(1)', 'https://user:pw@example.com/x',
                                              'https://example.com/%0aevil', 'https://example.com/\nurl',
                                              'https://user@example.com/demo', '//example.com/video',
                                              'https://example.com:99999/video', 'https://x.com\\@on.com/',
                                              'https://SOURCE.example:443/repo']}},
            'README.md': '## Dependencies\n[Demo video](https://external.example/demo)\n\n'
                         '## 本模组\n[发布页](https://good.example/mod)\n'
                         '版权声明：[项目主页](https://copyright.example/mod)\n'
                         'Learn Unity from [UnityPy](https://github.com/K0lb3/UnityPy).\n'
                         '![preview](https://images.example/a.png)\n'
                         '```\n视频：https://example.com/sample\n```',
        }, [{'entry': {}, '_source_member': path}], include_links=True)
        self.assertEqual(found, [{'author_links': [
            {'url': 'https://good.example/mod', 'label': '发布页'},
            {'url': 'https://source.example/repo', 'label': '源码'},
        ]}])

    def test_carra2_links_follow_the_original_member(self):
        body = 'Generated/Installation/hash/otherhash/__data'
        found = self.read({
            'Pack/AddOn/README.txt': '演示视频：https://video.example/the-mod',
            'Pack/Dependencies/README.txt': '演示视频：https://video.example/dependency',
        }, [{'entry': {}, '_source_member': body}], include_links=True,
            expanded_members={body.casefold(): 'Pack/AddOn/Patch.carra2'})
        self.assertEqual(found, [{'author_links': [
            {'url': 'https://video.example/the-mod', 'label': '演示视频'},
        ]}])

    def test_folder_normalization_preserves_named_link_documents(self):
        from appearance_authors import read_attribution
        from mod_archive import normalized

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / '演示视频.txt').write_text('https://video.example/demo?id=42', encoding='utf-8')
            (folder / '发布页.url').write_text('[InternetShortcut]\n'
                                             'IconFile=https://other.example/icon\n'
                                             'URL=https://release.example/mod', encoding='utf-8')
            (folder / 'other.url').write_text('URL=https://other.example/mod', encoding='utf-8')
            (folder / 'README.zh-CN.md').write_text('作者：目录作者', encoding='utf-8')
            records = [{'entry': {}, '_source_member': 'custom_appearance/body.bundle'}]
            with normalized(folder) as package, ZipFile(package) as archive:
                found = read_attribution(archive, records)
        self.assertCountEqual(found[0]['author_links'], [
            {'url': 'https://video.example/demo?id=42', 'label': '演示视频'},
            {'url': 'https://release.example/mod', 'label': '发布页'},
        ])
        self.assertEqual(found[0]['author'], '目录作者')

    def test_conflicting_item_credits_do_not_expose_their_links(self):
        found = self.read({
            'Pack/custom_limbus_data/personality/a.json': {
                'list': [{'id': 123, 'author': 'A', 'authorUrl': 'https://a.example/author'}],
            },
            'Pack/custom_limbus_data/personality/b.json': {
                'list': [{'id': 123, 'author': 'B', 'authorUrl': 'https://b.example/author'}],
            },
            'Pack/README.md': '发布页：https://mod.example/project',
        }, [{'entry': {'private_declaration': {'root': 'Pack', 'personality': '123'}}}],
            include_links=True)
        self.assertEqual(found, [{'author_links': [
            {'url': 'https://mod.example/project', 'label': '发布页'},
        ]}])

    def test_action_manifest_links_follow_only_the_matching_prefab(self):
        found = self.read({
            'mos-skin.json': {'schema': 1, 'website': 'https://pack.example/mod', 'appearances': {
                'assets/A.prefab': {'videoUrl': 'https://video.example/a'},
                'assets/B.prefab': {},
            }},
        }, [
            {'entry': {}, '_source_member': 'custom_appearance/A.bundle', '_source_address': 'assets/a.prefab'},
            {'entry': {}, '_source_member': 'custom_appearance/B.bundle', '_source_address': 'assets/b.prefab'},
        ], include_links=True)
        self.assertEqual([[link['url'] for link in row['author_links']] for row in found], [
            ['https://video.example/a', 'https://pack.example/mod'], ['https://pack.example/mod'],
        ])

    def test_skin_readme_then_package_readme_win_over_framepack_manifest(self):
        path = 'Pack/skins/momoi/manifest.json'
        found = self.read({
            path: {'meta': {'author': 'studio'}},
            'Pack/README.md': '> **作者**: `Full Author Name` | **版本**: 2',
            'Pack/skins/midori/manifest.json': {'meta': {'author': 'different studio'}},
            'Pack/skins/midori/README.md': 'Author: Artist Name',
        }, [
            {'entry': {'private_declaration': {'root': 'pack/skins/momoi', 'personality': '10316'}}},
            {'entry': {'private_declaration': {'root': 'pack/skins/midori', 'personality': '11017'}}},
        ])
        self.assertEqual(found, [('Full Author Name', 'Pack/README.md'),
                                 ('Artist Name', 'Pack/skins/midori/README.md')])

    def test_distinct_nested_sources_do_not_share_credits(self):
        found = self.read({
            'Collection/README.md': 'Author: Pack curator',
            'Collection/A/manifest.json': {'authors': [{'name': 'Alice'}, 'Bob', 'alice']},
            'Collection/B/README.md': 'Thanks to Carol\n\nThird-party assets by Dan',
            'Collection/B/dependencies/credits.txt': 'Author: Dependency author',
        }, [
            {'entry': {}, '_source_member': PurePosixPath('Collection/A/custom_appearance/model.bundle')},
            {'entry': {}, '_source_member': PurePosixPath('Collection/B/custom_appearance/model.bundle')},
        ])
        self.assertEqual(found, [('Alice、Bob', 'Collection/A/manifest.json'), None])

    def test_package_manifest_is_fallback_if_readme_has_no_attribution(self):
        found = self.read({
            'Pack/skins/momoi/manifest.json': {'meta': {}},
            'Pack/pack.json': {'author': 'Manifest Author'},
            'Pack/READ ME.txt': 'Thanks to Another Person',
        }, [{'entry': {'private_declaration': {'root': 'pack/skins/momoi', 'personality': '10316'}}}])
        self.assertEqual(found, [('Manifest Author', 'Pack/pack.json')])

    def test_markdown_and_language_readme_priority_and_link_fallback(self):
        records = [{'entry': {}, '_source_member': 'Pack/custom_appearance/body.bundle'}]
        found = self.read({
            'Pack/README.txt': '作者：TXT Author',
            'Pack/README_CN.md': '作者：Localized Author\n演示视频：https://video.example/translation\n'
                                 '发布页：https://project.example/release',
            'Pack/说明.txt': '作者：Other Author',
            'Pack/README.md': '作者：Markdown Author\n演示视频：https://video.example/main',
            'Pack/docs/README.md': '作者：Documentation Author',
        }, records, include_links=True)
        self.assertEqual(found, [{
            'author': 'Markdown Author', 'imported_author_source': 'Pack/README.md',
            'author_links': [
                {'url': 'https://video.example/main', 'label': '演示视频'},
                {'url': 'https://project.example/release', 'label': '发布页'},
            ],
        }])

    def test_ambiguous_language_readmes_do_not_select_an_author(self):
        records = [{'entry': {}, '_source_member': 'Pack/custom_appearance/body.bundle'}]
        files = [('Pack/README.en.md', 'Author: One'), ('Pack/README.zh-CN.md', 'Author: Two'),
                 ('Pack/README.txt', 'Author: Fallback')]
        for documents in (files, reversed(files)):
            self.assertEqual(self.read(dict(documents), records), [None])

    def test_only_associated_docs_readme_is_used_as_fallback(self):
        found = self.read({
            'Pack/docs/README.md': '作者：Documented Author',
            'Pack/dependency/docs/README.md': '作者：Dependency Author',
            'Pack/pack.json': {'author': 'Package Author'},
        }, [{'entry': {}, '_source_member': 'Pack/custom_appearance/body.bundle'}])
        self.assertEqual(found, [('Documented Author', 'Pack/docs/README.md')])

    def test_personality_author_applies_only_to_the_matching_declaration(self):
        path = 'Pack/custom_limbus_data/personality/units.json'
        found = self.read({
            path: {'list': [{'id': 123, 'authors': ['甲', '乙']}, {'id': 456}]},
            'Pack/credits.txt': '# Private server mod\n- **作者：** 丙',
        }, [
            {'entry': {'private_declaration': {'root': 'pack', 'personality': '123'}}},
            {'entry': {'private_declaration': {'root': 'pack', 'personality': '456'}}},
        ])
        self.assertEqual(found, [('甲、乙', path), ('丙', 'Pack/credits.txt')])

    def test_readme_author_links_references_autolinks_and_dependency_sections(self):
        found = self.read({
            'Pack/README.md': '''> **作者**: [`Full Author`][home] | 版本 2

## 演示与下载
[演示视频][demo]
下载镜像：<https://downloads.example/mod?code=3&from=archive>
[项目主页][]
学习工具请参阅 [UnityPy](https://github.com/K0lb3/UnityPy)。

## Credits
Author: Upstream Author
[项目主页][unity]

[home]: <https://author.example/profile> "作者主页"
[demo]: https://video.example/demo?v=5 "Demo"
[项目主页]: https://project.example/mod
[unity]: https://github.com/K0lb3/UnityPy
''',
        }, [{'entry': {}, '_source_member': 'Pack/custom_appearance/body.bundle'}], include_links=True)
        self.assertEqual(found, [{
            'author': 'Full Author', 'imported_author_source': 'Pack/README.md', 'author_links': [
                {'url': 'https://author.example/profile', 'label': '作者主页'},
                {'url': 'https://video.example/demo?v=5', 'label': '演示视频'},
                {'url': 'https://downloads.example/mod?code=3&from=archive', 'label': '下载镜像'},
                {'url': 'https://project.example/mod', 'label': '项目主页'},
            ],
        }])

    def test_explicit_download_and_generic_link_sections(self):
        found = self.read({
            'README.md': '''## 相关链接
- [点击查看][site]

## Links
- [Mod page](https://listing.example/mod)
- [Download](https://archive.example/mod?code=1)

## Prerequisites
- [Download](https://dependency.example/tools)

[site]: https://project.example/mod
''',
        }, [{'entry': {}, '_source_member': 'custom_appearance/body.bundle'}], include_links=True)
        self.assertEqual(found, [{'author_links': [
            {'url': 'https://project.example/mod', 'label': '点击查看'},
            {'url': 'https://listing.example/mod', 'label': 'Mod page'},
            {'url': 'https://archive.example/mod?code=1', 'label': 'Download'},
        ]}])

    def test_only_current_prefab_claims_per_appearance_metadata(self):
        path = 'mos-skin.json'
        found = self.read({
            path: {'schema': 1, 'author': 'Bundle author',
                   'appearances': {'Assets/A.prefab': {'authors': ['A', 'A2']},
                                   'Assets/B.prefab': {}}},
        }, [
            {'entry': {}, '_source_member': PurePosixPath('custom_appearance/a.bundle'),
             '_source_address': 'assets/a.prefab'},
            {'entry': {}, '_source_member': PurePosixPath('custom_appearance/b.bundle'),
             '_source_address': 'assets/b.prefab'},
        ])
        self.assertEqual(found, [('A、A2', path), ('Bundle author', path)])

    def test_carra2_uses_original_member_scope(self):
        first = 'ExpandedOne/Installation/hash/otherhash/__data'
        second = 'ExpandedTwo/Installation/hash/otherhash/__data'
        found = self.read({
            'Pack/README.md': 'Author: Curator',
            'Pack/PartOne/credits.txt': 'Author: One',
            'Pack/PartTwo/credits.txt': 'Author: Two',
        }, [
            {'entry': {}, '_source_member': first},
            {'entry': {}, '_source_member': second},
        ], expanded_members={first.casefold(): 'Pack/PartOne/ExpandedOne.carra2',
                             second.casefold(): 'Pack/PartTwo/ExpandedTwo.carra2'})
        self.assertEqual(found, [('One', 'Pack/PartOne/credits.txt'), ('Two', 'Pack/PartTwo/credits.txt')])

    def test_document_line_must_explicitly_name_the_author(self):
        found = self.read({
            'README.md': '# Hero by Studio\nContributors: Preview Only\n'
                         '```\nAuthor: Example\n```\nCopyright: Project Moon',
            'credits.txt': 'Special thanks: Someone',
        }, [{'entry': {}, '_source_member': PurePosixPath('custom_appearance/test.bundle')}])
        self.assertEqual(found, [None])


if __name__ == '__main__':
    unittest.main()
