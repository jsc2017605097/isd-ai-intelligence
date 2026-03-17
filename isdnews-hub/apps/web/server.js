const express = require('express');
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });

const app = express();
app.get('/favicon.ico', (req, res) => res.status(204).end());
app.use((req, res, next) => {
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  next();
});
app.use(express.static(path.resolve(__dirname, 'public')));
app.listen(Number(process.env.WEB_PORT || 4173), () => console.log('[isdnews-hub-web] running'));
