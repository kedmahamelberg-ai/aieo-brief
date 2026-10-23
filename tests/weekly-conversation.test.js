'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const Core = require('../assets/core.js');

test('weekly news and research load their own discussions', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../assets/app.js'), 'utf8');
  const line = source.split('\n').find(s => s.startsWith(' async function comments(){'));
  assert.ok(line);
  function section(key) {
    const status = {textContent: ''}, signin = {hidden: false};
    const form = {hidden: true}, list = {rows: [], replaceChildren(...rows) { this.rows = rows; }};
    const fields = {
      '[data-community-status]': status, '[data-comment-signin]': signin,
      '[data-comment-form]': form, '[data-comments-list]': list,
    };
    return {dataset: {key}, status, signin, form, list, querySelector: selector => fields[selector]};
  }
  const news = section('weekly:2026-W42:markets');
  const research = section('weekly:2026-W42:research');
  const calls = [];
  const Community = {
    enabled: true, signedIn: () => true,
    rpc: async (name, args) => {
      assert.equal(name, 'brief_community_comments_for');
      calls.push(args.p_story_key);
      return args.p_story_key === news.dataset.key ? [{id: 1}, {id: 2}, {id: 3}] : [{id: 4}];
    },
  };
  await vm.runInNewContext(line + ';comments();', {
    document: {querySelectorAll: () => [news, research]}, Community, Core,
    commentNode: row => row,
  });
  assert.deepEqual(calls, [news.dataset.key, research.dataset.key]);
  assert.equal(news.list.rows.length, 3);
  assert.equal(research.list.rows.length, 1);
  assert.equal(news.status.textContent, '3 approved comments');
  assert.equal(research.status.textContent, 'Join the conversation.');
  assert.equal(news.form.hidden, false);
  assert.equal(research.form.hidden, false);
});
