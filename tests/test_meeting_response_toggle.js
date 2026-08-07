'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
    path.join(__dirname, '..', 'app', 'game.js'),
    'utf8'
);
const start = source.indexOf('function toggleMtgResponse(');
assert.notEqual(start, -1, 'Missing production function toggleMtgResponse');
const bodyStart = source.indexOf('{', start);
let depth = 0;
let end = -1;
for (let index = bodyStart; index < source.length; index++) {
    if (source[index] === '{') depth++;
    if (source[index] === '}') {
        depth--;
        if (depth === 0) {
            end = index + 1;
            break;
        }
    }
}
assert.notEqual(end, -1, 'Unterminated production function toggleMtgResponse');

function createClassList() {
    const values = new Set();
    return {
        contains: (name) => values.has(name),
        toggle: (name, force) => {
            const enabled = force === undefined ? !values.has(name) : force;
            if (enabled) values.add(name);
            else values.delete(name);
            return enabled;
        },
    };
}

test('meeting response Expand toggles open then closed', () => {
    const response = { classList: createClassList() };
    const button = { textContent: '▼ expand' };
    const context = vm.createContext({
        document: { getElementById: () => response },
    });
    vm.runInContext(`${source.slice(start, end)}\nglobalThis.toggleMtgResponse = toggleMtgResponse;`, context);

    assert.equal(context.toggleMtgResponse('response-1', button), true);
    assert.equal(response.classList.contains('expanded'), true);
    assert.equal(button.textContent, '▲ collapse');

    assert.equal(context.toggleMtgResponse('response-1', button), false);
    assert.equal(response.classList.contains('expanded'), false);
    assert.equal(button.textContent, '▼ expand');
});
