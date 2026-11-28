const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../MirrorOfSkin/Workbench/ui/index.html'), 'utf8');
const start = html.indexOf('      function importResult(');
const end = html.indexOf('      async function followImport(', start);
assert(start >= 0 && end > start);
const context = vm.createContext({dialogueDetectionText: () => ''});
vm.runInContext(html.slice(start, end), context);
const report = context.importResult;

const unbound = {kind: 'voice', name: '未知语音', status: 'added',
  voice_binding_status: 'unknown_owner', targets: [], playable_banks: ['voice.bank'], connected_to: []};
const bound = {kind: 'voice', name: '可用语音', status: 'existing',
  voice_binding_status: 'bound', connected_to: ['已导入外观']};
const unmatched = {kind: 'voice', name: '等待外观', status: 'added',
  voice_binding_status: 'unmatched', targets: ['10315'], connected_to: []};

const one = report({stage: 'done', rows: [unbound]});
assert.match(one.summary, /语音已收录，尚未绑定外观/);
assert.match(one.text, /未识别对应人格或外观/);
assert.doesNotMatch(one.summary + one.text, /成功|已播放/);

const batch = report({stage: 'done', rows: [unbound, bound, unmatched], files: [
  {filename: 'unknown.zip', rowStart: 0, rowCount: 1},
  {filename: 'bound.zip', rowStart: 1, rowCount: 1},
  {filename: 'waiting.zip', rowStart: 2, rowCount: 1},
]});
assert.match(batch.summary, /语音已绑定 1 项/);
assert.match(batch.summary, /语音待绑定 2 项/);
assert.match(batch.text, /unknown\.zip：仅收录，尚未绑定外观/);
assert.match(batch.text, /已绑定到外观：已导入外观/);
assert.match(batch.text, /未匹配到唯一可绑定的外观/);

const legacy = report({stage: 'done', rows: [{kind: 'voice', name: '缺素材',
  status: 'added', targets: ['10101'], playable_banks: [], connected_to: []}]});
assert.match(legacy.text, /未确认完整的 FMOD 事件库和音频素材/);

const mixed = report({stage: 'done', rows: [{name: '新外观', status: 'added'}, unbound],
  errors: ['读包失败'], files: [
    {filename: 'mixed.zip', rowStart: 0, rowCount: 2},
    {filename: 'broken.zip', rowStart: 2, rowCount: 0, error: '读包失败'},
  ]});
assert.match(mixed.summary, /部分失败.*语音待绑定 1 项/);
assert.match(mixed.text, /mixed\.zip：已处理，部分语音待绑定\n  新外观 已加入/);
assert.match(mixed.text, /broken\.zip：失败 · 读包失败/);
const current = {name: '自描述外观', status: 'existing', version: '1.0.0', unchanged: true};
const unchanged = report({stage: 'done', rows: [current]});
assert.match(unchanged.summary, /已是最新版本：1 项/);
assert.match(unchanged.text, /版本 1\.0\.0，未变化/);
const withPending = report({stage: 'done', rows: [current, unmatched]});
assert.match(withPending.summary, /语音待绑定 1 项/);
assert.doesNotMatch(withPending.summary, /已是最新版本/);
assert.match(withPending.text, /版本 1\.0\.0，未变化/);
console.log('PASS voice import reports distinguish bound, unknown, unmatched and incomplete banks');
