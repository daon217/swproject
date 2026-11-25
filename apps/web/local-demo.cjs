const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { randomBytes, randomUUID, scryptSync, timingSafeEqual } = require('node:crypto');

const demo = !process.argv.includes('--api');
const port = demo ? 3001 : 3000;
const host = `localhost:${port}`;
const apiTarget = (process.env.INTERNAL_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const accountDirectory = path.join(__dirname, '.local-demo');
const accountFile = path.join(accountDirectory, 'accounts.txt');
const sessionLifetime = 8 * 60 * 60;
const sessions = new Map();
const index = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const assets = new Map([['/', 'index.html'], ['/index.html', 'index.html']]);
for (const [, file] of index.matchAll(/<script src="\.\/([^"]+\.js)"/g)) {
  assets.set('/' + file, file);
}
const consentVersion = index.match(/id="admin-signup-terms" data-version="([^"]+)"/)[1];

if (demo) {
  fs.mkdirSync(accountDirectory, { recursive: true });
  try {
    fs.writeFileSync(accountFile, '{}\n', { flag: 'wx', mode: 0o600 });
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
  }
}

function readAccounts() {
  return JSON.parse(fs.readFileSync(accountFile, 'utf8'));
}

function saveAccounts(accounts) {
  const temporary = accountFile + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(accounts, null, 2) + '\n', { mode: 0o600 });
  fs.renameSync(temporary, accountFile);
}

function respond(response, status, data) {
  if (status === 204) {
    response.writeHead(status).end();
    return;
  }
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  response.end(JSON.stringify(status < 400 ? { data } : { error: { code: data } }));
}

async function readBody(request) {
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers['content-type'] || '')) return null;
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size <= 8192) chunks.push(chunk);
  }
  if (size > 8192) return null;
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    return null;
  }
}

async function handleAuth(request, response, route) {
  const { method } = request;
  if (method === 'POST' && ['/v2/auth/signup', '/v2/auth/login'].includes(route)) {
    const body = await readBody(request);
    const { login_id: loginId, password } = body || {};
    if (typeof loginId !== 'string' || !/^[A-Za-z0-9]{4,16}$/.test(loginId) ||
      typeof password !== 'string' || password.length < 1 || password.length > 128) {
      return respond(response, 422, 'INVALID_INPUT');
    }
    const accounts = readAccounts();
    const key = loginId.toLowerCase();
    const account = Object.hasOwn(accounts, key) ? accounts[key] : null;
    if (route === '/v2/auth/signup') {
      if (password.length < 8 || password !== body.password_confirmation ||
        body.consent_accepted !== true || body.consent_version !== consentVersion) {
        return respond(response, 422, 'INVALID_INPUT');
      }
      if (account) return respond(response, 409, 'LOGIN_ID_TAKEN');
      const salt = randomBytes(16).toString('hex');
      const userId = randomUUID();
      accounts[key] = {
        loginId, userId, salt,
        passwordHash: scryptSync(password, salt, 32).toString('hex'),
        consentVersion,
      };
      saveAccounts(accounts);
      return respond(response, 201, { user_id: userId });
    }

    const hash = scryptSync(password, account?.salt || 'demo-missing-account', 32);
    if (!account || !timingSafeEqual(hash, Buffer.from(account.passwordHash, 'hex'))) {
      return respond(response, 401, 'INVALID_CREDENTIALS');
    }
    const token = randomBytes(32).toString('hex');
    const now = Date.now();
    for (const [key, session] of sessions) {
      if (session.expiresAt <= now) sessions.delete(key);
    }
    sessions.set(token, { userId: account.userId, expiresAt: now + sessionLifetime * 1000 });
    return respond(response, 200, { token, expires_in: sessionLifetime });
  }

  if ((method === 'GET' && route === '/v2/admin/me') || (method === 'POST' && route === '/v2/auth/logout')) {
    const token = request.headers.authorization?.match(/^Bearer (\S+)$/i)?.[1];
    const session = sessions.get(token);
    if (!session || session.expiresAt <= Date.now()) return respond(response, 401, 'AUTH_REQUIRED');
    if (method === 'GET') return respond(response, 200, { user_id: session.userId, role: 'admin' });
    sessions.delete(token);
    return respond(response, 204);
  }
  return respond(response, 404, 'NOT_FOUND');
}

async function handleRunCrawlCycle(request, response) {
  if (request.method !== 'POST') return respond(response, 405, 'METHOD_NOT_ALLOWED');
  const { execFile } = require('node:child_process');
  const repoRoot = path.resolve(__dirname, '../..');
  const collectorDir = path.join(repoRoot, 'services', 'collector', 'domeggook_live');
  const venvPython = path.join(repoRoot, '.venv', 'Scripts', 'python.exe');
  const pythonBin = fs.existsSync(venvPython) ? venvPython : 'python';

  if (fs.existsSync(collectorDir)) {
    const output = await new Promise((resolve) => {
      execFile(
        pythonBin,
        ['-m', 'services.collector.domeggook_live', '--watch', '--cycles', '1'],
        { cwd: repoRoot, timeout: 45000 },
        (error, stdout, stderr) => {
          resolve({
            ok: !error,
            stdout: String(stdout || '').trim(),
            stderr: String(stderr || '').trim(),
          });
        }
      );
    });
    return respond(response, 200, {
      mode: 'collector_cycle',
      executedAt: new Date().toISOString(),
      ...output,
    });
  }

  return respond(response, 200, {
    mode: 'api_sync_cycle',
    executedAt: new Date().toISOString(),
    ok: true,
  });
}

async function handleBackendProxy(request, response, url) {
  const apiPath = url.pathname.slice('/backend'.length) + url.search;
  const headers = { 'Content-Type': 'application/json' };
  if (request.headers.authorization) {
    headers.Authorization = request.headers.authorization;
  }
  let body;
  if (!['GET', 'HEAD'].includes(request.method)) {
    const chunks = [];
    let size = 0;
    for await (const chunk of request) {
      size += chunk.length;
      if (size <= 65536) chunks.push(chunk);
    }
    if (size > 65536) return respond(response, 413, 'PAYLOAD_TOO_LARGE');
    if (chunks.length) body = Buffer.concat(chunks);
  }
  try {
    const upstream = await fetch(apiTarget + apiPath, {
      method: request.method,
      headers,
      body,
      redirect: 'manual',
      signal: AbortSignal.timeout(15000),
    });
    const text = upstream.status === 204 ? '' : await upstream.text();
    response.writeHead(upstream.status, {
      'Content-Type': upstream.headers.get('content-type') || 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    response.end(upstream.status === 204 ? undefined : text);
  } catch {
    respond(response, 502, 'BACKEND_UNAVAILABLE');
  }
}

const server = http.createServer(async (request, response) => {
  response.setHeader('Cache-Control', 'no-store');
  response.setHeader('X-Content-Type-Options', 'nosniff');
  if (request.headers.host !== host ||
    (request.headers.origin && request.headers.origin !== `http://${host}`)) {
    return respond(response, 403, 'LOCAL_ONLY');
  }

  try {
    const url = new URL(request.url, `http://${host}`);
    if (url.pathname === '/__run-crawl-cycle') {
      return await handleRunCrawlCycle(request, response);
    }
    if (!demo && url.pathname.startsWith('/backend/')) {
      return await handleBackendProxy(request, response, url);
    }
    const prefix = '/__local-demo';
    if (demo && url.pathname.startsWith(prefix + '/')) {
      return await handleAuth(request, response, url.pathname.slice(prefix.length));
    }
    const asset = assets.get(url.pathname);
    if (!asset || !['GET', 'HEAD'].includes(request.method)) return respond(response, 404, 'NOT_FOUND');
    const content = fs.readFileSync(path.join(__dirname, asset));
    response.writeHead(200, {
      'Content-Type': (asset.endsWith('.js') ? 'text/javascript' : 'text/html') + '; charset=utf-8',
    });
    response.end(request.method === 'HEAD' ? undefined : content);
  } catch {
    respond(response, 500, 'DEMO_SERVER_ERROR');
  }
});

server.listen(port, '127.0.0.1', () => {
  console.log(demo ? `꿀픽 로컬 데모 · http://${host}/?demo=1#/signup` : `꿀픽 관리자 웹 · http://${host}/`);
});
