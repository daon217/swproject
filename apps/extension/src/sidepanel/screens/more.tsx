import { useEffect, useRef, useState } from 'react';
import { allergenLabel, knownAllergens } from '../../shared/allergens';
import { api } from '../../shared/api';
import { formatDate, formatPrice, formatTime } from '../../shared/format';
import { sendMessage } from '../../shared/messages';
import { ApiError, type PaymentMethod, type SubscriptionPlan, type SupportConversation, type SupportMessage } from '../../shared/types';
import { Checkbox, ConfirmDialog, Field, Note, Page, SubHeader } from '../components';
import { useNav } from '../nav';
import { useSession } from '../session';

// ---------- 고객지원 상담 채팅 (E14) ----------
/** 상담원이 상담을 끝냈는지(서버 status가 resolved·closed) */
const isClosed = (c: SupportConversation | null) => c?.status === 'resolved' || c?.status === 'closed';

export function SupportScreen() {
  const [conv, setConv] = useState<SupportConversation | null>(null);
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const convId = conv?.conversation_id;
  const closed = isClosed(conv);

  // 처음 열 때: 진행 중인 상담이 있으면 그것을, 없으면 가장 최근 상담(종료됐으면 종료 상태로)을 보여준다.
  // 상담 기록이 하나도 없을 때만 새 상담을 연다(POST는 종료된 상담 대신 새 상담을 만든다).
  useEffect(() => {
    let alive = true;
    (async () => {
      const list = await api.listSupportConversations().catch(() => [] as SupportConversation[]);
      return list[0] ?? (await api.getSupportConversation());
    })()
      .then((c) => alive && setConv(c))
      .catch(() => alive && setError('상담을 불러오지 못했어요.'));
    return () => {
      alive = false;
    };
  }, []);

  // 메시지와 상담 상태를 3초마다 갱신한다(실시간 채널 확정 전까지 폴링). 종료되면 더 묻지 않는다.
  useEffect(() => {
    if (!convId) return;
    let alive = true;
    const load = async () => {
      const [m, list] = await Promise.all([
        api.listSupportMessages(convId).catch(() => null),
        api.listSupportConversations().catch(() => null),
      ]);
      if (!alive) return;
      if (m) setMessages(m);
      const cur = list?.find((c) => c.conversation_id === convId);
      if (cur) setConv((prev) => (prev && prev.status !== cur.status ? { ...prev, status: cur.status } : prev));
    };
    void load();
    if (closed) return () => void (alive = false);
    const timer = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [convId, closed]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages.length, closed]);

  const send = async () => {
    const body = text.trim();
    if (!body || !conv || closed) return;
    setText('');
    try {
      // 재전송해도 같은 메시지가 되도록 client_message_id를 붙인다.
      const msg = await api.sendSupportMessage(conv.conversation_id, body, crypto.randomUUID());
      setMessages((prev) => (prev.some((m) => m.message_id === msg.message_id) ? prev : [...prev, msg]));
    } catch (e) {
      setText(body);
      // 보내는 사이 상담이 종료됐으면 종료 상태로 바꾼다.
      if (e instanceof ApiError && e.code === 'CONVERSATION_CLOSED') setConv((prev) => (prev ? { ...prev, status: 'resolved' } : prev));
      else setError('메시지를 보내지 못했어요.');
    }
  };

  const startNew = async () => {
    setStarting(true);
    setError(null);
    try {
      const c = await api.getSupportConversation();
      setMessages([]);
      setText('');
      setConv(c);
    } catch {
      setError('새 상담을 시작하지 못했어요.');
    } finally {
      setStarting(false);
    }
  };

  let lastDay = '';
  return (
    <>
      <SubHeader title="고객지원" />
      <div className="sp-chat">
        <div className="sp-chat-list" ref={listRef}>
          <div className="sp-chat-agent">
            <span className={`sp-dot ${closed ? 'is-off' : ''}`} aria-hidden="true" />
            <div>
              <strong>꿀픽 고객지원</strong>
              <small>{closed ? '상담 종료' : conv?.agent_name ? `상담사 ${conv.agent_name} · 상담 중` : '상담사 연결 대기 중'}</small>
            </div>
          </div>
          {messages.length === 0 && !closed && <p className="kp-muted-center">궁금한 점을 남겨 주시면 상담사가 답변드려요.</p>}
          {messages.map((m) => {
            const day = formatDate(m.created_at);
            const showDay = day !== lastDay;
            lastDay = day;
            return (
              <div key={m.message_id}>
                {showDay && <div className="sp-chat-day">{day}</div>}
                <div className={`sp-msg ${m.sender === 'member' ? 'is-me' : ''}`}>
                  {m.sender === 'agent' && m.sender_name && <div className="sp-msg-name">{m.sender_name}</div>}
                  {/* 본문은 텍스트로만 렌더링(HTML 실행 금지) */}
                  <div className="sp-bubble">{m.body}</div>
                  <div className="sp-msg-time">{formatTime(m.created_at)}</div>
                </div>
              </div>
            );
          })}
          {closed && (
            <div className="sp-chat-closed" role="status">
              상담이 종료되었습니다.
            </div>
          )}
        </div>
        {error && <p className="sp-error sp-pad-x">{error}</p>}
        {closed && (
          <div className="sp-pad-x sp-chat-restart">
            <button className="kp-btn kp-btn-outline kp-btn-block" onClick={() => void startNew()} disabled={starting}>
              새 상담 시작하기
            </button>
          </div>
        )}
        <form
          className="sp-chat-input"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <input
            className="sp-input"
            placeholder={closed ? '상담이 종료되어 메시지를 보낼 수 없어요' : '메시지를 입력하세요'}
            value={text}
            maxLength={10000}
            onChange={(e) => setText(e.target.value)}
            aria-label="메시지"
            disabled={closed || !conv}
          />
          <button className="kp-btn kp-btn-primary" disabled={closed || !text.trim() || !conv}>
            전송
          </button>
        </form>
      </div>
    </>
  );
}

// ---------- 재료 필터 (E21) : 프리미엄 식품 추천 전용 ----------
const splitList = (s: string) =>
  s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
    .slice(0, 10);

export function FilterScreen() {
  const nav = useNav();
  const { me, setMe } = useSession();
  const [avoid, setAvoid] = useState(me?.profile.ingredient_filter.avoid.join(', ') ?? '');
  const [prefer, setPrefer] = useState(me?.profile.ingredient_filter.prefer.join(', ') ?? '');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!me) return null;

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      setMe(await api.updateProfile({ expected_version: me.profile.version, ingredient_filter: { avoid: splitList(avoid), prefer: splitList(prefer) } }));
      nav.reset('recommend');
    } catch (e) {
      setError(e instanceof Error ? e.message : '필터를 적용하지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <SubHeader title="재료 필터" />
      <Page
        footer={
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={() => void apply()} disabled={busy}>
            필터 적용
          </button>
        }
      >
        <h1 className="sp-hero">입맛에 맞게 골라보세요</h1>
        <p className="sp-desc">프리미엄 식품 추천에만 적용돼요.</p>
        <Field label="기피 재료" placeholder="예) 고수" value={avoid} onChange={(e) => setAvoid(e.target.value)} />
        <Note>추천에서 피하고 싶은 재료를 입력해 주세요.</Note>
        <Field label="선호 재료" placeholder="예) 현미" value={prefer} onChange={(e) => setPrefer(e.target.value)} />
        <Note>더 자주 추천받고 싶은 재료를 입력해 주세요.</Note>
        <p className="sp-desc">여러 재료는 쉼표로 구분해 주세요.</p>
        <h2 className="sp-subtitle">선택한 알레르기 · {knownAllergens(me.profile.allergies).map(allergenLabel).join(', ') || '없음'}</h2>
        <Note>재료 필터를 바꿔도 알레르기 설정은 유지돼요.</Note>
        {error && <p className="sp-error">{error}</p>}
      </Page>
    </>
  );
}

// ---------- 프리미엄 안내 (E28) ----------
export function PremiumScreen() {
  const nav = useNav();
  const [plan, setPlan] = useState<SubscriptionPlan | null>(null);
  useEffect(() => {
    api.listPlans().then((p) => setPlan(p[0] ?? null)).catch(() => setPlan(null));
  }, []);
  return (
    <>
      <SubHeader title="꿀픽 프리미엄" />
      <Page
        footer={
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={() => nav.push('payment')} disabled={!plan}>
            결제하기
          </button>
        }
      >
        <div className="sp-eyebrow">PREMIUM</div>
        <h1 className="sp-hero sp-hero-lg">
          더 많은 선택지,
          <br />더 나다운 추천.
        </h1>
        <p className="sp-desc">잠겨 있던 추천까지 한 번에 확인하세요.</p>
        <ol className="sp-benefits">
          {(plan?.benefits ?? []).map((b, i) => (
            <li key={b}>
              <span>{String(i + 1).padStart(2, '0')}</span> {b}
            </li>
          ))}
        </ol>
        <div className="sp-chipbox">
          {plan?.price ? `월 ${formatPrice(plan.price, plan.currency)}` : '구독 요금 · 결제 주기는 정책 확정 후 표시'}
        </div>
        <p className="sp-desc sp-mt16">결제수단을 선택한 후 결제를 진행합니다. 결제 결과에 따라 완료 또는 오류 화면을 안내합니다.</p>
      </Page>
    </>
  );
}

// ---------- 결제수단 선택 (E29) · 오류 (E31) ----------
// 실제 VAN/PG 연동 없이 결제 흐름 형식만 구현한다. 완료 여부는 서버 권한 조회로 확정한다.
const METHODS: { id: PaymentMethod; label: string }[] = [
  { id: 'card', label: '신용카드 결제' },
  { id: 'bank_transfer', label: '무통장 입금' },
];
const EASY_PAY: { id: PaymentMethod; label: string; cls: string; mark: string }[] = [
  { id: 'naverpay', label: '네이버페이', cls: 'is-naver', mark: 'N pay' },
  { id: 'kakaopay', label: '카카오페이', cls: 'is-kakao', mark: 'pay' },
  { id: 'tosspay', label: '토스페이', cls: 'is-toss', mark: 'toss pay' },
];

export function PaymentScreen() {
  const nav = useNav();
  const { refresh } = useSession();
  const [plan, setPlan] = useState<SubscriptionPlan | null>(null);
  const [method, setMethod] = useState<PaymentMethod | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [paymentMessage, setPaymentMessage] = useState('');
  // 같은 결제 시도의 재요청이 중복 결제가 되지 않도록 화면 진입 단위로 멱등 키를 고정한다.
  const idemKey = useRef(crypto.randomUUID());

  useEffect(() => {
    api.listPlans().then((p) => setPlan(p[0] ?? null)).catch(() => setPlan(null));
  }, []);

  const pay = async () => {
    if (!plan || !method || !agree) return;
    setBusy(true);
    try {
      const payment = await api.createSubscription(plan.plan_id, method, idemKey.current);
      if (payment.status === 'pending') {
        setPaymentMessage('결제 결과를 확인 중입니다. 같은 요청으로 다시 확인해 주세요.');
        return;
      }
      const sub = await api.getSubscription(); // 리다이렉트 성공만으로 프리미엄을 켜지 않는다
      if (!sub.active) throw new Error('not active');
      await refresh();
      void sendMessage({ type: 'reanalyze' }); // 혜택이 바뀌었으니 현재 페이지 추천을 다시 받는다
      nav.replace('paymentDone');
    } catch (error) {
      setPaymentMessage(error instanceof Error ? error.message : '결제 결과를 확인하지 못했어요.');
      setFailed(true);
      // 연결 오류 시에도 같은 멱등 키로 결과를 확인한다.
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <SubHeader title="결제하기" />
      <Page
        footer={
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={() => void pay()} disabled={!plan || plan.billing_mode === 'disabled' || !method || !agree || busy}>
            {busy ? '결제 진행 중…' : '결제하기'}
          </button>
        }
      >
        <div className="sp-card sp-pay-summary">
          <div className="sp-desc">상품명</div>
          <div className="sp-pay-name">{plan?.name ?? '꿀픽 프리미엄'}</div>
          <div className="sp-pay-row">
            <span>월 요금</span>
            <strong>{plan?.price ? formatPrice(plan.price, plan.currency) : '확정 예정'}</strong>
          </div>
        </div>
        <p role="status">{plan?.billing_mode === 'disabled' ? '결제 서비스가 아직 연결되지 않았습니다.' : plan?.billing_mode === 'mock' ? '개발용 테스트 결제입니다. 실제 청구는 발생하지 않습니다.' : ''}</p>
        {paymentMessage && <p role="status">{paymentMessage}</p>}
        <h2 className="sp-subtitle">결제수단</h2>
        <div className="sp-methods" role="radiogroup" aria-label="결제수단">
          {METHODS.map((m) => (
            <button key={m.id} role="radio" aria-checked={method === m.id} className={`sp-method ${method === m.id ? 'is-on' : ''}`} onClick={() => setMethod(m.id)}>
              {m.label}
            </button>
          ))}
          <div className="sp-easypay">
            {EASY_PAY.map((m) => (
              <button key={m.id} role="radio" aria-checked={method === m.id} className={`sp-method sp-method-easy ${method === m.id ? 'is-on' : ''}`} onClick={() => setMethod(m.id)}>
                <span className={`sp-paymark ${m.cls}`}>{m.mark}</span>
                <small>{m.label}</small>
              </button>
            ))}
          </div>
        </div>
        <div className="sp-mt16">
          <Checkbox checked={agree} onChange={setAgree}>
            [필수] 결제 내용을 확인하고 동의합니다.
          </Checkbox>
        </div>
        <p className="sp-desc">선택한 결제수단으로 결제를 진행합니다.</p>
      </Page>
      {failed && (
        <ConfirmDialog
          title="결제 오류"
          body={
            <>
              <strong>결제가 정상적으로 처리되지 않았습니다.</strong>
              <p className="sp-desc">{paymentMessage}</p>
            </>
          }
          confirmLabel="확인"
          cancelLabel={null}
          onConfirm={() => setFailed(false)}
        />
      )}
    </>
  );
}

// ---------- 결제 완료 (E30) ----------
export function PaymentDoneScreen() {
  const nav = useNav();
  return (
    <>
      <SubHeader title="결제 완료" onBack={() => nav.reset('recommend')} />
      <Page
        footer={
          <button className="kp-btn kp-btn-primary kp-btn-block" onClick={() => nav.reset('recommend')}>
            돌아가기
          </button>
        }
      >
        <div className="sp-done-check" aria-hidden="true">
          ✓
        </div>
        <h1 className="sp-hero sp-hero-lg">
          프리미엄 구독이
          <br />
          완료되었어요!
        </h1>
        <p className="sp-desc">이제 AI 추천 상품 5개와 식품 재료 필터를 이용할 수 있어요.</p>
        <Note>프리미엄 혜택이 지금부터 적용돼요.</Note>
      </Page>
    </>
  );
}
