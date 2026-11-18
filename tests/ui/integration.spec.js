const { test, expect } = require('@playwright/test');
const extension = process.env.EXTENSION_UI_URL || 'http://127.0.0.1:5174';
const mobile = process.env.MOBILE_UI_URL || 'http://127.0.0.1:8081';
const password = 'LocalTest42!';
const unique = () => 'ui' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

async function backend(page, path, body, method = 'GET') {
  return page.evaluate(async ({ path, body, method }) => {
    const token = JSON.parse(localStorage.getItem('kp.auth') || 'null')?.token;
    const r = await fetch('/backend' + path, { method,
      headers: { ...(token ? { Authorization: 'Bearer ' + token } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    return { status: r.status, json: await r.json().catch(() => null) };
  }, { path, body, method });
}
async function clickCheckbox(page, name) {
  const checkbox = page.getByRole('checkbox', { name });
  // 확장의 실제 클릭 대상은 숨겨진 input을 감싼 label이다.
  if (await checkbox.evaluate(element => element.tagName === 'INPUT')) await checkbox.locator('..').click();
  else await checkbox.click();
  await expect(checkbox).toBeChecked();
}

async function signup(page, id) {
  await page.getByPlaceholder('아이디 입력', { exact: true }).fill(id);
  await page.getByRole('button', { name: '중복확인', exact: true }).click();
  await expect(page.getByText('사용 가능한 아이디', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByPlaceholder('비밀번호 입력', { exact: true }).fill(password);
  await page.getByPlaceholder('비밀번호를 다시 입력하세요', { exact: true }).fill(password);
  await clickCheckbox(page, /필수/);
  const saved = page.waitForResponse(r => r.url().endsWith('/v2/auth/signup') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '동의하고 가입하기', exact: true }).click();
  expect((await saved).status()).toBe(201);
  await expect(page.getByText(id, { exact: true })).toBeVisible();
  expect((await backend(page, '/v2/me')).json.data.login_id).toBe(id);
}

test('extension UI: real signup, profile persistence, support, upload/cancel, mock subscription and withdrawal', async ({ page }) => {
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const id = unique();
  await page.goto(extension + '/preview.html');
  await expect(page.getByText(/실제 API 모드/)).toBeVisible();
  await page.getByRole('tab', { name: '설정', exact: true }).click();
  await page.getByRole('button', { name: /로그인 해 주세요/ }).click();
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
  await signup(page, id);
  await page.getByRole('button', { name: new RegExp(id) }).click();
  await page.getByRole('button', { name: '개인정보 수정', exact: true }).click();
  await page.getByLabel('생년월일', { exact: true }).fill('2001-02-03');
  await page.getByRole('button', { name: '변경사항 저장', exact: true }).click();
  await expect.poll(async () => (await backend(page, '/v2/me')).json.data.profile.birth_date).toBe('2001-02-03');
  await page.reload();
  await page.getByRole('tab', { name: '설정', exact: true }).click();
  await expect(page.getByText(id, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '고객지원', exact: true }).click();
  await page.getByRole('textbox', { name: '메시지', exact: true }).fill('실제 DB 상담 저장 ' + id);
  await page.getByRole('button', { name: '전송', exact: true }).click();
  await expect(page.getByText('실제 DB 상담 저장 ' + id, { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole('tab', { name: '설정', exact: true }).click();
  await page.getByRole('button', { name: '고객지원', exact: true }).click();
  await expect(page.getByText('실제 DB 상담 저장 ' + id, { exact: true })).toBeVisible();
  await page.getByLabel('분석 테스트 이미지').setInputFiles({ name: 'fixture.png', mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8sI+LgYGBiYGBgYGBAQAVsAG8p0alPQAAAABJRU5ErkJggg==', 'base64') });
  await page.getByRole('button', { name: '분석 접수 테스트', exact: true }).click();
  await expect(page.getByText('분석 상태: queued', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '분석 취소', exact: true }).click();
  await expect(page.getByText('분석 상태: cancelled', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '뒤로', exact: true }).click();
  await page.getByRole('button', { name: new RegExp(id) }).click();
  await page.getByRole('button', { name: '프리미엄 알아보기', exact: true }).click();
  await page.getByRole('button', { name: '결제하기', exact: true }).click();
  await expect(page.getByText(/개발용 테스트 결제입니다/)).toBeVisible();
  await page.getByRole('radio', { name: '신용카드 결제', exact: true }).click();
  await clickCheckbox(page, /필수/);
  await page.getByRole('button', { name: '결제하기', exact: true }).click();
  await expect.poll(async () => (await backend(page, '/v2/me/subscription')).json.data.active).toBe(true);
  await page.reload();
  await page.getByRole('tab', { name: '설정', exact: true }).click();
  await page.getByRole('button', { name: new RegExp(id) }).click();
  await page.getByRole('button', { name: '자동 결제 해지', exact: true }).click();
  await page.getByRole('button', { name: '해지하기', exact: true }).click();
  await expect(page.getByText('자동 결제 해지됨', { exact: true })).toBeVisible();
  expect((await backend(page, '/v2/me/subscription')).json.data.active).toBe(true);
  await page.screenshot({ path: 'test-results/extension-integrated.png' });
  await page.getByRole('button', { name: '개인정보 수정', exact: true }).click();
  await expect(page.getByLabel('생년월일', { exact: true })).toHaveValue('2001-02-03');
  await page.getByRole('button', { name: '회원 탈퇴', exact: true }).click();
  await page.getByPlaceholder('현재 비밀번호 입력', { exact: true }).fill(password);
  await clickCheckbox(page, /탈퇴에 동의/);
  await page.getByRole('button', { name: '탈퇴하기', exact: true }).click();
  await page.getByRole('dialog', { name: '정말 탈퇴할까요?' }).getByRole('button', { name: '탈퇴하기', exact: true }).click();
  await expect(page.getByText('탈퇴가 접수됐어요', { exact: true })).toBeVisible();
  expect((await backend(page, '/v2/me')).status).toBe(401);
  expect(errors).toEqual([]);
});

test('mobile web: actual API signup, persisted profile and conversation', async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const id = unique();
  await page.goto(mobile + '/signup');
  await signup(page, id);
  await page.goto(mobile + '/mypage');
  await expect(page.getByText(`${id}님, 안녕하세요!`, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '개인정보 수정', exact: true }).click();
  await page.getByLabel('생년월일', { exact: true }).fill('2000-05-06');
  await page.getByRole('button', { name: '변경사항 저장', exact: true }).click();
  await expect.poll(async () => (await backend(page, '/v2/me')).json.data.profile.birth_date).toBe('2000-05-06');
  await page.goto(mobile + '/support');
  await page.getByRole('textbox', { name: '메시지', exact: true }).fill('모바일 상담 저장 ' + id);
  await page.getByRole('button', { name: '전송', exact: true }).click();
  await expect(page.getByText('모바일 상담 저장 ' + id, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('모바일 상담 저장 ' + id, { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/mobile-integrated.png' });
  const withdrawn = await backend(page, '/v2/me/withdrawal', { current_password: password }, 'POST');
  expect(withdrawn.status).toBe(202);
  expect(errors).toEqual([]);
});
