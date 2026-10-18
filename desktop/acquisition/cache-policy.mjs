// Integration policy for the pinned Wigolo 0.2.1 cache connection.
export function prepareCacheConnection(db) {
  // INSERT OR REPLACE must fire the upstream FTS delete trigger as well as insert.
  db.pragma("recursive_triggers = ON");
  const check = () => db.prepare(
    "INSERT INTO url_cache_fts(url_cache_fts, rank) VALUES('integrity-check', 1)"
  ).run();
  try {
    check();
  } catch (error) {
    if (error.code !== "SQLITE_CORRUPT_VTAB") throw error;
    // Repair only a derived index over an otherwise intact cache. Never discard
    // URL content, vectors, migrations or the upstream database on a core error.
    const integrity = db.pragma("integrity_check");
    if (integrity.length !== 1 || integrity[0].integrity_check !== "ok") {
      throw new Error("Wigolo cache integrity failed; derived index repair refused");
    }
    db.transaction(() => {
      db.prepare("INSERT INTO url_cache_fts(url_cache_fts) VALUES('rebuild')").run();
      check();
    })();
  }
}
