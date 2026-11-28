// Set NODE_PATH to the bundled node_modules; optionally set BROWSER_PATH.
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { chromium } = require('playwright');

async function main() {
  const html = fs.readFileSync(path.join(__dirname, '../MirrorOfSkin/Workbench/ui/index.html'), 'utf8');
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : process.platform === 'win32' ? { channel: 'msedge' } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 400, height: 900 } });
    await context.route('**/*', route => route.abort());
    const page = await context.newPage();
    await page.setContent(html);
    const result = await page.evaluate(() => {
      const id = 'story_WBImp_123456789012345678901234';
      data = { activeRule: {}, catalog: [{ identity_id:id, name:'测试', author:'', chapter:'custom', author_links:[
        {url:'http://example.invalid/project',label:'https://example.invalid/project'},
        {url:'https://example.invalid/watch',label:'演示视频'},
        {url:'https://example.invalid/third',label:'例子.中国'},
        {url:'https://example.invalid/fourth',label:'<img src=x>'},
        {url:'javascript:alert(1)',label:'坏'}, {url:'https://user:pass@example.invalid/',label:'坏'},
        {url:'/relative',label:'坏'}, {url:'file:///tmp/x',label:'坏'},
        {url:'https:foo',label:'坏'}, {url:'https://example.invalid/\\evil',label:'坏'},
        {url:'https://example.invalid/' + String.fromCharCode(10) + 'evil',label:'坏'},
      ] }] };
      selected = new Map([[id,1]]);
      render();
      const card = document.querySelector('.pool-card[data-id]');
      let bubbled = 0;
      document.querySelector('#poolGrid').addEventListener('click', () => bubbled++);
      document.querySelector('#poolGrid').addEventListener('contextmenu', () => bubbled++);
      card.querySelector('summary').click();
      const links = [...card.querySelectorAll('.author-links a')];
      links[0].dispatchEvent(new MouseEvent('contextmenu', {bubbles:true, cancelable:true}));
      return { count:links.length, labels:links.map(a=>a.textContent), attrs:links.map(a=>[a.target,a.rel,a.draggable]), bubbled, author:card.querySelector('.pool-source').textContent, injected:!!card.querySelector('.author-links img'), positions:links.map(a=>({w:a.getBoundingClientRect().width, parent:a.parentElement.getBoundingClientRect().width})) };
    });
    assert.strictEqual(result.count, 4);
    assert.strictEqual(await page.locator('.author-links > a').textContent(), '演示视频');
    assert.strictEqual(await page.evaluate(() => authorLinks({author_links:[{url:'https://example.invalid/',label:'主页'}]}).includes('<details>')), false);
    assert.deepStrictEqual(result.labels, ['演示视频','作者链接','作者链接','<img src=x>']);
    assert(result.attrs.every(([target, rel, draggable]) => target === '_blank' && rel === 'noopener noreferrer' && !draggable));
    assert.strictEqual(result.bubbled, 0);
    assert(result.author.includes('未注明或未识别'));
    assert(!result.injected && result.positions.every(p => p.w <= p.parent));
    const summary = page.locator('.author-links summary');
    await summary.focus();
    await page.keyboard.press('Enter');
    assert.strictEqual(await page.locator('.author-links details').evaluate(el => el.open), false);
    await page.keyboard.press('Enter');
    assert.strictEqual(await page.locator('.author-links details').evaluate(el => el.open), true);
    await page.locator('.author-links a').first().focus();
    const popupPromise = page.waitForEvent('popup');
    await page.keyboard.press('Enter');
    const popup = await popupPromise;
    await popup.waitForLoadState().catch(() => {});
    assert.strictEqual(await popup.evaluate(() => window.opener === null), true);
    await popup.close();
    console.log('PASS: filtered links, readable labels, keyboard, isolation, no external requests, 400px layout');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exit(1); });
