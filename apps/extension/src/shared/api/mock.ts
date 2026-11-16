import { allergenLabel } from '../allergens';
import { getAuthToken } from '../auth';
import { josa } from '../format';
import { getItem, KEYS, setItem } from '../storage';
import {
  ApiError,
  type Analysis,
  type AnalysisHistoryItem,
  type Me,
  type OfferCard,
  type Profile,
  type ResultSection,
  type SupportMessage,
} from '../types';
import type { PageProduct } from '../pageProduct';
import type { KkulpickApi } from './index';
import { FEATURED, mockPageFor, PRINTER_AI, PRINTER_USED, SNACK_AI } from './mockCatalog';

// 백엔드가 준비되기 전 화면 흐름 확인용 목업. 저장소는 chrome.storage.local(미리보기는 localStorage).
// 서버 규칙 중 화면에 드러나는 부분(무료/프리미엄 한도, 잠긴 후보 URL 미포함, 비회원 중고 OFF,
// expected_version 충돌, 알레르기 경고)을 흉내 낸다.

const FREE_LIMIT = 1;
const PREMIUM_LIMIT = 3;
const USED_LIMIT = 3;
const AI_DELAY = 900;
const USED_DELAY = 2600;

interface MockUser {
  user_id: string;
  login_id: string;
  password_hash: string;
  profile: Profile;
  premium_until: string | null;
  history: AnalysisHistoryItem[];
  support: SupportMessage[];
}

interface MockJob {
  analysis_id: string;
  owner: string | null; // user_id 또는 null(비회원)
  page_url: string;
  page_session_id: string;
  page_revision: number;
  created_at: number;
  cancelled: boolean;
  page_product: PageProduct | null;
}

interface MockDb {
  users: Record<string, MockUser>; // key: user_id
  sessions: Record<string, string>; // token -> user_id
  jobs: Record<string, MockJob>;
}

const emptyDb = (): MockDb => ({ users: {}, sessions: {}, jobs: {} });

async function load(): Promise<MockDb> {
  return getItem<MockDb>(KEYS.mockDb, emptyDb());
}
async function save(db: MockDb) {
  await setItem(KEYS.mockDb, db);
}

const uuid = () => crypto.randomUUID();
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function currentUser(db: MockDb): Promise<MockUser | null> {
  const token = await getAuthToken();
  const id = token ? db.sessions[token] : undefined;
  return id ? db.users[id] ?? null : null;
}

async function requireUser(db: MockDb): Promise<MockUser> {
  const u = await currentUser(db);
  if (!u) throw new ApiError(401, 'UNAUTHENTICATED', '로그인이 필요해요.');
  return u;
}

const isPremium = (u: MockUser | null) => !!u?.premium_until && new Date(u.premium_until).getTime() > Date.now();

function toMe(u: MockUser): Me {
  return { user_id: u.user_id, login_id: u.login_id, premium: isPremium(u), profile: u.profile };
}

const LOGIN_ID_RE = /^[A-Za-z0-9]{4,16}$/;

function section(kind: ResultSection['kind'], all: OfferCard[], limit: number, footnote: string | null): ResultSection {
  const visible = all.slice(0, limit);
  return {
    kind,
    state: 'ready',
    items: visible,
    // 잠긴 후보는 개수만 알려주고 내용은 보내지 않는다(명세 10.2).
    locked_count: Math.max(0, Math.min(all.length, PREMIUM_LIMIT) - visible.length),
    lock_reason: visible.length < Math.min(all.length, PREMIUM_LIMIT) ? 'premium_required' : null,
    footnote,
  };
}

function buildAnalysis(job: MockJob, user: MockUser | null): Analysis {
  const elapsed = Date.now() - job.created_at;
  const base: Analysis = {
    analysis_id: job.analysis_id,
    state: 'running',
    result_kind: null,
    ingredient_status: 'not_applicable',
    page_session_id: job.page_session_id,
    page_revision: job.page_revision,
    selected_domain: null,
    source_summary: {},
    warnings: [],
    sections: [],
    applied_filter: null,
    premium: isPremium(user),
    page_product: job.page_product ?? null,
    error: null,
  };
  if (job.cancelled) return { ...base, state: 'cancelled' };
  if (elapsed < AI_DELAY) return base;

  const page = mockPageFor(job.page_url);
  if (!page) return { ...base, state: 'completed', result_kind: 'empty' };

  const premium = isPremium(user);
  const limit = premium ? PREMIUM_LIMIT : FREE_LIMIT;
  const result: Analysis = {
    ...base,
    state: 'completed',
    result_kind: 'recommendation',
    selected_domain: page.domain,
    source_summary: { catalog: 'success' },
  };

  if (page.domain === 'product') {
    result.sections.push(section('ai', PRINTER_AI, limit, premium ? '판매처에서 최종 가격과 배송 조건을 확인하세요.' : null));
    // 중고는 product 도메인 + 회원 include_used일 때만. 비회원 기본값은 false(명세 9.4).
    if (user?.profile.include_used) {
      const ready = elapsed >= USED_DELAY;
      result.sections.push({
        kind: 'used',
        state: ready ? 'ready' : 'loading',
        items: ready ? PRINTER_USED.slice(0, USED_LIMIT) : [],
        locked_count: 0,
        lock_reason: null,
        footnote: null,
      });
    }
    return result;
  }

  // 식품
  result.ingredient_status = 'complete';
  const allergies = user?.profile.allergies ?? [];
  const hits = page.contains.filter((c) => allergies.includes(c));
  for (const code of hits) {
    const label = allergenLabel(code);
    result.warnings.push({
      type: 'allergy',
      allergen: code,
      evidence: 'contains',
      message: `상품명에 ${josa(label, '이', '가')} 표시되어 있어요.`,
    });
  }
  const filter = premium ? user?.profile.ingredient_filter ?? null : null;
  const hasFilter = !!filter && (filter.avoid.length > 0 || filter.prefer.length > 0);
  result.applied_filter = hasFilter ? filter : null;
  if (hits.length > 0) {
    const alt = SNACK_AI.map((c) => ({ ...c, reason: '구매 전 성분표를 확인해야 하는 대체 후보예요.' }));
    result.sections.push(section('alternative', alt, limit, null));
  } else {
    result.sections.push(section('ai', SNACK_AI, limit, premium ? '구매 전 판매처 원재료 표시를 확인해 주세요.' : null));
  }
  return result;
}

// 목업 저장소는 읽기→수정→쓰기라서 같은 화면 안의 동시 호출이 서로 덮어쓰지 않도록 직렬화한다.
let chain: Promise<unknown> = Promise.resolve();
function serial<T>(fn: () => Promise<T>): Promise<T> {
  const p = chain.then(fn);
  chain = p.catch(() => undefined);
  return p;
}

export function createMockApi(): KkulpickApi {
  const impl = createMockImpl();
  return Object.fromEntries(
    Object.entries(impl).map(([k, fn]) => [k, (...args: unknown[]) => serial(() => (fn as (...a: unknown[]) => Promise<unknown>)(...args))]),
  ) as unknown as KkulpickApi;
}

function createMockImpl(): KkulpickApi {
  return {
    async signup(req) {
      await wait(300);
      if (!LOGIN_ID_RE.test(req.login_id)) throw new ApiError(422, 'INVALID_LOGIN_ID', '아이디는 영문·숫자 4~16자로 입력해 주세요.');
      if (req.password.length < 8) throw new ApiError(422, 'WEAK_PASSWORD', '비밀번호는 8자 이상이어야 해요.');
      if (req.password !== req.password_confirmation) throw new ApiError(422, 'PASSWORD_MISMATCH', '비밀번호가 일치하지 않아요.');
      if (!req.consent_accepted) throw new ApiError(422, 'CONSENT_REQUIRED', '필수 동의가 필요해요.');
      if (req.birth_date && new Date(req.birth_date) > new Date()) throw new ApiError(422, 'INVALID_BIRTH_DATE', '생년월일을 확인해 주세요.');
      const db = await load();
      if (Object.values(db.users).some((u) => u.login_id.toLowerCase() === req.login_id.toLowerCase())) {
        throw new ApiError(409, 'LOGIN_ID_TAKEN', '이미 사용 중인 아이디예요.');
      }
      const user_id = uuid();
      db.users[user_id] = {
        user_id,
        login_id: req.login_id,
        password_hash: await sha256(req.password),
        profile: {
          version: 1,
          gender: req.gender,
          birth_date: req.birth_date,
          include_used: false,
          allergies: req.allergies,
          ingredient_filter: { avoid: [], prefer: [] },
        },
        premium_until: null,
        history: [],
        support: [],
      };
      await save(db);
      return { user_id };
    },

    async checkLoginId(login_id) {
      await wait(250);
      if (!LOGIN_ID_RE.test(login_id)) throw new ApiError(422, 'INVALID_LOGIN_ID', '아이디는 영문·숫자 4~16자로 입력해 주세요.');
      const db = await load();
      return { available: !Object.values(db.users).some((u) => u.login_id.toLowerCase() === login_id.toLowerCase()) };
    },

    async login(login_id, password) {
      await wait(300);
      const db = await load();
      const hash = await sha256(password);
      const user = Object.values(db.users).find((u) => u.login_id.toLowerCase() === login_id.toLowerCase());
      if (!user || user.password_hash !== hash) throw new ApiError(401, 'INVALID_CREDENTIALS', '아이디 또는 비밀번호를 확인해 주세요.');
      const token = uuid();
      db.sessions[token] = user.user_id;
      await save(db);
      return { token };
    },

    async logout() {
      const db = await load();
      const token = await getAuthToken();
      if (token) delete db.sessions[token];
      await save(db);
    },

    async getMe() {
      return toMe(await requireUser(await load()));
    },

    async updateProfile(patch) {
      await wait(250);
      const db = await load();
      const u = await requireUser(db);
      if (patch.expected_version !== u.profile.version) {
        throw new ApiError(409, 'VERSION_CONFLICT', '다른 곳에서 정보가 바뀌었어요. 새로고침 후 다시 저장해 주세요.');
      }
      if (patch.birth_date && new Date(patch.birth_date) > new Date()) throw new ApiError(422, 'INVALID_BIRTH_DATE', '생년월일을 확인해 주세요.');
      const { expected_version: _ignored, ...rest } = patch;
      u.profile = { ...u.profile, ...rest, version: u.profile.version + 1 };
      await save(db);
      return toMe(u);
    },

    async changePassword(current, next, confirmation) {
      await wait(300);
      const db = await load();
      const u = await requireUser(db);
      if (u.password_hash !== (await sha256(current))) throw new ApiError(422, 'WRONG_PASSWORD', '현재 비밀번호가 맞지 않아요.');
      if (next.length < 8) throw new ApiError(422, 'WEAK_PASSWORD', '새 비밀번호는 8자 이상이어야 해요.');
      if (next !== confirmation) throw new ApiError(422, 'PASSWORD_MISMATCH', '새 비밀번호와 확인 값이 같지 않아요.');
      u.password_hash = await sha256(next);
      await save(db);
    },

    async createAnalysis(req) {
      const db = await load();
      const user = await currentUser(db);
      const analysis_id = uuid();
      db.jobs[analysis_id] = {
        analysis_id,
        owner: user?.user_id ?? null,
        page_url: req.page_url,
        page_session_id: req.page_session_id,
        page_revision: req.page_revision,
        created_at: Date.now(),
        cancelled: false,
        page_product: req.page_product ?? null,
      };
      // 오래된 작업 정리(목업 저장소 크기 제한)
      const ids = Object.keys(db.jobs);
      if (ids.length > 30) for (const id of ids.slice(0, ids.length - 30)) delete db.jobs[id];
      await save(db);
      return { analysis_id, state: 'queued', status_url: `/analyses/${analysis_id}` };
    },

    async getAnalysis(id) {
      const db = await load();
      const job = db.jobs[id];
      const user = await currentUser(db);
      if (!job || job.owner !== (user?.user_id ?? null)) throw new ApiError(404, 'NOT_FOUND', '분석 결과를 찾을 수 없어요.');
      const result = buildAnalysis(job, user);
      // 완료된 첫 카드를 회원 최근 추천에 기록
      if (user && result.state === 'completed' && result.result_kind === 'recommendation') {
        const first = result.sections[0]?.items[0];
        if (first && !user.history.some((h) => h.analysis_id === id)) {
          user.history.unshift({ analysis_id: id, created_at: new Date().toISOString(), card: first });
          user.history = user.history.slice(0, 20);
          await save(db);
        }
      }
      return result;
    },

    async cancelAnalysis(id) {
      const db = await load();
      if (db.jobs[id]) db.jobs[id].cancelled = true;
      await save(db);
    },

    async listHistory() {
      const db = await load();
      return (await requireUser(db)).history;
    },

    async listFeatured() {
      await wait(200);
      return FEATURED;
    },

    async deleteAllHistory() {
      await wait(400);
      const db = await load();
      const u = await requireUser(db);
      u.history = [];
      await save(db);
      return { request_id: uuid() };
    },

    async listPlans() {
      return [
        {
          plan_id: 'premium-monthly',
          name: '꿀픽 프리미엄',
          price: null, // 요금 미확정(D01)
          currency: 'KRW',
          interval: 'month',
          benefits: ['AI 추천 상품 3개 전체 보기', '기피·선호 재료로 식품 필터', '내 취향에 맞는 후보 비교'],
        },
      ];
    },

    async createSubscription() {
      await wait(900);
      const db = await load();
      const u = await requireUser(db);
      // 개발용: localStorage/chrome.storage에 kp.mock.paymentFail=true면 실패 흐름 확인
      if (await getItem<boolean>('kp.mock.paymentFail', false)) {
        throw new ApiError(402, 'PAYMENT_FAILED', '결제가 정상적으로 처리되지 않았습니다.');
      }
      const end = new Date();
      end.setMonth(end.getMonth() + 1);
      u.premium_until = end.toISOString();
      await save(db);
      return { subscription_id: uuid(), invoice_id: uuid(), payment_id: uuid() };
    },

    async getSubscription() {
      const u = await requireUser(await load());
      return { active: isPremium(u), entitlement_end: u.premium_until, cancel_at_period_end: false };
    },

    async getSupportConversation() {
      const u = await requireUser(await load());
      return { conversation_id: `conv-${u.user_id}`, agent_name: '김상담', status: 'open' };
    },

    async listSupportMessages() {
      return (await requireUser(await load())).support;
    },

    async sendSupportMessage(_id, body, client_message_id) {
      const db = await load();
      const u = await requireUser(db);
      const existing = u.support.find((m) => m.message_id === client_message_id);
      if (existing) return existing;
      const msg: SupportMessage = {
        message_id: client_message_id,
        sequence_no: u.support.length + 1,
        sender: 'member',
        sender_name: null,
        body: body.slice(0, 10000),
        created_at: new Date().toISOString(),
      };
      u.support.push(msg);
      await save(db);
      // 목업 상담원 자동 응답
      setTimeout(() => void serial(async () => {
        const db2 = await load();
        const u2 = db2.users[u.user_id];
        if (!u2) return;
        u2.support.push({
          message_id: uuid(),
          sequence_no: u2.support.length + 1,
          sender: 'agent',
          sender_name: '김상담',
          body: '안녕하세요, 꿀픽입니다. 확인 후 답변드릴게요.',
          created_at: new Date().toISOString(),
        });
        await save(db2);
      }), 1500);
      return msg;
    },
  };
}
