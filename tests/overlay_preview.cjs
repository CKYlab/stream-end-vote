const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const elements = new Map();
const context = {
  document: { getElementById(id) {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, { hidden: true, style: {}, offsetWidth: 360, offsetHeight: 240,
        classList: { add: c => classes.add(c), remove: c => classes.delete(c),
          contains: c => classes.has(c), toggle(c, value) { value ? classes.add(c) : classes.delete(c); } } });
    }
    return elements.get(id);
  } },
  innerWidth: 1920, innerHeight: 1080, addEventListener() {}, setInterval() {},
  fetch: async () => ({ ok: true, json: async () => ({ visible: false }) }),
};
vm.createContext(context);
const html = fs.readFileSync(path.join(__dirname, '..', 'overlay.html'), 'utf8');
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
context.state = { visible: false, preview_mode: 'vote', vote_panel_x: 100 };
vm.runInContext('render(state)', context);
assert.equal(elements.get('overlay').classList.contains('hidden'), false);
assert.equal(elements.get('endVotes').textContent, 14);
assert.equal(elements.get('continueVotes').textContent, 6);
assert.match(elements.get('decision').textContent, /プレビュー/);
assert.equal(elements.get('countdown').hidden, true);
assert.equal(context.state.visible, false);
context.state.preview_mode = 'countdown';
vm.runInContext('render(state)', context);
assert.equal(elements.get('countdown').hidden, false);
assert.equal(elements.get('overlay').classList.contains('hidden'), true);
assert.match(elements.get('countdownMain').textContent, /30秒/);
assert.match(elements.get('countdownSub').textContent, /プレビュー/);
context.state.preview_mode = 'none';
vm.runInContext('render(state)', context);
assert.equal(elements.get('countdown').hidden, true);
assert.equal(elements.get('overlay').classList.contains('hidden'), true);
