const fs = require('fs');
const path = require('path');
const assert = require('assert');
const {chromium} = require('playwright');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.BROWSER_PATH});
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.abort());
    await page.setContent(fs.readFileSync(path.join(__dirname,'../MirrorOfSkin/Workbench/ui/index.html'),'utf8'));
    await page.evaluate(() => {
      data = {activeRule:{},catalog:[{identity_id:'one',name:'一'},{identity_id:'two',name:'二'}],blood_visible_ids:[]};
      selected = new Map([['one',2],['two',3]]); render(); document.querySelector('#poolGrid').closest('section').classList.remove('hidden');
      window.calls=[]; api=async (route,body) => {if (route === 'appearance-blood') window.calls.push({route,body}); return {blood_visible_ids:body.visible?[body.identity_id]:[]};};
    });
    await page.locator('[data-id=one].pool-card').click({button:'right'});
    let item=page.locator('#identityMenu [data-action=blood]');
    assert.strictEqual(await item.getAttribute('aria-checked'),'false');
    await item.click();
    await page.waitForFunction(() => window.calls.length===1);
    assert.deepStrictEqual(await page.evaluate(()=>window.calls[0]),{route:'appearance-blood',body:{identity_id:'one',visible:true}});
    await page.locator('[data-id=one].pool-card').focus(); await page.keyboard.press('Shift+F10');
    assert.strictEqual(await item.getAttribute('aria-checked'),'true'); await page.keyboard.press('Enter');
    await page.waitForFunction(() => window.calls.length===2);
    assert.deepStrictEqual(await page.evaluate(()=>window.calls[1].body),{identity_id:'one',visible:false});
    await page.locator('[data-id=two].pool-card').click({button:'right'});
    assert.strictEqual(await item.getAttribute('aria-checked'),'false');
    assert.deepStrictEqual(await page.evaluate(()=>[...selected]),[['one',2],['two',3]]);
    console.log('PASS: per-appearance blood toggle, API, default, keyboard and weight preservation');
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
