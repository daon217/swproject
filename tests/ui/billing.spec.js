const { test, expect } = require('@playwright/test');
test('pending payment keeps one idempotent request and never enables premium', async ({ page, request }) => {
  test.skip(process.env.UI_PAYMENT_OUTCOME !== 'pending', 'Run against an explicit pending mock-billing server');
  const base = process.env.EXTENSION_UI_URL || 'http://127.0.0.1:5174';
  const id = 'pend' + Date.now().toString(36);
  const password = 'PendingTest42!';
  const signup = await request.post(base + '/backend/v2/auth/signup', { data: {
    login_id: id, password, password_confirmation: password,
    consent_accepted: true, consent_version: 'integration-test', allergies: [], gender: null, birth_date: null,
  } });
  expect(signup.status()).toBe(201);
  await page.goto(base + '/preview.html');
  await page.getByRole('tab', { name: '설정', exact: true }).click();
  await page.getByRole('button', { name: /로그인 해 주세요/ }).click();
  await page.getByPlaceholder('아이디 입력', { exact: true }).fill(id);
  await page.getByPlaceholder('비밀번호 입력', { exact: true }).fill(password);
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.getByRole('button', { name: new RegExp(id) }).click();
  await page.getByRole('button', { name: '프리미엄 알아보기', exact: true }).click();
  await page.getByRole('button', { name: '결제하기', exact: true }).click();
  await page.getByRole('radio', { name: '신용카드 결제', exact: true }).click();
  await page.getByRole('checkbox', { name: /필수/ }).click();
  let paymentId;
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = page.waitForResponse(r => r.url().endsWith('/v2/me/subscriptions') && r.request().method() === 'POST');
    await page.getByRole('button', { name: '결제하기', exact: true }).click();
    const r = await response; expect(r.status()).toBe(202);
    const result = (await r.json()).data;
    if (paymentId) expect(result.payment_id).toBe(paymentId);
    paymentId = result.payment_id;
    await expect(page.getByText(/결제 결과를 확인 중입니다/)).toBeVisible();
  }
  const state = await page.evaluate(async () => {
    const { token } = JSON.parse(localStorage.getItem('kp.auth'));
    const headers = { Authorization: 'Bearer ' + token };
    const sub = await fetch('/backend/v2/me/subscription', { headers }).then(r => r.json());
    const payments = await fetch('/backend/v2/me/payments', { headers }).then(r => r.json());
    return { sub: sub.data, payments: payments.data };
  });
  expect(state.sub.active).toBe(false);
  expect(state.payments).toHaveLength(1);
  expect(state.payments[0].status).toBe('pending');
  await page.screenshot({ path: 'test-results-pending/pending-payment.png' });
});
