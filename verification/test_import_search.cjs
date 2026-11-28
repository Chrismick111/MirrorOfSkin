const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const html = fs.readFileSync(path.join(__dirname, '../MirrorOfSkin/Workbench/ui/index.html'), 'utf8');
  const browser = await chromium.launch({
    ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : process.platform === 'win32' ? { channel: 'msedge' } : {}),
    headless: true,
  });
  try {
    const page = await browser.newPage();
    const chapterErrors = [];
    page.on('pageerror', error => {
      if (error.stack.includes('renderChapterManageList')) chapterErrors.push(error.message);
    });
    await page.setContent(html);
    const result = await page.evaluate(() => {
      const manager = document.querySelector('#chapterManager');
      manager.dispatchEvent(new Event('toggle'));
      data = {
        catalog: [
          { identity_id: '10101', name: '原生人格', chapter: 'stock', chapter_label: '原生章节',
            chapter_memberships: [{ chapter: 'shared', label: '旧名称' }] },
          { identity_id: 'story_WBImp_' + 'a'.repeat(24), name: '缪', import_source: 'RCorp_Myo.v2',
            chapter: 'private', chapter_label: '外来专用章节' },
          { identity_id: 'story_WBImp_' + 'b'.repeat(24), name: '另一外观', import_source: 'another',
            chapter: 'shared', chapter_label: '旧名称' },
        ],
        chapterArt: { shared: { label: '自定义名称' } },
      };
      fillAddFilters();
      refreshChapterManager();
      document.querySelector('#chapterName').value = '编辑中的章节名';
      manager.dispatchEvent(new Event('toggle'));
      const field = document.querySelector('#importedSearch');
      const chapter = document.querySelector('#importedChapter');
      const rows = () => [...document.querySelectorAll('#importedRows .identity-copy strong')].map(el => el.textContent);
      const result = { draft: document.querySelector('#chapterName').value,
        options: [...chapter.options].map(el => [el.value, el.textContent]), matches: [] };
      result.cards = {};
      for (const id of ['private', 'shared', '']) {
        const card = document.querySelector(`#chapterCards [data-chapter="${id}"]`);
        card.click();
        result.cards[id] = {
          count: Number(card.querySelector('small').textContent.match(/\d+/)[0]),
          names: [...document.querySelectorAll('#identityRows .identity-copy strong')].map(el => el.textContent),
        };
      }
      for (const suffix of ['ZIP', '7z', 'RAR', 'carra2', 'bank']) {
        field.value = '  RCorp_Myo.v2.' + suffix + '  ';
        field.dispatchEvent(new Event('input'));
        result.matches.push(rows());
      }
      field.value = '';
      chapter.value = 'private';
      chapter.dispatchEvent(new Event('change'));
      result.inChapter = rows();
      fillAddFilters();
      result.preserved = chapter.value;
      data.catalog = data.catalog.filter(entry => entry.chapter !== 'private');
      fillAddFilters();
      renderImportedList();
      result.afterRemoval = [chapter.value, rows()];
      return result;
    });
    assert.deepEqual(chapterErrors, [], 'the hidden chapter manager must wait for its catalog');
    assert.equal(result.draft, '编辑中的章节名');
    assert.deepEqual(result.cards.private, {count: 1, names: ['缪']});
    assert.deepEqual(result.cards.shared, {count: 2, names: ['原生人格', '另一外观']});
    assert.deepEqual(result.cards[''], {count: 3, names: ['原生人格', '缪', '另一外观']});
    for (const rows of result.matches) assert.deepEqual(rows, ['缪'], 'searching by archive filename');
    assert.deepEqual(new Map(result.options), new Map([['', '全部章节'], ['private', '外来专用章节'], ['shared', '自定义名称']]));
    assert.deepEqual(result.inChapter, ['缪']);
    assert.equal(result.preserved, 'private');
    assert.deepEqual(result.afterRemoval, ['', ['另一外观']]);
    console.log('PASS: full archive name, imported-only chapters, renamed chapter, refresh and removal');
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
