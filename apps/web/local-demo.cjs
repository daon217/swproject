const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { randomBytes, randomUUID, scryptSync, timingSafeEqual } = require('node:crypto');

const demo = !process.argv.includes('--api');
const port = demo ? 3001 : 3000;
const host = `localhost:${port}`;
const accountDirectory = path.join(__dirname, '.local-demo');
const accountFile = path.join(accountDirectory, 'accounts.txt');
const approvalFile = path.join(accountDirectory, 'admin-approvals.json');
const sessionLifetime = 8 * 60 * 60;
const sessions = new Map();
const index = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const assets = new Map([['/', 'index.html'], ['/index.html', 'index.html']]);
for (const [, file] of index.matchAll(/<script src="\.\/([^"]+\.js)"/g)) {
  assets.set('/' + file, file);
}
const consentVersion = index.match(/id="admin-signup-terms" data-version="([^"]+)"/)[1];

fs.mkdirSync(accountDirectory, { recursive: true });
if (demo) {
  try {
    fs.writeFileSync(accountFile, '{}\n', { flag: 'wx', mode: 0o600 });
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
  }
}
try {
  fs.writeFileSync(approvalFile, '{"requests":{},"delegate":null,"deletedOffers":[]}\n', { flag: 'wx', mode: 0o600 });
} catch (error) {
  if (error.code !== 'EEXIST') throw error;
}

function readApprovals() {
  try {
    const parsed = JSON.parse(fs.readFileSync(approvalFile, 'utf8'));
    return {
      requests: parsed && typeof parsed.requests === 'object' ? parsed.requests : {},
      delegate: parsed?.delegate || null,
      deletedOffers: Array.isArray(parsed?.deletedOffers) ? parsed.deletedOffers : [],
    };
  } catch {
    return { requests: {}, delegate: null, deletedOffers: [] };
  }
}

function saveApprovals(state) {
  const temporary = approvalFile + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(state, null, 2) + '\n', { mode: 0o600 });
  fs.renameSync(temporary, approvalFile);
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

async function handleAdminApproval(request, response, url) {
  const route = url.pathname.slice('/__admin-approval'.length);
  const { method } = request;
  const state = readApprovals();

  if (method === 'POST' && route === '/requests') {
    const body = await readBody(request);
    const { user_id: userId, login_id: loginId } = body || {};
    if (typeof userId !== 'string' || !userId || typeof loginId !== 'string' || !loginId) {
      return respond(response, 422, 'INVALID_INPUT');
    }
    const key = loginId.toLowerCase();
    const existing = state.requests[key];
    state.requests[key] = {
      user_id: userId,
      login_id: loginId,
      status: existing?.status === 'approved' ? 'approved' : 'pending_approval',
      role: existing?.role || null,
      created_at: existing?.created_at || new Date().toISOString(),
      approved_at: existing?.approved_at || null,
    };
    saveApprovals(state);
    return respond(response, 201, state.requests[key]);
  }

  if (method === 'GET' && route === '/requests') {
    const pending = Object.values(state.requests)
      .filter((item) => item && item.status === 'pending_approval')
      .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
    return respond(response, 200, pending);
  }

  const approveMatch = route.match(/^\/requests\/([^/]+)\/approve$/);
  if (method === 'POST' && approveMatch) {
    const targetId = decodeURIComponent(approveMatch[1]);
    const body = await readBody(request);
    const role = body?.role;
    if (!['admin', 'support'].includes(role)) {
      return respond(response, 422, 'INVALID_INPUT');
    }
    const entry = Object.values(state.requests).find(
      (item) => item && (item.user_id === targetId || item.login_id.toLowerCase() === targetId.toLowerCase())
    );
    if (!entry) return respond(response, 404, 'REQUEST_NOT_FOUND');
    entry.status = 'approved';
    entry.role = role;
    entry.approved_at = new Date().toISOString();
    if (typeof body?.delegate_token === 'string' && body.delegate_token) {
      state.delegate = {
        token: body.delegate_token,
        expiresAt: Number(body.delegate_expires_at) || (Date.now() + sessionLifetime * 1000),
      };
    }
    saveApprovals(state);
    return respond(response, 200, { user_id: entry.user_id, login_id: entry.login_id, status: 'approved', role });
  }

  if (method === 'POST' && route === '/delegate') {
    const body = await readBody(request);
    if (typeof body?.token === 'string' && body.token) {
      state.delegate = {
        token: body.token,
        expiresAt: Number(body.expiresAt) || (Date.now() + sessionLifetime * 1000),
      };
      saveApprovals(state);
    }
    return respond(response, 200, { ok: true });
  }

  if (method === 'GET' && route === '/status') {
    const loginId = (url.searchParams.get('login_id') || '').toLowerCase();
    const userId = url.searchParams.get('user_id') || '';
    const entry = (loginId && state.requests[loginId]) ||
      Object.values(state.requests).find((item) => item && item.user_id === userId) ||
      null;
    const delegateValid = state.delegate && state.delegate.expiresAt > Date.now() ? state.delegate : null;
    return respond(response, 200, {
      request: entry,
      delegateToken: entry?.status === 'approved' && delegateValid ? delegateValid.token : null,
      delegateExpiresAt: entry?.status === 'approved' && delegateValid ? delegateValid.expiresAt : null,
    });
  }

  if (method === 'GET' && route === '/deleted-offers') {
    return respond(response, 200, { deleted_offer_ids: state.deletedOffers });
  }

  if (method === 'POST' && route === '/deleted-offers') {
    const body = await readBody(request);
    const ids = Array.isArray(body?.offer_ids) ? body.offer_ids.filter((id) => typeof id === 'string') : [];
    const merged = new Set([...state.deletedOffers, ...ids]);
    state.deletedOffers = [...merged];
    saveApprovals(state);
    return respond(response, 200, { deleted_offer_ids: ids, protected_offer_ids: [], missing_offer_ids: [] });
  }

  return respond(response, 404, 'NOT_FOUND');
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
    if (url.pathname.startsWith('/__admin-approval/')) {
      return await handleAdminApproval(request, response, url);
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
