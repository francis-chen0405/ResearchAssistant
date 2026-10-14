'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

async function fixture(t) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'ra-cache-policy-'));
  fs.chmodSync(temporary, 0o700);
  const { initDatabase, closeDatabase } = await import('./node_modules/wigolo/dist/cache/db.js');
  const db = initDatabase(path.join(temporary, 'cache.db'));
  t.after(() => { closeDatabase(); fs.rmSync(temporary, {recursive:true, force:true}); });
  const { prepareCacheConnection } = await import('./cache-policy.mjs');
  return {db, prepareCacheConnection};
}
const insert = db => db.prepare(`INSERT OR REPLACE INTO url_cache(url,normalized_url,title,markdown,fetched_at) VALUES('https://example.org/a','https://example.org/a',? ,?,'2026-10-13')`);
const check = db => db.prepare("INSERT INTO url_cache_fts(url_cache_fts,rank) VALUES('integrity-check',1)").run();

test('pinned replacement writes reproduce stale FTS; policy repairs only derived index', async t => {
  const {db, prepareCacheConnection} = await fixture(t);
  assert.equal(db.pragma('recursive_triggers', {simple:true}), 0);
  insert(db).run('Old title', 'Old markdown');
  insert(db).run('New title', 'New markdown');
  assert.throws(() => check(db), {code:'SQLITE_CORRUPT_VTAB'});
  db.prepare('INSERT INTO vec_id_map(external_id) VALUES(?)').run('https://example.org/a');
  db.prepare('INSERT INTO vec_documents(rowid,embedding) VALUES(?,?)').run(1n, Buffer.alloc(384*4));
  db.prepare("INSERT INTO vec_metadata(rowid,url,content_hash,model_id,created_at) VALUES(1,'https://example.org/a','hash','fixture',1)").run();
  const retained = () => JSON.stringify(['url_cache','vec_id_map','vec_documents','vec_metadata','schema_migrations'].map(table => db.prepare(`SELECT * FROM ${table}`).all()));
  const before = retained();
  prepareCacheConnection(db);
  check(db);
  assert.equal(retained(), before);
  assert.equal(db.pragma('recursive_triggers', {simple:true}), 1);
  insert(db).run('Third title', 'Third markdown');
  check(db);
  assert.equal(db.prepare('SELECT count(*) n FROM url_cache').get().n, 1);
  assert.equal(db.prepare("SELECT count(*) n FROM url_cache_fts WHERE url_cache_fts MATCH 'Old'").get().n, 0);
  assert.equal(db.prepare("SELECT count(*) n FROM url_cache_fts WHERE url_cache_fts MATCH 'Third'").get().n, 1);
});

test('healthy cache and repeated initialization preserve content and FTS', async t => {
  const {db, prepareCacheConnection} = await fixture(t);
  prepareCacheConnection(db);
  insert(db).run('First', 'First text');
  const before = JSON.stringify(db.prepare('SELECT * FROM url_cache').all());
  prepareCacheConnection(db);
  assert.equal(JSON.stringify(db.prepare('SELECT * FROM url_cache').all()), before);
  insert(db).run('Second', 'Second text');
  check(db);
});

test('unrecognized SQLite errors fail without index rebuild', async () => {
  const { prepareCacheConnection } = await import('./cache-policy.mjs');
  const error = Object.assign(new Error('fixture I/O failure'), {code:'SQLITE_IOERR'});
  const calls = [];
  const db = {pragma(sql) {calls.push(sql);}, prepare(sql) {calls.push(sql); return {run() {throw error;}};}};
  assert.throws(() => prepareCacheConnection(db), error);
  assert.equal(calls.length, 2);
});

test('core corruption refuses derived-index rebuild', async () => {
  const { prepareCacheConnection } = await import('./cache-policy.mjs');
  const calls = [];
  const db = {
    pragma(sql) {calls.push(sql); return [{integrity_check:'fixture damaged page'}];},
    prepare(sql) {calls.push(sql); return {run() {throw Object.assign(new Error('stale index'), {code:'SQLITE_CORRUPT_VTAB'});}};}
  };
  assert.throws(() => prepareCacheConnection(db), /repair refused/);
  assert.equal(calls.length, 3);
});
