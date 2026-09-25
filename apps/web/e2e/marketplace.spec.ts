import { expect, test } from "@playwright/test";

test("server health is public and never cached", async ({ request }) => {
  const response = await request.get("/api/health");

  expect(response.ok()).toBe(true);
  expect(response.headers()["cache-control"]).toContain("no-store");
  await expect(response.json()).resolves.toMatchObject({
    status: "ok",
    service: "taiwan-moto-auction-intelligence-web",
    mode: "fixture",
  });
});

test("public portfolio demo is synthetic, filterable, and does not require owner login", async ({ page }) => {
  await page.goto("/demo?view=active&within=30&cc=le-125&cc=126-150");
  await expect(page.getByRole("heading", { name: /先看能不能買/ })).toBeVisible();
  await expect(page.getByText("互動作品展示・全部為合成資料")).toBeVisible();
  await expect(page.getByText("進行中・30 天內・125 以下 c.c.・126–150 c.c.", { exact: false })).toBeVisible();
  await expect(page.getByText("都會通勤機車 A")).toBeVisible();
  await expect(page.getByText("大型重型機車 B")).toHaveCount(0);
  await expect(page.getByText("普通輕型機車 D")).toHaveCount(0);
  await expect(page.locator('a[href*="DO_VIEWPDF"], a[href*="AUID="]')).toHaveCount(0);
});

test("CC filters and ended state are URL-backed with a clear browsing summary", async ({ page }) => {
  await page.goto("/motorcycles?view=active&within=30&vehicleClass=ORDINARY_HEAVY&cc=le-125&cc=126-150");
  await expect(page.getByLabel("目前瀏覽條件")).toContainText("進行中・機車・30 天內・普通重型機車・125 c.c. 以下・126–150 c.c.");
  await expect(page.getByLabel("目前套用條件").getByText("排氣量：125 c.c. 以下")).toBeVisible();
  await page.getByRole("link", { name: /看歷史/ }).click();
  await expect(page).toHaveURL(/view=ended/);
  await expect(page).not.toHaveURL(/within=/);
});

test("quick presets keep the shopper's source and region, and scrap navigation clears conflicts", async ({ page }) => {
  await page.goto("/motorcycles?view=all&source=judicial&county=臺中市&vehicleType=MOTORCYCLE");
  await page.getByRole("link", { name: /有照片的單台車/ }).click();
  await expect(page).toHaveURL(/source=judicial/);
  await expect(page).toHaveURL(/county=/);
  await expect(page).toHaveURL(/vehicleType=MOTORCYCLE/);
  await expect(page).toHaveURL(/hasPhotos=true/);
  await expect(page).toHaveURL(/singleVehicle=true/);
  await expect(page.getByLabel("目前瀏覽條件")).toContainText("臺中市");
  await expect(page.getByLabel("目前瀏覽條件")).toContainText("司法院地院法拍");

  await page.goto("/motorcycles?view=active&source=judicial&eligibility=NATURAL_PERSON_ALLOWED&registration=NORMAL_TRANSFER&excludeScrap=true");
  await page.getByRole("link", { name: /報廢／回收/ }).click();
  await expect(page).toHaveURL(/view=scrap/);
  await expect(page).toHaveURL(/source=judicial/);
  await expect(page).not.toHaveURL(/eligibility=|registration=|excludeScrap=/);
});

test("CC options show counts under the other active filters and remain useful for multi-select", async ({ page }) => {
  await page.goto("/motorcycles?view=all&vehicleType=MOTORCYCLE&source=judicial&eligibility=UNKNOWN&cc=le-125");
  const ccFilter = page.locator(".cc-filter");
  await expect(ccFilter.getByText("125 c.c. 以下（4）", { exact: true })).toBeVisible();
  await expect(ccFilter.getByText("151–250 c.c.（1）", { exact: true })).toBeVisible();
  await expect(ccFilter.getByText("官方未提供（2）", { exact: true })).toBeVisible();
  await expect(page.getByLabel("目前瀏覽條件")).toContainText("共 4 筆");
});

test("search, filter, favorite, and evidence workflow", async ({ page }) => {
  await page.goto("/motorcycles");
  await expect(page.getByRole("heading", { name: "今天想找什麼車？" })).toBeVisible();
  await expect(page.getByLabel("地區")).toBeVisible();
  await expect(page.getByLabel("資料來源")).toBeVisible();
  await expect(page.getByLabel("排序方式")).toBeVisible();
  await page.getByRole("link", { name: /看歷史/ }).click();
  await expect(page).toHaveURL(/view=ended/);
  await page.getByRole("link", { name: /有照片的單台車/ }).click();
  await expect(page).toHaveURL(/view=ended.*hasPhotos=true.*singleVehicle=true/);
  await expect(page.getByRole("link", { name: "SYM HM12VB", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "警用機車 7 臺", exact: true })).toHaveCount(0);
  const resultCard = page.locator(".moto-card").filter({ hasText: "SYM HM12VB" });
  await expect(resultCard.locator(".card-image").getByRole("button", { name: /收藏/ })).toHaveCount(0);
  await expect(resultCard.locator(".card-topline-actions").getByRole("button", { name: /收藏/ })).toBeVisible();
  await page.getByRole("link", { name: "SYM HM12VB", exact: true }).click();
  const detailGallery = page.getByLabel("共 2 張官方照片");
  await expect(detailGallery).toBeVisible();
  await detailGallery.getByRole("button", { name: "下一張照片" }).click();
  await expect(page.getByAltText("SYM HM12VB 官方照片 2／2")).toBeVisible();
  await expect(page.getByText("2011 年 5 月", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /前往官方每筆 2 元查詢/ })).toHaveAttribute("href", "https://mvdvan.mvdis.gov.tw/mvdvan/");
  await expect(page.getByText("合成測試：目前無法發動，原因未確認。", { exact: false })).toBeVisible();
  const favorite = page.getByRole("button", { name: "加入收藏" });
  await favorite.click();
  await expect(page.getByRole("button", { name: "移除收藏" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("已加入收藏", { exact: true })).toBeVisible();
  await page.goto("/motorcycles?view=favorites");
  await expect(page.getByRole("heading", { name: "今天想找什麼車？" })).toBeVisible();
  await expect(page.getByRole("link", { name: "SYM HM12VB", exact: true })).toBeVisible();
});

test("judicial no-photo records omit the media block and keep a compact fact label", async ({ page }) => {
  await page.goto("/motorcycles/fixture-judicial-ksd-2894");
  await expect(page.getByText("官方未附照片")).toBeVisible();
  await expect(page.locator(".detail-media")).toHaveCount(0);
});

test("no-photo marketplace cards omit empty media and keep deadline plus favorite controls", async ({ page }) => {
  await page.goto("/motorcycles?view=active");
  await expect(page.getByPlaceholder("例如：品牌、重型機車、車牌、法院機關")).toBeVisible();
  const card = page.locator(".moto-card.no-official-photo").filter({ hasText: "TEST-COURT-04" });
  await expect(card.locator(".card-image")).toHaveCount(0);
  await expect(card.locator(".auction-state")).toHaveCount(0);
  await expect(card.locator(".deadline-copy")).toContainText("截止");
  await expect(card.getByRole("button", { name: /收藏/ })).toBeVisible();
  await expect(card).not.toContainText("NO ATTACHMENT");
});

test("identified judicial vehicles can be favorited from the card and appear in favorites", async ({ page }) => {
  await page.goto("/motorcycles?view=active&source=judicial");
  const card = page.locator(".moto-card").filter({ hasText: "TEST-COURT-04" });
  const favorite = card.getByRole("button", { name: "加入收藏" });
  await expect(favorite).toBeVisible();
  await favorite.click();
  await expect(card.getByRole("button", { name: "移除收藏" })).toHaveAttribute("aria-pressed", "true");
  await page.goto("/motorcycles?view=favorites");
  await expect(page.getByRole("link", { name: "SYM 普通重型機車", exact: true })).toBeVisible();
});

test("private comparison persists, rejects a fourth vehicle, and stays inside the mobile viewport", async ({ page }) => {
  await page.goto("/motorcycles?view=all&source=judicial");
  const compareButtons = page.locator(".compare-toggle");
  expect(await compareButtons.count()).toBeGreaterThanOrEqual(4);

  await compareButtons.nth(0).click();
  await compareButtons.nth(1).click();
  const tray = page.getByLabel("候選車輛比較列");
  await expect(tray).toContainText("2／3 輛");
  await expect(tray.getByRole("link", { name: "比較 2 輛" })).toBeVisible();

  await page.reload();
  await expect(page.locator(".compare-toggle").nth(0)).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("候選車輛比較列")).toContainText("2／3 輛");

  await page.getByLabel("候選車輛比較列").getByRole("button", { name: "清空" }).click();
  await expect(page.getByLabel("候選車輛比較列")).toHaveCount(0);
  await page.locator(".compare-toggle").nth(0).click();
  await page.locator(".compare-toggle").nth(1).click();
  await page.locator(".compare-toggle").nth(2).click();
  await page.locator(".compare-toggle").nth(3).click();
  await expect(page.getByText("最多只能同時比較 3 輛，請先移除一輛再加入。", { exact: true })).toBeVisible();
  await expect(page.locator(".compare-toggle").nth(3)).toHaveAttribute("aria-pressed", "false");

  const selectedNames = page.getByLabel("候選車輛比較列").getByRole("button", { name: /從比較移除：/ });
  await expect(selectedNames).toHaveCount(3);
  await selectedNames.first().click();
  await expect(page.getByLabel("候選車輛比較列")).toContainText("2／3 輛");
  await page.locator(".compare-toggle").nth(0).click();

  const viewport = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.width + 1);

  await page.getByLabel("候選車輛比較列").getByRole("link", { name: "比較 3 輛" }).click();
  await expect(page.getByRole("heading", { name: "比較候選車輛" })).toBeVisible();
  await expect(page.getByLabel("候選車輛比較表")).toBeVisible();
  await expect(page.locator(".comparison-table tbody tr")).toHaveCount(14);
  const comparisonViewport = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(comparisonViewport.scrollWidth).toBeLessThanOrEqual(comparisonViewport.width + 1);
});

test("nationwide source and disposal-origin filters are bookmarkable", async ({ page }) => {
  await page.goto("/motorcycles?view=scrap&source=pcc&origin=IMPOUNDED_UNCLAIMED");
  await expect(page.getByRole("link", { name: "逾期未領回機車 4 輛", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "花蓮地院報廢機車標售批次", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("資料來源")).toHaveValue("pcc");
  await expect(page.getByLabel("處分性質")).toHaveValue("IMPOUNDED_UNCLAIMED");
  await page.goto("/motorcycles?view=all&source=judicial&origin=JUDICIAL_EXECUTION");
  await expect(page.getByRole("link", { name: "KYMCO SJ25HE", exact: true })).toBeVisible();
  await expect(page.locator(".moto-card").filter({ hasText: "KYMCO SJ25HE" }).getByText("司法院 22 地院動產法拍")).toBeVisible();
  await expect(page.getByLabel("資料來源")).toHaveValue("judicial");
  await page.getByRole("link", { name: "普通重型機車（司法測試）", exact: true }).click();
  const judicialSource = page.getByRole("link", { name: /查看司法院法拍來源/ }).first();
  await expect(judicialSource).toHaveAttribute("href", "https://www.judicial.gov.tw/tw/lp-85-1.html");
});

test("source health makes planned coverage explicit", async ({ page }) => {
  await page.goto("/sources");
  await expect(page.getByRole("heading", { name: "資料來源健康狀態" })).toBeVisible();
  await expect(page.getByText("未實作").first()).toBeVisible();
  await expect(page.locator("table").getByText("正式同步", { exact: true })).toHaveCount(0);
  await expect(page.getByText("官方搜尋有驗證碼", { exact: false })).toBeVisible();
});

test("scrap and recycler-only records stay in their dedicated area", async ({ page }) => {
  await page.goto("/motorcycles?view=active");
  await expect(page.getByRole("link", { name: "花蓮地院報廢機車標售批次", exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: /報廢／回收/ }).click();
  await expect(page).toHaveURL(/view=scrap/);
  await expect(page.getByRole("link", { name: "花蓮地院報廢機車標售批次", exact: true })).toBeVisible();
});

test("active, ended, and sorting controls are URL-backed", async ({ page }) => {
  await page.goto("/motorcycles?view=ended&sort=auction_desc");
  await expect(page.getByRole("link", { name: /看歷史/ })).toHaveClass(/active/);
  await expect(page.getByLabel("排序方式")).toHaveValue("auction_desc");
  await expect(page.locator(".result-note")).toContainText("截止不等於成交");
});

test("car listings use car-specific cards and detail language without inventing history prices", async ({ page }) => {
  await page.goto("/motorcycles?view=all&vehicleType=CAR");
  await expect(page.getByRole("link", { name: "TOYOTA 小客車（測試）", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "公務小貨車（測試）", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "TOYOTA 小客車（測試）", exact: true }).click();
  await expect(page.getByText("汽車類別", { exact: true })).toBeVisible();
  await expect(page.getByText("小客車／轎車", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("機車級別", { exact: true })).toHaveCount(0);
  const history = page.getByRole("heading", { name: "拍賣歷史" }).locator("..");
  await expect(history).toContainText("官方未提供");
  await expect(history).not.toContainText("NT$0");
});

test("switching vehicle type clears incompatible motorcycle filters before submit", async ({ page }) => {
  await page.goto("/motorcycles?view=all&vehicleType=MOTORCYCLE&vehicleClass=ORDINARY_HEAVY&cc=le-125");
  await page.getByLabel("車輛類型").selectOption("CAR");
  await page.locator(".core-submit").click();
  await expect(page).toHaveURL(/vehicleType=CAR/);
  await expect(page).not.toHaveURL(/vehicleClass=ORDINARY_HEAVY/);
  await expect(page).not.toHaveURL(/cc=le-125/);
  await expect(page.getByRole("link", { name: "TOYOTA 小客車（測試）", exact: true })).toBeVisible();
});

test("cursor pagination preserves filters and exposes a bookmarkable next batch", async ({ page }) => {
  await page.goto("/motorcycles?view=all&vehicleType=MOTORCYCLE&limit=2");
  const firstPageTitles = await page.locator(".card-title a").allTextContents();
  expect(firstPageTitles).toHaveLength(2);
  const next = page.getByRole("link", { name: /下一批結果/ });
  await expect(next).toBeVisible();
  await next.click();
  await expect(page).toHaveURL(/cursor=/);
  await expect(page).toHaveURL(/limit=2/);
  await expect(page.getByRole("link", { name: /回第一頁/ })).toBeVisible();
  const secondPageTitles = await page.locator(".card-title a").allTextContents();
  expect(secondPageTitles).toHaveLength(2);
  expect(secondPageTitles).not.toEqual(firstPageTitles);
});
