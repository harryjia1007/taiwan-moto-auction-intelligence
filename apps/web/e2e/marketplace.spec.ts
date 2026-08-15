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
  await expect(page.getByLabel("目前瀏覽條件")).toContainText("進行中・30 天內・普通重型機車・125 c.c. 以下・126–150 c.c.");
  await expect(page.getByLabel("目前套用條件").getByText("排氣量：125 c.c. 以下")).toBeVisible();
  await page.getByRole("link", { name: /看歷史/ }).click();
  await expect(page).toHaveURL(/view=ended/);
  await expect(page).not.toHaveURL(/within=/);
});

test("search, filter, favorite, and evidence workflow", async ({ page }) => {
  await page.goto("/motorcycles");
  await expect(page.getByRole("heading", { name: "今天想找什麼機車？" })).toBeVisible();
  await expect(page.getByLabel("地區")).toBeVisible();
  await expect(page.getByLabel("資料來源")).toBeVisible();
  await expect(page.getByLabel("排序方式")).toBeVisible();
  await page.getByRole("link", { name: /看歷史/ }).click();
  await expect(page).toHaveURL(/view=ended/);
  await page.getByRole("link", { name: /有照片的單台車/ }).click();
  await expect(page).toHaveURL(/view=ended.*hasPhotos=true.*singleVehicle=true/);
  await expect(page.getByRole("link", { name: "SYM HM12VB", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "警用機車 7 臺", exact: true })).toHaveCount(0);
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
  await page.goto("/motorcycles?view=favorites");
  await expect(page.getByRole("heading", { name: "今天想找什麼機車？" })).toBeVisible();
  await expect(page.getByRole("link", { name: "SYM HM12VB", exact: true })).toBeVisible();
});

test("judicial no-photo records use an explicit text state instead of a generic vehicle graphic", async ({ page }) => {
  await page.goto("/motorcycles/fixture-judicial-ksd-2894");
  await expect(page.getByLabel("官方未提供照片")).toBeVisible();
  await expect(page.getByText("官方未附照片")).toBeVisible();
  await expect(page.locator(".detail-media img")).toHaveCount(0);
});

test("no-photo marketplace cards stay compact and keep the deadline in the auction facts", async ({ page }) => {
  await page.goto("/motorcycles?view=active");
  await expect(page.getByPlaceholder("例如：品牌、重型機車、車牌、法院機關")).toBeVisible();
  const card = page.locator(".moto-card.no-official-photo").filter({ hasText: "TEST-COURT-04" });
  const notice = card.locator(".photo-absence-card");
  await expect(notice.getByText("官方未附照片")).toBeVisible();
  await expect(card.locator(".auction-state")).toHaveCount(0);
  await expect(card.locator(".deadline-copy")).toContainText("截止");
  await expect(card).not.toContainText("NO ATTACHMENT");
  expect(await notice.evaluate((element) => element.getBoundingClientRect().height)).toBeLessThan(200);
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

test("nationwide source and disposal-origin filters are bookmarkable", async ({ page }) => {
  await page.goto("/motorcycles?view=scrap&source=pcc&origin=IMPOUNDED_UNCLAIMED");
  await expect(page.getByRole("link", { name: "逾期未領回機車 4 輛", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "花蓮地院報廢機車標售批次", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("資料來源")).toHaveValue("pcc");
  await expect(page.getByLabel("處分性質")).toHaveValue("IMPOUNDED_UNCLAIMED");
  await page.goto("/motorcycles?source=judicial&origin=JUDICIAL_EXECUTION");
  await expect(page.getByRole("link", { name: "KYMCO SJ25HE", exact: true })).toBeVisible();
  await expect(page.locator(".moto-card").filter({ hasText: "KYMCO SJ25HE" }).getByText("司法院 22 地院動產法拍")).toBeVisible();
  await expect(page.getByLabel("資料來源")).toHaveValue("judicial");
  await page.getByRole("link", { name: "普通重型機車（司法測試）", exact: true }).click();
  const judicialSource = page.getByRole("link", { name: /查看司法拍賣來源說明/ }).first();
  await expect(judicialSource).toHaveAttribute("href", "https://www.judicial.gov.tw/tw/lp-85-1.html");
});

test("source health makes planned coverage explicit", async ({ page }) => {
  await page.goto("/sources");
  await expect(page.getByRole("heading", { name: "資料來源健康狀態" })).toBeVisible();
  await expect(page.getByText("未實作").first()).toBeVisible();
  await expect(page.locator("table").getByText("正式同步", { exact: true })).toHaveCount(0);
  await expect(page.getByText("官方搜尋有 CAPTCHA", { exact: false })).toBeVisible();
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
