const { test, expect } = require('@playwright/test');

test('extension: launcher works before analysis, hides with panel and returns on close', async ({page}) => {
  await page.goto('http://127.0.0.1:5174/preview.html?panel=closed');
  const launcher = page.getByRole('button', { name: '꿀픽 사이드바 열기', exact: true });
  await expect(launcher).toBeVisible();
  await launcher.click();
  await expect(page.getByRole('tab', { name: 'AI 추천', exact: true })).toBeVisible();
  await expect(launcher).toHaveCount(0);
  await expect(page.getByRole('switch', { name: '상품 추천', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '사이드바 닫기', exact: true }).click();
  await expect(launcher).toBeVisible();
  await launcher.click();
  await expect(launcher).toHaveCount(0);
});

for (const platform of ['extension', 'mobile']) {
  test(`${platform}: guest browses real catalog without analysis uploads; recent sites removed`, async ({page,request}) => {
    const base = platform === 'extension' ? 'http://127.0.0.1:5174' : 'http://127.0.0.1:8081';
    const analyses=[];
    page.on('request', req => { if (req.method()==='POST' && new URL(req.url()).pathname.endsWith('/analyses')) analyses.push(req.url()); });
    const response=await request.get(base+'/backend/v2/recommendations/basic');
    expect(response.status()).toBe(200);
    const cards=(await response.json()).data;
    expect(cards.length).toBeGreaterThan(0); // real DB seed, no fabricated UI fixture
    await page.goto(base+(platform==='extension'?'/preview.html':'/'));
    await expect(page.getByText(cards[0].name, {exact:true})).toBeVisible();
    await page.getByRole('button',{name:'식품',exact:true}).click();
    await expect(page.getByText(/현재 표시할 상품이 없어요/)).toBeVisible();
    await page.getByRole('button',{name:'상품',exact:true}).click();
    await expect(page.getByText(cards[0].name,{exact:true})).toBeVisible();
    if(platform==='extension') await page.getByRole('tab',{name:'바로가기',exact:true}).click();
    else await page.goto(base+'/browser');
    await expect(page.getByText('쇼핑몰 바로가기',{exact:true})).toBeVisible();
    await expect(page.getByText('최근 방문 페이지',{exact:true})).toHaveCount(0);
    await expect(page.getByText('마지막 페이지 다시 열기',{exact:true})).toHaveCount(0);
    expect(analyses).toEqual([]);
    expect((await request.get(base+'/backend/v2/me/analyses')).status()).toBe(401);
  });
}
