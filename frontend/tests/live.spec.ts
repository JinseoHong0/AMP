import { test, expect } from '@playwright/test';

// Real frontend ↔ real backend (no injected data). Run with the FastAPI server on :8000:
//   AMP_LIVE_API=1 npx playwright test tests/live.spec.ts
test.skip(!process.env.AMP_LIVE_API, 'requires a running backend (AMP_LIVE_API=1)');

test('listings page shows real upcoming shows from GET /api/events and filters on the server', async ({
  page,
}) => {
  const exceptions: string[] = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  const calls: URL[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname === '/api/events') {
      expect(response.status()).toBe(200);
      calls.push(url);
    }
  });

  await page.goto('/events');
  const cards = page.locator('.event-card');
  await expect(cards.first()).toBeVisible();
  const caption = page.locator('.result-heading .section-caption');
  await expect(caption).toHaveText(/총 \d+개 · 20개 표시/);
  await expect(cards).toHaveCount(20);
  expect(calls.at(-1)?.searchParams.get('upcoming')).toBe('true');

  // 20개 넘게 있으면 '공연 더 보기' → limit=50 재조회
  await page.getByRole('button', { name: '공연 더 보기' }).click();
  await expect(page).toHaveURL(/limit=50/);
  await expect.poll(() => calls.at(-1)?.searchParams.get('limit')).toBe('50');
  await expect(caption).toHaveText(/· 50개 표시/);

  // 지역 칩 → 서버 필터, 카드가 모두 신촌 공연장
  await page.getByRole('button', { name: '신촌', exact: true }).click();
  await expect(page).toHaveURL(/area=sinchon/);
  await expect.poll(() => calls.at(-1)?.searchParams.get('area')).toBe('sinchon');
  await expect(cards.first()).toContainText('아지토 라이브홀');
  const sinchonCount = await cards.count();
  await expect(caption).toHaveText(new RegExp(`총 ${sinchonCount}개`));

  // 가격 0(무료만) → max_price_krw=0 그대로 전송, 결과는 무료 공연만
  await page.getByRole('button', { name: '모든 동네' }).click();
  await page.getByRole('button', { name: '상세 필터' }).click();
  await page.getByLabel('최대 티켓 가격').fill('0');
  await expect.poll(() => calls.at(-1)?.searchParams.get('max_price_krw')).toBe('0');
  await expect(cards.first()).toBeVisible();
  for (const text of await cards.allInnerTexts()) expect(text).toContain('무료');

  // EN 전환 → locale=en 재조회, 번역 없는 원문은 명시 표시
  await page.getByRole('button', { name: 'EN', exact: true }).click();
  await expect.poll(() => calls.at(-1)?.searchParams.get('locale')).toBe('en');
  await expect(cards.first()).toContainText('English translation unavailable');

  expect(exceptions).toEqual([]);
});

test('detail page renders a real show from GET /api/events/{id}; unknown ids show "not found"', async ({
  page,
}) => {
  const exceptions: string[] = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  const detailCalls: number[] = [];
  page.on('response', (response) => {
    const match = new URL(response.url()).pathname.match(/^\/api\/events\/(\d+)$/);
    if (match) detailCalls.push(response.status());
  });

  await page.goto('/events?date=2026-11-07&area=hongdae&max_price_krw=40000');
  const card = page.locator('.event-card', { hasText: 'ADYNE SOLO CONCERT' });
  await card.click();
  await expect(page).toHaveURL(/\/events\/\d+$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'ADYNE SOLO CONCERT ‘ANOTHER WAY’',
  );
  await expect(page.getByRole('heading', { name: '방문 준비 카드' })).toBeVisible();
  const visit = page.locator('.visit-section');
  await expect(visit).toContainText('40,000원예매 가격 기준'); // 대표가 + 가격 출처
  await expect(visit).toContainText('40,000원 / 45,000원'); // 예매가 / 현장가
  await expect(visit).toContainText('20:00'); // KST 공연 시작
  await expect(visit).toContainText('확인 필요'); // 입장 시각 미확인을 공연 시작으로 대체하지 않음
  await expect(page.locator('.detail-intro')).toContainText('에이다인');
  // 공연장 가이드 (GET /api/venues/{id}): 데이터에 없는 주소·층수·입구 정보는 '확인 필요'
  const guide = page.locator('.venue-guide');
  await expect(guide.getByRole('heading', { name: '벨르(구 벨로주)' })).toBeVisible();
  await expect(guide).toContainText('홍대');
  await expect(guide.locator('.info-list')).toContainText('건물 층수확인 필요');
  await expect(page.getByRole('alert')).toHaveCount(0); // 공연장 영역 오류 없음
  // dev 모드 React StrictMode 는 effect 를 두 번 실행하므로 호출 횟수가 아니라 상태만 확인
  expect(detailCalls.length).toBeGreaterThan(0);
  expect(detailCalls.every((status) => status === 200)).toBe(true);

  // 뒤로가기 링크는 필터가 유지된 목록으로
  await page.getByRole('link', { name: '공연 탐색으로' }).click();
  await expect(page).toHaveURL(/\/events\?date=2026-11-07&area=hongdae&max_price_krw=40000$/);

  await page.goto('/events/99999999');
  await expect(page.getByRole('heading', { name: '공연 정보를 찾을 수 없어요.' })).toBeVisible();
  expect(exceptions).toEqual([]);
});

test('venue guide shows only the address and floor stated in the data (클럽에반스)', async ({
  page,
}) => {
  const exceptions: string[] = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  await page.goto('/events?area=hongdae&limit=50');
  await page.locator('.event-card', { hasText: '클럽에반스' }).first().click();
  const guide = page.locator('.venue-guide');
  await expect(guide.getByRole('heading', { name: '클럽에반스' })).toBeVisible();
  await expect(guide.locator('.venue-address')).toHaveText('서울시 마포구 와우산로 63 2층');
  await expect(guide.locator('.info-list')).toContainText('건물 층수2F');
  // 입장 시각: 데이터의 '입장 오후 7시'를 공연 시작(20:00)과 구분해 표시
  await expect(page.locator('.visit-section')).toContainText('공연 시작 20:00');
  expect(exceptions).toEqual([]);
});

test('registration venue picker lists real venues from GET /api/venues and searches on the server', async ({
  page,
}) => {
  const exceptions: string[] = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  const searches: (string | null)[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname === '/api/venues') {
      expect(response.status()).toBe(200);
      searches.push(url.searchParams.get('q'));
    }
  });
  await page.goto('/admin/register');
  await page.getByRole('button', { name: '포스터 없이 직접 입력하기' }).click();
  const select = page.locator('#form-venue_id');
  await expect(select.locator('option', { hasText: 'Club FF · 홍대' })).toHaveCount(1);
  const total = (await select.locator('option').count()) - 1; // 첫 항목은 안내 문구
  expect(total).toBeGreaterThanOrEqual(20);

  await page.getByPlaceholder('공연장 이름으로 검색').fill('에반스');
  await expect.poll(() => searches.at(-1)).toBe('에반스');
  await expect(select.locator('option')).toHaveCount(2);
  await select.selectOption({ label: '클럽에반스 · 홍대' });
  await expect(select).not.toHaveValue('');

  // 선택한 공연장은 검색어를 바꿔도 목록에 유지
  await page.getByPlaceholder('공연장 이름으로 검색').fill('아지토');
  await expect(select.locator('option', { hasText: '아지토 라이브홀 · 신촌' })).toHaveCount(1);
  await expect(select.locator('option', { hasText: '클럽에반스 · 홍대' })).toHaveCount(1);
  expect(exceptions).toEqual([]);
});

test('home recommendation uses POST /api/recommend: filters-only works, query-only shows the AI failure honestly', async ({
  page,
}) => {
  const exceptions: string[] = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  const bodies: unknown[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/recommend') bodies.push(request.postDataJSON());
  });

  await page.goto('/');
  await page.getByRole('button', { name: '직접 조건 선택' }).click();
  await page.getByLabel('동네').selectOption('hongdae');
  await page.getByLabel('최대 티켓 가격').fill('40000');
  await page.getByRole('button', { name: '공연 추천받기' }).click();

  const cards = page.locator('.event-card');
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeLessThanOrEqual(3);
  await expect(page.locator('.applied-conditions')).toContainText('적용된 필수 조건');
  await expect(page.locator('.applied-conditions')).toContainText('홍대');
  await expect(page.locator('.applied-conditions')).toContainText('40,000');
  await expect(page.locator('.recommendation-reason').first()).toContainText('홍대 공연이며');
  await expect(page.getByText('AI 추천 순위는 적용되지 않았어요', { exact: false })).toBeVisible();
  await expect(page.getByText(/필수 조건에 맞는 공연 \d+개/)).toBeVisible();
  expect(bodies.at(-1)).toMatchObject({
    query: '',
    filters: { area: 'hongdae', max_price_krw: 40000 },
    locale: 'ko',
  });

  // 추천 카드 → 상세로 이동
  await cards.first().click();
  await expect(page).toHaveURL(/\/events\/\d+$/);
  await expect(page.getByRole('heading', { name: '방문 준비 카드' })).toBeVisible();

  // 검색어만 (AI 연결 공란) → 503 → AI 실패 안내, 입력은 유지
  await page.goto('/');
  const query = page.getByLabel('원하는 공연 설명');
  await query.fill('홍대에서 잔잔한 공연');
  await page.getByRole('button', { name: '공연 추천받기' }).click();
  await expect(page.getByRole('alert')).toContainText('AI 요청을 완료하지 못했어요.');
  await expect(query).toHaveValue('홍대에서 잔잔한 공연');
  expect(exceptions).toEqual([]);
});

test('manual registration saves through POST /api/events and the new show opens from the real DB', async ({
  page,
}, info) => {
  const exceptions: string[] = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  const posts: { status: number; body: unknown }[] = [];
  page.on('response', async (response) => {
    if (
      new URL(response.url()).pathname === '/api/events' &&
      response.request().method() === 'POST'
    )
      posts.push({ status: response.status(), body: response.request().postDataJSON() });
  });
  const title = `브라우저 등록 확인 ${info.project.name} ${Date.now()}`;

  await page.goto('/admin/register');
  await page.getByRole('button', { name: '포스터 없이 직접 입력하기' }).click();
  await page.locator('#form-title').fill(title);
  await page.getByPlaceholder('공연장 이름으로 검색').fill('에반스');
  await page.locator('#form-venue_id').selectOption({ label: '클럽에반스 · 홍대' });
  await page.locator('#form-starts_at_local').fill('2026-12-24T20:00');
  await page.locator('#form-advance_price_krw').fill('30000');
  await page.locator('#form-door_price_krw').fill('35000');
  await page.locator('#form-review_confirmed').check();
  await page.getByRole('button', { name: '원문 확인 후 공연 등록' }).click();

  await expect(page.getByRole('heading', { name: '공연이 등록되었어요.' })).toBeVisible();
  await expect(
    page.getByText('공연은 등록되었으나 영어 번역은 아직 준비되지 않았습니다.'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: '영어 번역 재시도' })).toBeVisible(); // AI 번역은 미연결
  expect(posts).toHaveLength(1); // 한 번만 저장
  expect(posts[0].status).toBe(201);
  expect(posts[0].body).not.toHaveProperty('price_basis');
  expect(posts[0].body).toMatchObject({
    title,
    price_krw: 30000,
    data_origin: 'demo',
    review_confirmed: true,
  });

  await page.getByRole('link', { name: '등록한 공연 보기' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
  const visit = page.locator('.visit-section');
  await expect(visit).toContainText('30,000원예매 가격 기준');
  await expect(visit).toContainText('30,000원 / 35,000원');
  await expect(page.locator('.venue-guide')).toContainText('서울시 마포구 와우산로 63 2층');
  expect(exceptions).toEqual([]);
});
