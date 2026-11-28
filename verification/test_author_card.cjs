const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const page = path.join(__dirname, '..', 'MirrorOfSkin', 'Workbench', 'ui', 'index.html');
const html = fs.readFileSync(page, 'utf8').replace(/\r\n/g, '\n');
function section(start, end) {
  const first = html.indexOf(start);
  assert(first >= 0, `Missing start marker: ${start}`);
  const last = html.indexOf(end, first + start.length);
  assert(last > first, `Missing end marker: ${end}`);
  return html.slice(first, last);
}
const code = [
  section('      const esc = (v) =>', '      const who ='),
  section('      function isImportedIdentity(', '      function rulesetCard('),
  section('      function render() {', '      let poolEditVersion ='),
].join('\n');
const cases = [
  { identity_id: 'story_WBImp_123456789012345678901234', chapter: 'custom', name: '自建章节', author: '<img src=x onerror=alert(1)>作者'.repeat(12) },
  { identity_id: 'story_BRolandBaseAppearance', name: '缺省', author: '' },
  { identity_id: 'normal', name: '内置', appearance_name: '内置代码', chapter_label: '第一章', author: '不应显示' },
];
const grid = { innerHTML: '', querySelectorAll: () => [] };
const context = {
  data: { activeRule: {}, catalog: cases },
  selected: new Map(cases.map(entry => [entry.identity_id, 1])),
  $: () => grid,
  catalogChapters: () => new Map(),
  updatePoolSummary: () => {},
};
vm.runInNewContext(code + '\nrender()', context);
const output = grid.innerHTML;
assert(output.includes('作者：&lt;img src=x onerror=alert(1)&gt;'));
assert(!output.includes('<img src=x'));
assert(output.includes('未注明或未识别'));
assert(output.includes('外来人格'));
assert(!output.includes('不应显示'));
assert(output.includes('内置代码'));
assert(output.includes('pool-add'));
assert(html.includes('.pool-source.is-imported span { display: block; overflow: hidden; text-overflow: ellipsis; }'));
console.log('PASS: actual render function, custom chapter, long escaped author, missing author, built-in and add card');
