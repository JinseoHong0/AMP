import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

// Existing docs examples are injected only inside isolated tests. The shipped app has no mock data.
const markdown = readFileSync(new URL('../../docs/API.md', import.meta.url), 'utf8');
const examples = Array.from(markdown.matchAll(/```json\r?\n([\s\S]*?)\r?\n```/g), (match) =>
  JSON.parse(match[1]),
);
const recommendation = examples.find((item) => item.status === 'ok' && item.items?.[0]?.event);
const detail = examples.find((item) => item.venue_id && item.title && item.starts_at);
const venue = examples.find((item) => item.address && item.entrance_hint_ko);
const venues = examples.find((item) => item.items?.[0]?.area && item.items[0].name);
const created = examples.find(
  (item) => item.status === 'published' && item.translation && item.message,
);
const eventList = examples.find((item) => typeof item.limit === 'number' && item.items);
const extraction = examples.find((item) => item.extracted && item.upload_id);

async function injectReadContracts(page: Page) {
  await page.evaluate(
    async (values) => {
      // Use the module actually loaded by Vite, including its HMR version query.
      const path =
        performance
          .getEntriesByType('resource')
          .find((entry) => new URL(entry.name).pathname === '/src/api/client.ts')?.name ||
        '/src/api/client.ts';
      const { ampApi } = await import(/* @vite-ignore */ path);
      ampApi.recommend = async () => values.recommendation;
      ampApi.getEvent = async () => values.detail;
      ampApi.getVenue = async () => values.venue;
      ampApi.listVenues = async () => values.venues;
    },
    { recommendation, detail, venue, venues },
  );
}

test('frontend-only navigation, search filters and unavailable state are honest', async ({
  page,
}, info) => {
  const exceptions: string[] = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  const apiRequests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('localhost:8000')) apiRequests.push(request.url());
  });
  // The listings adapter is connected; simulate an unreachable backend to keep this test about honest failure.
  await page.route('http://localhost:8000/**', (route) => route.abort('connectionrefused'));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('오늘의 나에게');
  await page.screenshot({ path: `test-results/home-${info.project.name}.png`, fullPage: true });
  const query = page.getByLabel('원하는 공연 설명');
  await query.fill('신촌에서 좌석 공연만');
  await page.getByRole('button', { name: '직접 조건 선택' }).click();
  await page.getByLabel('최대 티켓 가격').fill('0');
  await page.getByRole('button', { name: '공연 추천받기' }).click();
  await expect(page.getByRole('alert')).toContainText('지금은 정보를 불러올 수 없어요');
  await expect(query).toHaveValue('신촌에서 좌석 공연만');
  await page.getByRole('link', { name: '모든 공연 둘러보기' }).click();
  await expect(page).toHaveURL(/\/events$/);
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: 'EN', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Small stages');
  await expect(
    page.getByText('Information is temporarily unavailable.', { exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect(exceptions).toEqual([]);
  // Only the connected endpoints this flow uses were attempted (recommend, then listings KO/EN).
  const paths = apiRequests.map((url) => new URL(url).pathname);
  expect(paths).toContain('/api/recommend');
  expect(paths).toContain('/api/events');
  expect(paths.every((path) => path === '/api/recommend' || path === '/api/events')).toBe(true);
});

test('recommendation, detail, AI translation and original view follow existing API examples', async ({
  page,
}, info) => {
  await page.goto('/');
  await injectReadContracts(page);
  await page.getByLabel('원하는 공연 설명').fill('좌석 공연만');
  await page.getByRole('button', { name: '공연 추천받기' }).click();
  await expect(page.locator('.event-card')).toHaveCount(1);
  await page.locator('.event-card-link').click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText(detail.title);
  await expect(page.getByRole('heading', { name: '방문 준비 카드' })).toBeVisible();
  await page.getByRole('button', { name: 'EN', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText(detail.title_en);
  await expect(page.getByText('AI-translated', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'View original' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText(detail.title);
  await page.screenshot({ path: `test-results/detail-${info.project.name}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test('AI clarification is distinct from zero results and incomplete search', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(async (example) => {
    // Use the module actually loaded by Vite, including its HMR version query.
    const path =
      performance
        .getEntriesByType('resource')
        .find((entry) => new URL(entry.name).pathname === '/src/api/client.ts')?.name ||
      '/src/api/client.ts';
    const { ampApi } = await import(/* @vite-ignore */ path);
    ampApi.recommend = async () => ({
      ...example,
      status: 'needs_clarification',
      items: [],
      total_matches: null,
      applied_conditions: null,
      preferences: [],
      notice: null,
      clarification: '어느 날짜의 공연을 찾고 있나요?',
    });
  }, recommendation);
  await page.getByLabel('원하는 공연 설명').fill('언젠가 공연');
  await page.getByRole('button', { name: '공연 추천받기' }).click();
  await expect(page.getByText('어느 날짜의 공연을 찾고 있나요?')).toBeVisible();
  await expect(page.getByText('조건에 맞는 공연이 아직 없어요.')).toHaveCount(0);
  await page.getByRole('button', { name: '검색 조건 수정하기' }).click();
  await expect(page.getByLabel('원하는 공연 설명')).toBeFocused();
});

test('manual registration validates input; translation retry never re-registers', async ({
  page,
}, info) => {
  await page.goto('/');
  await injectReadContracts(page);
  await page.evaluate(async (result) => {
    // Use the module actually loaded by Vite, including its HMR version query.
    const path =
      performance
        .getEntriesByType('resource')
        .find((entry) => new URL(entry.name).pathname === '/src/api/client.ts')?.name ||
      '/src/api/client.ts';
    const { ampApi } = await import(/* @vite-ignore */ path);
    (window as unknown as { submissions: unknown[] }).submissions = [];
    ampApi.createEvent = async (payload: unknown) => {
      (window as unknown as { submissions: unknown[] }).submissions.push(payload);
      return { ...result, translation: { status: 'failed', generated_at: null }, warnings: [] };
    };
    ampApi.retryTranslation = async (id: number) => ({ id, translation: result.translation });
  }, created);
  await page.locator('nav:visible').getByRole('link', { name: '공연 등록', exact: true }).click();
  await page.getByRole('button', { name: '포스터 없이 직접 입력하기' }).click();
  await page.getByRole('button', { name: '원문 확인 후 공연 등록' }).click();
  await expect(page.getByText('공연명을 1~120자로 입력해 주세요.')).toBeVisible();
  await page.locator('#form-title').fill(detail.title);
  await page.locator('#form-venue_id').selectOption(String(venues.items[0].id));
  await page.locator('#form-starts_at_local').fill('2026-11-07T19:00');
  await page.locator('#form-advance_price_krw').fill('15000');
  await page.locator('#form-door_price_krw').fill('20000');
  await page.locator('#form-review_confirmed').check();
  await page.screenshot({ path: `test-results/register-${info.project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: '원문 확인 후 공연 등록' }).click();
  await expect(page.getByRole('heading', { name: '공연이 등록되었어요.' })).toBeVisible();
  await page.getByRole('button', { name: '영어 번역 재시도' }).click();
  await expect(page.getByText('영어 안내 생성 완료 · AI-translated')).toBeVisible();
  const submissions = await page.evaluate(
    () => (window as unknown as { submissions: Record<string, unknown>[] }).submissions,
  );
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).toMatchObject({
    price_krw: 15000,
    upload_id: null,
    review_confirmed: true,
  });
  expect(submissions[0]).not.toHaveProperty('title_en');
  expect(submissions[0]).not.toHaveProperty('price_basis');
});

test('file validation rejects disguised and oversized images, and unknown routes remain navigable', async ({
  page,
}) => {
  await page.goto('/admin/register');
  await page.getByLabel('포스터 이미지 선택').setInputFiles({
    name: 'broken.png',
    mimeType: 'image/png',
    buffer: Buffer.from('not an image'),
  });
  await expect(
    page.getByText('올바른 이미지 파일을 읽을 수 없어요. 다른 파일을 선택해 주세요.'),
  ).toBeVisible();
  await page.getByLabel('포스터 이미지 선택').setInputFiles({
    name: 'large.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.alloc(5 * 1024 * 1024 + 1),
  });
  await expect(page.getByText('5MB 이하 이미지를 선택해 주세요.')).toBeVisible();
  await page.goto('/missing');
  await expect(page.getByRole('heading', { name: '찾고 있는 페이지가 없어요.' })).toBeVisible();
  await page.getByRole('link', { name: '처음으로' }).click();
  await expect(page).toHaveURL(/\/$/);
});

test('the separate listings page loads without a query and is not capped at three recommendations', async ({
  page,
}) => {
  await page.goto('/');
  await page.evaluate(async (example) => {
    // Use the module actually loaded by Vite, including its HMR version query.
    const path =
      performance
        .getEntriesByType('resource')
        .find((entry) => new URL(entry.name).pathname === '/src/api/client.ts')?.name ||
      '/src/api/client.ts';
    const { ampApi } = await import(/* @vite-ignore */ path);
    ampApi.listEvents = async (params: unknown) => {
      (window as unknown as { lastListParams: unknown }).lastListParams = params;
      return {
        ...example,
        total: 4,
        items: Array.from({ length: 4 }, (_, index) => ({
          ...example.items[0],
          id: example.items[0].id + index,
        })),
      };
    };
  }, eventList);
  await page.getByRole('link', { name: '모든 공연 둘러보기' }).click();
  await expect(page.locator('.event-card')).toHaveCount(4);
  await page.getByRole('button', { name: '상세 필터' }).click();
  await page.getByLabel('최대 티켓 가격').fill('0');
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { lastListParams: { max_price_krw: number } }).lastListParams
            .max_price_krw,
      ),
    )
    .toBe(0);
  await expect(page).toHaveURL(/max_price_krw=0/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test('real image preview uses the selected file and a specified extraction fills only original fields', async ({
  page,
}) => {
  await page.goto('/');
  await injectReadContracts(page);
  await page.evaluate(async (example) => {
    // Use the module actually loaded by Vite, including its HMR version query.
    const path =
      performance
        .getEntriesByType('resource')
        .find((entry) => new URL(entry.name).pathname === '/src/api/client.ts')?.name ||
      '/src/api/client.ts';
    const { ampApi } = await import(/* @vite-ignore */ path);
    ampApi.parsePoster = async (file: File) => {
      (window as unknown as { uploadedName: string }).uploadedName = file.name;
      return example;
    };
  }, extraction);
  // Use a screenshot of the actual wordmark, not a fabricated concert asset.
  const image = await page.locator('.wordmark').screenshot();
  await page.locator('nav:visible').getByRole('link', { name: '공연 등록', exact: true }).click();
  await page
    .getByLabel('포스터 이미지 선택')
    .setInputFiles({ name: 'wordmark.png', mimeType: 'image/png', buffer: image });
  await expect(page.getByAltText('선택한 포스터 미리보기')).toBeVisible();
  await page.getByRole('button', { name: '포스터에서 정보 가져오기' }).click();
  await expect(page.locator('#form-title')).toHaveValue(extraction.extracted.title);
  await expect(page.locator('#form-review_confirmed')).not.toBeChecked();
  await expect(page.locator('#form-venue_id')).toHaveValue(String(extraction.venue_match.venue_id));
  await expect(page.locator('input[name="title_en"]')).toHaveCount(0);
  expect(
    await page.evaluate(() => (window as unknown as { uploadedName: string }).uploadedName),
  ).toBe('wordmark.png');
});
