const express = require('express');
const cors = require('cors');
const dayjs = require('dayjs');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { promisify } = require('util');
const { execFile } = require('child_process');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });

const { sourceDb, hubDb } = require('../../shared/db');

const app = express();
app.use(cors({ origin: process.env.CORS_ORIGIN || '*' }));
app.use(express.json({ limit: '1mb' }));

const execFileAsync = promisify(execFile);
const ttsOutDir = path.resolve(__dirname, '../../data/tts');
fs.mkdirSync(ttsOutDir, { recursive: true });
app.use('/audio', express.static(ttsOutDir));

function sanitizeForTTS(text = '') {
  return String(text)
    .replace(/<[^>]*>/g, ' ')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/[_*`#~|<>\[\]{}]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}


function getLLMConfig() {
  const base = (process.env.LLM_BASE_URL || process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434').replace(/\/$/, '');
  const style = (process.env.LLM_API_STYLE || (base.includes('11434') ? 'ollama' : 'openai')).toLowerCase();
  const model = process.env.CHAT_MODEL || process.env.DIGEST_MODEL || process.env.AI_MODEL || 'openai/gpt-oss-20b';
  return { base, style, model };
}

async function llmComplete({ messages, model, temperature = 0.4 }) {
  const cfg = getLLMConfig();
  const m = model || cfg.model;

  if (cfg.style === 'openai' || cfg.style === 'vllm') {
    const endpoint = cfg.base + '/v1/chat/completions';
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: m, messages, temperature, stream: false })
    });
    if (!resp.ok) throw new Error(`LLM ${resp.status}`);
    const data = await resp.json();
    return (data?.choices?.[0]?.message?.content || '').trim();
  }

  const endpoint = cfg.base + '/api/chat';
  const resp = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: m, stream: false, messages, options: { temperature } })
  });
  if (!resp.ok) throw new Error(`LLM ${resp.status}`);
  const data = await resp.json();
  return (data?.message?.content || '').trim();
}

async function vietnamizeWithLocalLLM(text = '') {
  const model = process.env.TTS_PHONETIC_MODEL || process.env.CHAT_MODEL || process.env.AI_MODEL || 'openai/gpt-oss-20b';
  const prompt = `Hãy chuyển các thuật ngữ tiếng Anh trong đoạn văn sau thành phiên âm tiếng Việt dễ đọc cho TTS.\nYêu cầu:\n- Giữ nguyên ý nghĩa câu.\n- Giữ dấu câu (. , ; : ! ?) và xuống dòng hợp lý để ngắt nhịp.\n- Chỉ đổi các từ tiếng Anh kỹ thuật sang cách đọc tiếng Việt (ví dụ API -> ây pi ai, Docker -> đọc cơ).\n- Không thêm giải thích. Chỉ trả về văn bản đã chuyển.\n\nVăn bản:\n${text}`;

  const out = await llmComplete({
    model,
    messages: [{ role: 'user', content: prompt }],
    temperature: 0.1
  });
  return (out || text).trim();
}

function buildArticleQuery(q) {
  const where = ['1=1'];
  const params = {};
  if (q.search) {
    const rawSearch = String(q.search).trim();
    if (/https?:\/\//i.test(rawSearch)) {
      where.push('a.url LIKE @urlsearch');
      params.urlsearch = `%${rawSearch}%`;
      return { where: where.join(' AND '), params };
    }

    const phraseClause = '(a.title LIKE @search OR a.url LIKE @search OR a.content LIKE @search OR a.ai_content LIKE @search)';
    params.search = `%${rawSearch}%`;

    const tokens = String(q.search)
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s]/gu, ' ')
      .split(/\s+/)
      .filter((t) => t.length >= 2)
      .slice(0, 8);

    const tokenClauses = [];
    tokens.forEach((tk, i) => {
      const k = `token${i}`;
      tokenClauses.push(`(LOWER(a.title) LIKE @${k} OR LOWER(a.url) LIKE @${k} OR LOWER(a.content) LIKE @${k} OR LOWER(a.ai_content) LIKE @${k})`);
      params[k] = `%${tk}%`;
    });

    if (tokenClauses.length) {
      where.push(`(${phraseClause} OR ${tokenClauses.join(' OR ')})`);
    } else {
      where.push(phraseClause);
    }
  }
  if (q.team) { where.push('LOWER(t.code)=LOWER(@team)'); params.team = q.team; }
  if (q.source) { where.push('LOWER(s.source)=LOWER(@source)'); params.source = q.source; }
  if (q.dateFrom) { where.push('a.published_at >= @dateFrom'); params.dateFrom = q.dateFrom; }
  if (q.dateTo) { where.push('a.published_at <= @dateTo'); params.dateTo = q.dateTo; }
  if (q.aiProcessed === 'true') where.push('a.is_ai_processed = 1');
  if (q.aiProcessed === 'false') where.push('a.is_ai_processed = 0');

  return { where: where.join(' AND '), params };
}

async function buildDigestWithLLM({ today, rows, rangeDays = 1 }) {
  const rangeLabel = rangeDays === 1 ? '24h gần đây' : `${rangeDays} ngày gần đây`;
  if (!rows?.length) {
    return `Bản tin tổng hợp (${rangeLabel}) - ${today}\n\nChưa có bài mới trong ${rangeLabel}.`;
  }

  const model = process.env.DIGEST_MODEL || process.env.AI_MODEL || process.env.CHAT_MODEL || 'openai/gpt-oss-20b';

  const compactItems = rows.slice(0, 50).map((r, i) => {
    const short = String(r.ai_content || r.summary || r.content || '')
      .replace(/\s+/g, ' ')
      .slice(0, 360);
    return `${i + 1}. [${r.team_name || 'N/A'}|${r.source}] ${r.title}\n   Tóm tắt: ${short}`;
  }).join('\n');

  const prompt = `Bạn là biên tập viên công nghệ. Hãy viết bản tin tổng hợp ${rangeLabel} bằng tiếng Việt cho người mới.

Yêu cầu bắt buộc:
- Dễ hiểu cho người mới, nhưng KHÔNG bỏ các thuật ngữ quan trọng.
- Khi có thuật ngữ (VD: RAG, Kubernetes, SSO, Zero Trust), giữ nguyên thuật ngữ và giải thích ngắn trong ngoặc.
- Trình bày gạch đầu dòng rõ ràng, súc tích, có tính hành động.
- Có phần highlight nội dung CRITICAL (rủi ro, sự cố, bảo mật, downtime, data loss, pháp lý).
- Có phần gợi ý học tập/tìm hiểu tiếp theo (3-5 ý), theo mức nhập môn.
- Không bịa. Nếu thiếu dữ liệu thì nói rõ "chưa đủ dữ liệu".

Định dạng đầu ra (plain text):
1) Toàn cảnh (${rangeLabel}) (4-6 dòng)
2) Ý chính (5-8 bullet)
3) ⚠️ Critical cần chú ý (bullet, nếu không có thì ghi "Chưa thấy cảnh báo critical")
4) Gợi ý học tập tiếp theo (3-5 bullet, có lộ trình từ dễ đến khó)
5) Thuật ngữ nên biết hôm nay (5-10 mục: Thuật ngữ: giải thích ngắn)

Ngày tạo: ${today}
Khoảng tổng hợp: ${rangeLabel}
Dữ liệu tin tức:
${compactItems}`;

  const out = await llmComplete({
    model,
    messages: [{ role: 'user', content: prompt }],
    temperature: 0.2
  });
  return (out || '').trim();
}

app.get('/api/health', (req, res) => res.json({ ok: true }));

app.get('/api/teams', (req, res) => {
  const rows = sourceDb.prepare('SELECT id, code, name FROM collector_team WHERE is_active=1 ORDER BY name').all();
  res.json(rows);
});

app.get('/api/sources', (req, res) => {
  const rows = sourceDb.prepare('SELECT id, source, type, url FROM collector_source WHERE is_active=1 ORDER BY source').all();
  res.json(rows);
});

app.get('/api/articles', (req, res) => {
  const page = Math.max(1, parseInt(req.query.page || '1', 10));
  const pageSize = Math.min(50, Math.max(1, parseInt(req.query.pageSize || '12', 10)));
  const offset = (page - 1) * pageSize;

  const { where, params } = buildArticleQuery({
    search: req.query.q,
    team: req.query.team,
    source: req.query.source,
    dateFrom: req.query.dateFrom,
    dateTo: req.query.dateTo,
    aiProcessed: req.query.aiProcessed,
  });

  const baseFrom = `
    FROM collector_article a
    JOIN collector_source s ON s.id=a.source_id
    LEFT JOIN collector_team t ON t.id=s.team_id
    WHERE ${where}
  `;

  const orderBy = req.query.aiProcessed === 'true'
    ? `COALESCE((SELECT MAX(l.created_at) FROM collector_ailog l WHERE l.url = a.url), a.published_at) DESC, a.id DESC`
    : `a.published_at DESC`;

  const items = sourceDb.prepare(`
    SELECT a.id, a.title, a.url, a.summary, a.ai_content, a.is_ai_processed, a.published_at, a.thumbnail,
           s.source, s.type, t.code AS team_code, t.name AS team_name
    ${baseFrom}
    ORDER BY ${orderBy}
    LIMIT @limit OFFSET @offset
  `).all({ ...params, limit: pageSize, offset });

  const total = sourceDb.prepare(`SELECT COUNT(*) AS c ${baseFrom}`).get(params).c;
  res.json({ page, pageSize, total, items });
});

app.get('/api/articles/:id', (req, res) => {
  const id = Number(req.params.id);
  const article = sourceDb.prepare(`
    SELECT a.id, a.title, a.url, a.summary, a.content, a.ai_content, a.is_ai_processed, a.published_at, a.thumbnail,
           s.source, s.type, t.code AS team_code, t.name AS team_name
    FROM collector_article a
    JOIN collector_source s ON s.id=a.source_id
    LEFT JOIN collector_team t ON t.id=s.team_id
    WHERE a.id=?
  `).get(id);

  if (!article) return res.status(404).json({ error: 'Not found' });

  const related = hubDb.prepare(`
    SELECT r.related_id AS id, r.score
    FROM article_related r WHERE r.article_id=? ORDER BY r.score DESC LIMIT 8
  `).all(id).map((r) => {
    const x = sourceDb.prepare('SELECT id, title, published_at FROM collector_article WHERE id=?').get(r.id);
    return { ...x, score: r.score };
  }).filter(Boolean);

  const keywords = hubDb.prepare('SELECT keyword, weight FROM article_keywords WHERE article_id=? ORDER BY weight DESC LIMIT 8').all(id);

  res.json({ ...article, related, keywords });
});

app.get('/api/digest/today', async (req, res) => {
  try {
    const today = dayjs().format('YYYY-MM-DD');
    const forceRefresh = req.query.refresh === '1' || req.query.refresh === 'true';
    const allowedRanges = new Set([1, 3, 7, 14, 30]);
    const rangeDaysRaw = Number.parseInt(req.query.rangeDays || '1', 10);
    const rangeDays = allowedRanges.has(rangeDaysRaw) ? rangeDaysRaw : 1;
    const rangeLabel = rangeDays === 1 ? '24h gần đây' : `${rangeDays} ngày gần đây`;

    // Đồng bộ bản tin theo bộ lọc hiện tại trên Hub
    const digestFilters = {
      search: req.query.q,
      team: req.query.team,
      source: req.query.source,
      aiProcessed: req.query.aiProcessed,
    };
    const hasFilter = Boolean(digestFilters.search || digestFilters.team || digestFilters.source || digestFilters.aiProcessed);

    // Chỉ cache khi mặc định (1 ngày + không filter) để tránh lệch dữ liệu so với màn hình lọc
    let digest = (!forceRefresh && rangeDays === 1 && !hasFilter)
      ? hubDb.prepare('SELECT * FROM digest_daily WHERE digest_date=?').get(today)
      : null;

    if (!digest) {
      const windowFrom = dayjs().subtract(rangeDays, 'day').format('YYYY-MM-DD HH:mm:ss');
      const windowTo = dayjs().format('YYYY-MM-DD HH:mm:ss');

      const { where: baseWhere, params } = buildArticleQuery({
        ...digestFilters,
        dateFrom: null,
        dateTo: null,
      });

      // Nếu đang lọc "AI đã xử lý" thì lọc theo thời điểm AI xử lý (collector_ailog.created_at),
      // thay vì ngày published của bài.
      const useAiProcessedTime = digestFilters.aiProcessed === 'true';
      const timeField = useAiProcessedTime ? 'ai.ai_processed_at' : 'a.published_at';
      const extraWhere = [
        `datetime(${timeField}) >= datetime(@windowFrom)`,
        `datetime(${timeField}) <= datetime(@windowTo)`,
      ];
      if (useAiProcessedTime) extraWhere.push('ai.ai_processed_at IS NOT NULL');

      const rows = sourceDb.prepare(`
        SELECT a.title, a.summary, a.content, a.ai_content, a.published_at,
               s.source, t.name AS team_name, ai.ai_processed_at
        FROM collector_article a
        JOIN collector_source s ON s.id = a.source_id
        LEFT JOIN collector_team t ON t.id = s.team_id
        LEFT JOIN (
          SELECT url, MAX(created_at) AS ai_processed_at
          FROM collector_ailog
          GROUP BY url
        ) ai ON ai.url = a.url
        WHERE ${baseWhere} AND ${extraWhere.join(' AND ')}
        ORDER BY datetime(${timeField}) DESC
        LIMIT 80
      `).all({ ...params, windowFrom, windowTo });

      let content;
      try {
        content = await buildDigestWithLLM({ today, rows, rangeDays });
      } catch (e) {
        const bullets = rows.slice(0, 16).map((r) => `- [${r.team_name || 'N/A'}|${r.source}] ${r.title}`).join('\n');
        content = `Bản tin tổng hợp (${rangeLabel}) - ${today}\n\nTổng số bài: ${rows.length}\n\n${bullets || `Chưa có bài mới trong ${rangeLabel}.`}`;
      }

      const filterLabel = [
        digestFilters.team ? `team=${digestFilters.team}` : null,
        digestFilters.source ? `source=${digestFilters.source}` : null,
        digestFilters.aiProcessed ? `ai=${digestFilters.aiProcessed}` : null,
        digestFilters.search ? `q=${String(digestFilters.search).slice(0,40)}` : null,
      ].filter(Boolean).join(', ');

      const title = filterLabel
        ? `Bản tin ${rangeLabel} ngày ${today} (${filterLabel})`
        : `Bản tin tổng hợp ${rangeLabel} ngày ${today}`;

      if (rangeDays === 1 && !hasFilter) {
        hubDb.prepare('INSERT OR REPLACE INTO digest_daily(digest_date,title,content) VALUES (?,?,?)')
          .run(today, title, content);
      }

      digest = { digest_date: today, title, content, rangeDays, totalItems: rows.length, filters: digestFilters };
    }

    res.json({ ...digest, rangeDays });
  } catch (e) {
    res.status(500).json({ error: String(e?.message || e) });
  }
});

app.get('/api/topics/today', (req, res) => {
  const today = dayjs().format('YYYY-MM-DD');
  const topics = hubDb.prepare('SELECT keyword, score FROM topic_daily WHERE topic_date=? ORDER BY score DESC LIMIT 15').all(today);
  res.json({ date: today, topics });
});

app.post('/api/tts/google', async (req, res) => {
  try {
    const lang = String(req.body?.lang || 'vi').toLowerCase().startsWith('en') ? 'en' : 'vi';
    const text = sanitizeForTTS(String(req.body?.text || '')).slice(0, 6000);
    if (!text) return res.status(400).json({ error: 'Empty text' });

    const hash = crypto.createHash('sha1').update(`${lang}:${text}`).digest('hex');
    const outPath = path.join(ttsOutDir, `${hash}.mp3`);

    if (!fs.existsSync(outPath)) {
      const py = process.env.GTTS_PYTHON || '/home/khiemtv/sources/isdnews/venv/bin/python';
      const script = [
        'from gtts import gTTS',
        'import sys',
        'text=sys.argv[1]',
        'lang=sys.argv[2]',
        'out=sys.argv[3]',
        'gTTS(text=text, lang=lang).save(out)'
      ].join(';');
      await execFileAsync(py, ['-c', script, text, lang, outPath], { timeout: 120000 });
    }

    const audioUrl = `${req.protocol}://${req.get('host')}/audio/${hash}.mp3`;
    return res.json({ ok: true, audioUrl });
  } catch (e) {
    return res.status(500).json({ error: String(e?.message || e) });
  }
});

app.get('/api/tts/:articleId', async (req, res) => {
  try {
    const articleId = Number(req.params.articleId);
    const article = sourceDb.prepare(`
      SELECT title, is_ai_processed, ai_content, content, summary
      FROM collector_article
      WHERE id=?
    `).get(articleId);
    if (!article) return res.status(404).json({ error: 'Not found' });

    const isProcessed = Number(article.is_ai_processed) === 1;
    const rawText = isProcessed
      ? (article.ai_content || article.summary || article.content || '')
      : (article.content || article.summary || article.ai_content || '');
    const lang = isProcessed ? 'vi-VN' : 'en-US';

    let text = sanitizeForTTS(rawText);

    // Bài đã AI xử lý (tiếng Việt) => dùng LLM local để phiên âm thuật ngữ Anh cho TTS
    if (isProcessed) {
      const cached = hubDb.prepare('SELECT tts_text FROM tts_text_cache WHERE article_id=? AND lang=?').get(articleId, lang);
      if (cached?.tts_text) {
        text = cached.tts_text;
      } else {
        try {
          const converted = await vietnamizeWithLocalLLM(text);
          text = sanitizeForTTS(converted);
          hubDb.prepare('INSERT OR REPLACE INTO tts_text_cache(article_id, lang, tts_text) VALUES (?,?,?)')
            .run(articleId, lang, text);
        } catch (e) {
          // fallback text gốc đã sanitize
        }
      }
    }

    return res.json({ mode: 'browser', title: article.title, text, lang, is_ai_processed: isProcessed });
  } catch (e) {
    return res.status(500).json({ error: String(e?.message || e) });
  }
});

function buildChatMessages(userMessage, history = []) {
  const systemPrompt = `Bạn là trợ lý AI trong ISD News Hub.
- Trả lời bằng tiếng Việt, rõ ràng, thân thiện.
- Ưu tiên ngắn gọn, có cấu trúc.
- Khi phù hợp, dùng bullet để dễ đọc.
- Không bịa; nếu không chắc thì nói rõ.`;

  return [
    { role: 'system', content: systemPrompt },
    ...history
      .filter((m) => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string')
      .map((m) => ({ role: m.role, content: String(m.content).slice(0, 4000) })),
    { role: 'user', content: String(userMessage || '').slice(0, 4000) }
  ];
}

app.post('/api/chat', async (req, res) => {
  try {
    const userMessage = String(req.body?.message || '').trim();
    const history = Array.isArray(req.body?.history) ? req.body.history.slice(-12) : [];
    if (!userMessage) return res.status(400).json({ error: 'Empty message' });

    const model = process.env.CHAT_MODEL || process.env.DIGEST_MODEL || process.env.AI_MODEL || 'openai/gpt-oss-20b';
    const messages = buildChatMessages(userMessage, history);
    const reply = await llmComplete({ model, messages, temperature: 0.4 });
    return res.json({ ok: true, reply });
  } catch (e) {
    return res.status(500).json({ error: String(e?.message || e) });
  }
});

app.post('/api/chat/stream', async (req, res) => {
  try {
    const userMessage = String(req.body?.message || '').trim();
    const history = Array.isArray(req.body?.history) ? req.body.history.slice(-12) : [];
    if (!userMessage) return res.status(400).json({ error: 'Empty message' });

    const model = process.env.CHAT_MODEL || process.env.DIGEST_MODEL || process.env.AI_MODEL || 'openai/gpt-oss-20b';
    const messages = buildChatMessages(userMessage, history);
    const cfg = getLLMConfig();
    const endpoint = (cfg.style === 'openai' || cfg.style === 'vllm') ? (cfg.base + '/v1/chat/completions') : (cfg.base + '/api/chat');

    const upstream = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify((cfg.style === 'openai' || cfg.style === 'vllm')
        ? { model, stream: true, messages, temperature: 0.4 }
        : { model, stream: true, messages, options: { temperature: 0.4 } })
    });

    if (!upstream.ok || !upstream.body) {
      throw new Error(`Chat stream LLM ${upstream.status}`);
    }

    res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders?.();

    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const t = line.trim();
        if (!t) continue;
        const payload = t.startsWith('data:') ? t.slice(5).trim() : t;
        if (!payload || payload === '[DONE]') {
          res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
          continue;
        }
        try {
          const obj = JSON.parse(payload);
          const token = obj?.message?.content || obj?.choices?.[0]?.delta?.content || '';
          if (token) {
            res.write(`data: ${JSON.stringify({ token })}\n\n`);
          }
          if (obj?.done || obj?.choices?.[0]?.finish_reason) {
            res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
          }
        } catch (_) {
          // ignore malformed line
        }
      }
    }

    if (buffer.trim()) {
      try {
        const obj = JSON.parse(buffer.trim());
        const token = obj?.message?.content || '';
        if (token) res.write(`data: ${JSON.stringify({ token })}\n\n`);
      } catch (_) {}
    }

    res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
    res.end();
  } catch (e) {
    if (!res.headersSent) return res.status(500).json({ error: String(e?.message || e) });
    res.write(`data: ${JSON.stringify({ error: String(e?.message || e), done: true })}\n\n`);
    res.end();
  }
});

app.use('/', express.static(path.resolve(__dirname, '../web/public')));

const port = Number(process.env.PORT || 8787);
app.listen(port, () => console.log(`[isdnews-hub-api] running on :${port}`));
