// Set NODE_PATH to the bundled node_modules directory and optionally BROWSER_PATH.
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { chromium } = require('playwright');

async function main() {
  const html = fs.readFileSync(path.join(__dirname, '../MirrorOfSkin/Workbench/ui/index.html'), 'utf8');
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : process.platform === 'win32' ? { channel: 'msedge' } : {}),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    await page.route('**/*', route => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
    await page.setContent(html);
    const actual = await page.evaluate(() => {
      // Clone the symbol into a visible SVG so getBBox measures rendered shapes.
      const symbol = document.querySelector('#i-skin-import');
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 24 24');
      svg.style.cssText = 'position:fixed;left:0;top:0;width:24px;height:24px';
      svg.innerHTML = symbol.innerHTML;
      document.body.append(svg);
      const circle = svg.querySelector('circle').getBBox();
      const arrow = svg.querySelector('path').getBBox();
      const rect = box => ({ x: box.x, y: box.y, width: box.width, height: box.height });
      const buttons = ['headerImportLocalSkin', 'importLocalSkin'].map(id => {
        const button = document.getElementById(id);
        return { hint: button.title, href: button.querySelector('use').getAttribute('href') };
      });
      const mixed = importResult({
        stage: 'done',
        rows: [{name:'外观甲',status:'added'}, {name:'外观乙',status:'updated'}],
        errors: ['坏包：<img src=x>'],
        files: [
          {filename:'<b>好包</b>',rowStart:0,rowCount:2,error:''},
          {filename:'坏包',rowStart:2,rowCount:0,error:'<img src=x>'},
        ],
      });
      const legacy = importResult({stage:'done', rows:[{name:'旧外观',status:'existing'}], errors:[]});
      const single = importResult({
        stage:'done', rows:[{name:'单包外观',status:'added',package_directory:'目录'}], errors:[],
        files:[{filename:'单包',rowStart:0,rowCount:1,error:''}],
      });
      showImport({stage:'importing',filename:'<img src=x>',done:1,total:3,percent:40});
      document.querySelector('#importDetailsText').textContent = mixed.text;
      return {
        circle: rect(circle), arrow: rect(arrow), buttons, mixed, legacy, single,
        progress: document.querySelector('#importNoticeText').textContent,
        injected: !!document.querySelector('#importNotice img, #importDetailsText b'),
      };
    });
    for (const shape of [actual.circle, actual.arrow]) {
      assert(shape.width > 0 && shape.height > 0, 'Icon geometry must be nonzero');
    }
    assert.strictEqual(actual.circle.x + actual.circle.width / 2, actual.arrow.x + actual.arrow.width / 2);
    assert.strictEqual(actual.circle.y + actual.circle.height / 2, actual.arrow.y + actual.arrow.height / 2);
    assert(actual.buttons.every(button => button.hint.includes('Ctrl') && button.hint.includes('Shift') && button.href === '#i-skin-import'));
    assert(actual.mixed.summary.includes('部分失败'));
    assert(actual.mixed.text.includes('<b>好包</b>：成功\n  外观甲 已加入\n  外观乙 已更新'));
    assert(actual.mixed.text.includes('坏包：失败 · <img src=x>'));
    assert(actual.legacy.text.includes('旧外观'));
    assert(actual.single.text.includes('文件夹：目录'));
    assert(actual.progress.includes('文件 2/3') && actual.progress.includes('<img src=x>'));
    assert(!actual.injected);
    console.log('PASS: rendered Edge icon geometry, import hints, batch and legacy details, progress and text injection');
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exit(1); });
