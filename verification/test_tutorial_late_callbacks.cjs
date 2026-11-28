// Simulate delayed layout and data responses after a player leaves a tutorial step.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../MirrorOfSkin/Workbench/ui/index.html'), 'utf8');
function functionSource(name) {
  const lines = html.split(/\r?\n/);
  const start = lines.findIndex(line => new RegExp('^      (?:async )?function '+name+'\\(').test(line));
  assert.ok(start >= 0, name);
  const end = lines.findIndex((line, i) => i > start && line === '      }');
  assert.ok(end > start, name);
  return lines.slice(start, end + 1).join('\n');
}
async function main() {
  for (const nextState of ['finished', 'advanced']) {
    for (const opener of ['openIdentityModal', 'openChapterModal', 'openImportedModal']) {
      const step = {};
      let resolveData;
      const response = new Promise(resolve => { resolveData = resolve; });
      const context = vm.createContext({
        tutorialSteps: [step, {}], tutorialOpen: true, tutorialIndex: 0,
        data: {catalog: ['initial']}, api: () => response,
        $: () => { throw new Error('A stale tutorial callback touched the UI'); },
      });
      vm.runInContext(['isCurrentTourStep', 'positionTour', opener].map(functionSource).join('\n'), context);
      const pending = context[opener](step);
      context.tutorialOpen = nextState === 'advanced';
      context.tutorialIndex = nextState === 'advanced' ? 1 : -1;
      context.positionTour(step, null);
      resolveData({catalog: ['stale']});
      await pending;
      assert.deepEqual(context.data.catalog, ['initial']);
    }
  }
  console.log('PASS: late tutorial layout and modal responses after finish or advance');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
