module.exports = {
  apps: [
    {
      name: 'isdnews-hub-api',
      script: './apps/api/server.js',
      cwd: '/home/khiemtv/sources/isdnews-hub',
      env_file: '/home/khiemtv/sources/isdnews-hub/.env',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M'
    },
    {
      name: 'isdnews-hub-web',
      script: './apps/web/server.js',
      cwd: '/home/khiemtv/sources/isdnews-hub',
      env_file: '/home/khiemtv/sources/isdnews-hub/.env',
      autorestart: true,
      watch: false
    },
    {
      name: 'isdnews-hub-worker',
      script: './apps/worker/run.js',
      cwd: '/home/khiemtv/sources/isdnews-hub',
      env_file: '/home/khiemtv/sources/isdnews-hub/.env',
      autorestart: false,
      watch: false
    },
    {
      name: 'isdnews-hub-scheduler',
      script: './apps/scheduler/run.js',
      cwd: '/home/khiemtv/sources/isdnews-hub',
      env_file: '/home/khiemtv/sources/isdnews-hub/.env',
      autorestart: true,
      watch: false
    }
  ]
};
