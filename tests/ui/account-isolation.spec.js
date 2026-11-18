const {test, expect} = require('@playwright/test');
const password = 'AccountTest42!';
const unique = () => 'ac' + Date.now().toString(36) + Math.random().toString(36).slice(2,5);
for (const platform of ['extension','mobile']) {
  const base = platform === 'extension' ? 'http://127.0.0.1:5174' : 'http://127.0.0.1:8081';
  async function settings(page) {
    if(platform === 'mobile') await page.goto(base + '/settings');
    else { await page.goto(base + '/preview.html'); await page.getByRole('tab',{name:'설정',exact:true}).click(); }
  }
  async function shortcuts(page) {
    if(platform === 'mobile') await page.goto(base + '/browser');
    else await page.getByRole('tab',{name:'바로가기',exact:true}).click();
  }
  async function login(page, id) {
    await settings(page);
    await page.getByRole('button',{name:/로그인 해 주세요/}).click();
    await page.getByPlaceholder('아이디 입력',{exact:true}).fill(id);
    await page.getByPlaceholder('비밀번호 입력',{exact:true}).fill(password);
    await page.getByRole('button',{name:'로그인',exact:true}).click();
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('kp.auth') || 'null')?.login_id)).toBe(id);
    await settings(page);
    await expect(page.getByText(id,{exact:true})).toBeVisible();
  }
  test(`${platform}: live signup validation preserves whitespace and reports length`,async({page})=>{
    await settings(page);
    await page.getByRole('button',{name:/로그인 해 주세요/}).click();
    await page.getByRole('button',{name:'회원가입',exact:true}).click();
    const id=page.getByPlaceholder('아이디 입력',{exact:true});
    await id.fill('abc def');
    await expect(id).toHaveValue('abc def');
    await expect(page.getByText('아이디에는 공백을 사용할 수 없습니다.',{exact:true})).toBeVisible();
    await id.fill('valid123');
    await expect(page.getByText('아이디에는 공백을 사용할 수 없습니다.',{exact:true})).toHaveCount(0);
    const pw=page.getByPlaceholder('비밀번호 입력',{exact:true});
    await pw.fill('1234567');
    await expect(page.getByText(/현재 7자/)).toBeVisible();
    await pw.fill(password);
    await expect(page.getByText(/현재 7자/)).toHaveCount(0);
    await page.getByPlaceholder('비밀번호를 다시 입력하세요',{exact:true}).fill('different');
    await expect(page.getByText('비밀번호가 일치하지 않아요.',{exact:true})).toBeVisible();
  });
  test(`${platform}: bookmarks persist for A, stay hidden for B and guest`,async({page,request})=>{
    const a=unique(), b=unique(); const accounts=[];
    for(const login_id of [a,b]) {
      const res=await request.post(base+'/backend/v2/auth/signup',{data:{login_id,password,password_confirmation:password,consent_version:'2026-11-18-test',consent_accepted:true}});
      expect(res.status()).toBe(201); accounts.push({login_id,user_id:(await res.json()).data.user_id});
    }
    try {
      await login(page,a); await shortcuts(page);
      await page.getByRole('button',{name:'바로가기 추가',exact:true}).click();
      await page.getByLabel('이름',{exact:true}).fill('A 전용 상점');
      await page.getByPlaceholder('https://www.oasis.co.kr',{exact:true}).fill('https://example.com/item');
      await page.getByRole('button',{name:'추가',exact:true}).click();
      await expect(page.getByText('A 전용 상점',{exact:true})).toBeVisible();
      await expect(page.getByText('내가 저장',{exact:true})).toBeVisible();
      await page.reload();
      if(platform==='extension') await page.getByRole('tab',{name:'바로가기',exact:true}).click();
      await expect(page.getByText('A 전용 상점',{exact:true})).toBeVisible();
      await settings(page); await page.getByRole('button',{name:'로그아웃',exact:true}).click();
      await expect.poll(() => page.evaluate(() => localStorage.getItem('kp.auth'))).toBeNull();
      await shortcuts(page); await expect(page.getByText('A 전용 상점',{exact:true})).toHaveCount(0);
      await expect(page.getByRole('button',{name:'바로가기 추가',exact:true})).toBeDisabled();
      await login(page,b); await shortcuts(page);
      await expect(page.getByText('A 전용 상점',{exact:true})).toHaveCount(0);
      await settings(page); await page.getByRole('button',{name:'로그아웃',exact:true}).click();
      await expect.poll(() => page.evaluate(() => localStorage.getItem('kp.auth'))).toBeNull();
      await login(page,a); await shortcuts(page);
      await expect(page.getByText('A 전용 상점',{exact:true})).toBeVisible();
      // Another browser tab logs out: existing tab must immediately drop account-only UI.
      const second = await page.context().newPage();
      await settings(second);
      await second.getByRole('button',{name:'로그아웃',exact:true}).click();
      await expect(page.getByText('A 전용 상점',{exact:true})).toHaveCount(0);
      await second.close();
      await login(page,a); await shortcuts(page);
      await expect(page.getByText('A 전용 상점',{exact:true})).toBeVisible();
      await page.screenshot({path:`test-results/${platform}-account-isolation.png`});
    } finally {
      for(const {login_id} of accounts) {
        const res=await request.post(base+'/backend/v2/auth/login',{data:{login_id,password}});
        if(res.ok()) await request.post(base+'/backend/v2/me/withdrawal',{headers:{Authorization:'Bearer '+(await res.json()).data.token},data:{current_password:password}});
      }
    }
  });
}
