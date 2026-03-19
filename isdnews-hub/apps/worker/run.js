const path = require('path');
const dayjs = require('dayjs');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });
const { sourceDb, hubDb } = require('../../shared/db');

const STOPWORDS = new Set([
  'the','and','for','that','with','from','this','have','will','your','into','about','trong','những','các','được','theo','của','cho','với','một','khi','đang','đến','này','là','và'
]);

function cleanText(s = '') {
  return s
    .replace(/<[^>]*>/g, ' ')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/&[a-z]+;/gi, ' ');
}

function tokenize(s = '') {
  const t = cleanText(s);
  return new Set(
    t.toLowerCase()
      .replace(/[^\p{L}\p{N}\s]/gu, ' ')
      .split(/\s+/)
      .filter((w) => w.length > 3 && !STOPWORDS.has(w))
  );
}

function keywordScores(s = '') {
  const t = cleanText(s);
  const words = t.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/)
    .filter((w) => w.length > 3 && !STOPWORDS.has(w));
  const map = new Map();
  for (const w of words) map.set(w, (map.get(w) || 0) + 1);
  return [...map.entries()].sort((a,b)=>b[1]-a[1]);
}

function jaccard(a, b) {
  let inter = 0;
  for (const x of a) if (b.has(x)) inter++;
  const uni = a.size + b.size - inter;
  return uni ? inter / uni : 0;
}

function computeRelated() {
  const articles = sourceDb.prepare(`
    SELECT id, title, published_at, COALESCE(NULLIF(ai_content,''), summary, content, '') as text
    FROM collector_article
    ORDER BY published_at DESC
    LIMIT 400
  `).all();

  const tokens = new Map(articles.map((a) => [a.id, tokenize(`${a.title} ${a.text}`)]));
  const insert = hubDb.prepare('INSERT OR REPLACE INTO article_related(article_id,related_id,score) VALUES (?,?,?)');
  const del = hubDb.prepare('DELETE FROM article_related WHERE article_id=?');

  const tx = hubDb.transaction(() => {
    for (const a of articles.slice(0, 150)) {
      del.run(a.id);
      const scored = [];
      for (const b of articles) {
        if (a.id === b.id) continue;
        const sim = jaccard(tokens.get(a.id), tokens.get(b.id));
        const ageHours = Math.abs(new Date(a.published_at) - new Date(b.published_at)) / 36e5;
        const recencyBoost = Math.max(0, 1 - (ageHours / (24 * 7))) * 0.12; // gần nhau trong 7 ngày được ưu tiên
        const s = sim + recencyBoost;
        if (s >= 0.10) scored.push({ id: b.id, s });
      }
      scored.sort((x, y) => y.s - x.s).slice(0, 8).forEach((r) => insert.run(a.id, r.id, r.s));
    }
  });
  tx();
  return Math.min(150, articles.length);
}

function computeKeywords() {
  const today = dayjs().format('YYYY-MM-DD');
  const articles = sourceDb.prepare(`
    SELECT id, title, COALESCE(NULLIF(ai_content,''), summary, content, '') AS text, published_at
    FROM collector_article
    ORDER BY published_at DESC
    LIMIT 300
  `).all();

  const delKw = hubDb.prepare('DELETE FROM article_keywords WHERE article_id=?');
  const insKw = hubDb.prepare('INSERT OR REPLACE INTO article_keywords(article_id, keyword, weight) VALUES (?,?,?)');

  const topicCounter = new Map();
  const fallbackCounter = new Map();

  const tx = hubDb.transaction(() => {
    for (const a of articles) {
      delKw.run(a.id);
      const top = keywordScores(`${a.title} ${a.text}`).slice(0, 8);
      top.forEach(([k, w]) => insKw.run(a.id, k, w));

      const isRecent = new Date(a.published_at) >= new Date(Date.now() - 24*3600*1000);
      top.slice(0,5).forEach(([k, w]) => fallbackCounter.set(k, (fallbackCounter.get(k) || 0) + w));
      if (isRecent) {
        top.slice(0,5).forEach(([k, w]) => topicCounter.set(k, (topicCounter.get(k) || 0) + w));
      }
    }

    const finalCounter = topicCounter.size ? topicCounter : fallbackCounter;
    hubDb.prepare('DELETE FROM topic_daily WHERE topic_date=?').run(today);
    const insTopic = hubDb.prepare('INSERT OR REPLACE INTO topic_daily(topic_date, keyword, score) VALUES (?,?,?)');
    [...finalCounter.entries()].sort((a,b)=>b[1]-a[1]).slice(0, 20).forEach(([k,s]) => insTopic.run(today, k, s));
  });

  tx();
  return { today, topics: topicCounter.size };
}

function buildDigest() {
  const today = dayjs().format('YYYY-MM-DD');
  let rows = sourceDb.prepare(`
    SELECT a.title, a.url, a.published_at, COALESCE(NULLIF(a.ai_content,''), a.summary, a.content, '') AS txt,
           t.name AS team_name, s.source AS source_name
    FROM collector_article a
    JOIN collector_source s ON s.id=a.source_id
    LEFT JOIN collector_team t ON t.id=s.team_id
    WHERE datetime(a.published_at) >= datetime('now', '-24 hours', 'localtime')
    ORDER BY a.published_at DESC
    LIMIT 60
  `).all();

  if (!rows.length) {
    rows = sourceDb.prepare(`
      SELECT a.title, a.url, a.published_at, COALESCE(NULLIF(a.ai_content,''), a.summary, a.content, '') AS txt,
             t.name AS team_name, s.source AS source_name
      FROM collector_article a
      JOIN collector_source s ON s.id=a.source_id
      LEFT JOIN collector_team t ON t.id=s.team_id
      ORDER BY a.published_at DESC
      LIMIT 40
    `).all();
  }

  const byTeam = {};
  const bySource = {};
  for (const r of rows) {
    const team = r.team_name || 'Chung';
    byTeam[team] = byTeam[team] || [];
    byTeam[team].push(r);

    bySource[r.source_name] = (bySource[r.source_name] || 0) + 1;
  }

  const lines = [];
  lines.push(`Daily News Digest (${today})`);
  lines.push('');
  lines.push(`Total new articles (24h): ${rows.length}`);
  lines.push('');

  if (!rows.length) {
    lines.push('No new articles found in the last 24 hours.');
  } else {
    lines.push('Top active sources:');
    Object.entries(bySource).sort((a,b)=>b[1]-a[1]).slice(0,5)
      .forEach(([src,c],i)=>lines.push(`${i+1}. ${src} (${c} articles)`));
    lines.push('');

    Object.entries(byTeam).sort((a,b)=>b[1].length-a[1].length).forEach(([team, items]) => {
      lines.push(`## ${team} (${items.length} articles)`);
      items.slice(0, 4).forEach((x, i) => lines.push(`${i + 1}. ${x.title}`));
      lines.push('');
    });

    lines.push('Top headlines:');
    rows.slice(0, 10).forEach((x) => lines.push(`- ${x.title}`));
  }

  const title = `Daily Digest - ${today}`;
  const content = lines.join('\n');

  hubDb.prepare('INSERT OR REPLACE INTO digest_daily(digest_date,title,content) VALUES (?,?,?)')
    .run(today, title, content);

  return { today, count: rows.length };
}

const relatedCount = computeRelated();
const kw = computeKeywords();
const digest = buildDigest();
console.log(`[worker] related=${relatedCount} | keywords=${kw.topics} | digest=${digest.today} items=${digest.count}`);
