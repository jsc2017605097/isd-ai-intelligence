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

function getLLMConfig() {
  const provider = (process.env.AI_PROVIDER || 'ollama').toLowerCase();
  const apiKey = process.env.AI_API_KEY || '';
  const model = process.env.CHAT_MODEL || process.env.AI_MODEL || 'qwen3:30b-a3b';
  
  let baseUrl = process.env.LLM_BASE_URL || process.env.AI_BASE_URL || '';
  let endpoint = '';
  let headers = { 'Content-Type': 'application/json' };

  if (provider === 'openai') {
    if (!baseUrl) baseUrl = 'https://api.openai.com/v1';
    endpoint = (baseUrl.endsWith('/v1') ? baseUrl : `${baseUrl.replace(/\/$/, '')}/v1`) + '/chat/completions';
    headers['Authorization'] = `Bearer ${apiKey}`;
  } else if (provider === 'anthropic') {
    if (!baseUrl) baseUrl = 'https://api.anthropic.com/v1';
    endpoint = baseUrl.replace(/\/$/, '') + '/messages';
    headers['x-api-key'] = apiKey;
    headers['anthropic-version'] = '2023-06-01';
  } else if (provider === 'google') {
    endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
  } else if (provider === 'openrouter') {
    endpoint = 'https://openrouter.ai/api/v1/chat/completions';
    headers['Authorization'] = `Bearer ${apiKey}`;
  } else if (provider === 'ollama') {
    endpoint = (baseUrl.replace(/\/$/, '')) + '/api/chat';
  } else {
    // Default fallback
    endpoint = `${baseUrl}/v1/chat/completions`;
  }

  return { provider, model, endpoint, headers };
}

async function llmComplete({ messages, systemPrompt, temperature = 0.4 }) {
  const { provider, model, endpoint, headers } = getLLMConfig();
  let payload = {};

  if (provider === 'anthropic') {
    payload = { model, system: systemPrompt, messages, max_tokens: 4096, temperature };
  } else if (provider === 'google') {
    payload = { contents: [{ role: 'user', parts: [{ text: `System: ${systemPrompt}\n\nUser: ${messages[messages.length-1].content}` }] }] };
  } else if (provider === 'ollama') {
    // Native Ollama Chat API
    payload = { model, stream: false, messages: [{ role: 'system', content: systemPrompt }, ...messages], options: { temperature } };
  } else {
    // OpenAI style
    payload = { model, messages: [{ role: 'system', content: systemPrompt }, ...messages], temperature };
  }

  const resp = await fetch(endpoint, { method: 'POST', headers, body: JSON.stringify(payload) });
  if (!resp.ok) throw new Error(`LLM Error ${resp.status}: ${await resp.text()}`);
  
  const data = await resp.json();
  if (provider === 'anthropic') return data.content[0].text;
  if (provider === 'google') return data.candidates[0].content.parts[0].text;
  if (provider === 'ollama') return data.message.content;
  return data.choices[0].message.content;
}

async function vietnamizeWithLocalLLM(text = '') {
  const prompt = `Hãy chuyển các thuật ngữ tiếng Anh trong đoạn văn sau thành phiên âm tiếng Việt dễ đọc cho TTS.\nAPI -> ây pi ai, Docker -> đọc cơ...\nVăn bản:\n${text}`;
  try {
    const out = await llmComplete({ 
      systemPrompt: "Bạn là chuyên gia ngôn ngữ.", 
      messages: [{ role: 'user', content: prompt }], 
      temperature: 0.1 
    });
    return out || text;
  } catch (e) { return text; }
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
    where.push(phraseClause);
  }
  if (q.team) { where.push('LOWER(t.code)=LOWER(@team)'); params.team = q.team; }
  if (q.source) { where.push('LOWER(s.source)=LOWER(@source)'); params.source = q.source; }
  if (q.aiProcessed === 'true') where.push('a.is_ai_processed = 1');
  if (q.aiProcessed === 'false') where.push('a.is_ai_processed = 0');
  return { where: where.join(' AND '), params };
}

app.get('/api/health', (req, res) => res.json({ ok: true }));
app.get('/api/teams', (req, res) => res.json(sourceDb.prepare('SELECT code, name FROM collector_team WHERE is_active=1').all()));
app.get('/api/sources', (req, res) => res.json(sourceDb.prepare('SELECT source, type, url FROM collector_source WHERE is_active=1').all()));

app.get('/api/articles', (req, res) => {
  const page = Math.max(1, parseInt(req.query.page || '1', 10));
  const pageSize = Math.min(50, Math.max(1, parseInt(req.query.pageSize || '12', 10)));
  const { where, params } = buildArticleQuery(req.query);
  const baseFrom = `FROM collector_article a JOIN collector_source s ON s.id=a.source_id LEFT JOIN collector_team t ON t.id=s.team_id WHERE ${where}`;
  const items = sourceDb.prepare(`SELECT a.id, a.title, a.summary, a.ai_content, a.is_ai_processed, a.published_at, a.thumbnail, s.source, t.code AS team_code ${baseFrom} ORDER BY a.published_at DESC LIMIT @limit OFFSET @offset`).all({ ...params, limit: pageSize, offset: (page-1)*pageSize });
  const total = sourceDb.prepare(`SELECT COUNT(*) AS c ${baseFrom}`).get(params).c;
  res.json({ page, pageSize, total, items });
});

app.get('/api/articles/:id', (req, res) => {
  const article = sourceDb.prepare(`SELECT a.*, s.source, t.name AS team_name FROM collector_article a JOIN collector_source s ON s.id=a.source_id LEFT JOIN collector_team t ON t.id=s.team_id WHERE a.id=?`).get(req.params.id);
  if (!article) return res.status(404).json({ error: 'Not found' });
  res.json(article);
});

app.post('/api/chat', async (req, res) => {
  try {
    const reply = await llmComplete({
      systemPrompt: "Bạn là trợ lý AI chuyên gia. Trả lời ngắn gọn, tiếng Việt.",
      messages: req.body.history ? [...req.body.history, { role: 'user', content: req.body.message }] : [{ role: 'user', content: req.body.message }]
    });
    res.json({ ok: true, reply });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post('/api/chat/stream', async (req, res) => {
  const { endpoint, headers, model, provider } = getLLMConfig();
  const systemPrompt = "Bạn là trợ lý AI chuyên gia. Trả lời tiếng Việt.";
  const messages = req.body.history ? [...req.body.history, { role: 'user', content: req.body.message }] : [{ role: 'user', content: req.body.message }];
  
  let payload = {};
  if (provider === 'anthropic') {
    payload = { model, system: systemPrompt, messages, stream: true, max_tokens: 4096 };
  } else {
    payload = { model, messages: [{ role: 'system', content: systemPrompt }, ...messages], stream: true };
  }

  try {
    const upstream = await fetch(endpoint, { method: 'POST', headers, body: JSON.stringify(payload) });
    res.setHeader('Content-Type', 'text/event-stream');
    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(l => l.trim());
      for (const line of lines) {
        if (line.includes('[DONE]')) continue;
        try {
          const jsonStr = line.replace(/^data: /, '');
          const data = JSON.parse(jsonStr);
          let token = '';
          if (provider === 'anthropic') token = data.delta?.text || '';
          else token = data.choices?.[0]?.delta?.content || '';
          if (token) res.write(`data: ${JSON.stringify({ token })}\n\n`);
        } catch(e) {}
      }
    }
    res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
    res.end();
  } catch (e) { res.end(); }
});

app.use('/', express.static(path.resolve(__dirname, '../web/public')));
app.listen(8787, () => console.log('ISD Hub API running on :8787'));
