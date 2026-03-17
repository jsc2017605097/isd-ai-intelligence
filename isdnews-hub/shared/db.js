const Database = require('better-sqlite3');
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../.env') });

const sourceDb = new Database(process.env.SOURCE_DB_PATH, { readonly: true, fileMustExist: true });
const hubDb = new Database(process.env.HUB_DB_PATH);

hubDb.exec(`
CREATE TABLE IF NOT EXISTS article_related (
  article_id INTEGER NOT NULL,
  related_id INTEGER NOT NULL,
  score REAL NOT NULL,
  PRIMARY KEY (article_id, related_id)
);
CREATE TABLE IF NOT EXISTS digest_daily (
  digest_date TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS article_keywords (
  article_id INTEGER NOT NULL,
  keyword TEXT NOT NULL,
  weight REAL NOT NULL,
  PRIMARY KEY (article_id, keyword)
);
CREATE TABLE IF NOT EXISTS topic_daily (
  topic_date TEXT NOT NULL,
  keyword TEXT NOT NULL,
  score REAL NOT NULL,
  PRIMARY KEY (topic_date, keyword)
);
CREATE TABLE IF NOT EXISTS tts_text_cache (
  article_id INTEGER NOT NULL,
  lang TEXT NOT NULL,
  tts_text TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (article_id, lang)
);
`);

module.exports = { sourceDb, hubDb };
