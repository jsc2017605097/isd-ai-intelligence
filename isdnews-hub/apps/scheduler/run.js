const cron = require('node-cron');
const { spawn } = require('child_process');
const path = require('path');

function runWorker() {
  const p = spawn(process.execPath, [path.resolve(__dirname, '../worker/run.js')], { stdio: 'inherit' });
  p.on('exit', (code) => console.log(`[scheduler] worker exit ${code}`));
}

// mỗi 30 phút
cron.schedule('*/30 * * * *', runWorker);

console.log('[scheduler] started, cron=*/30 * * * *');
runWorker();
