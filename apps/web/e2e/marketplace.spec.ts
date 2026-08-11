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

test("search, filter, favorite, and evidence workflow", async ({ page }) => {
  await page.goto("/motorcycles");
  await expect(page.getByRole("heading", { name: "找到下一台值得出手的機車" })).toBeVisible();
  await page.getByRole("link", { name: "有照片的單台車" }).click();
  await expect(page.getByRole("link", { name: "SYM HM12VB", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "警用機車 7 臺", exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "SYM HM12VB", exact: true }).click();
  await expect(page.getByLabel("共 2 張官方照片")).toBeVisible();
  await page.getByRole("button", { name: "下一張照片" }).click();
  await expect(page.getByAltText("SYM HM12VB 官方照片 2／2")).toBeVisible();
  await expect(page.getByText("2011 年 5 月", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /前往官方每筆 2 元查詢/ })).toHaveAttribute("href", "https://mvdvan.mvdis.gov.tw/mvdvan/");
  await expect(page.getByText("目前車子發不動，不確定是否有那一部位機件故障，或電池沒電。", { exact: false })).toBeVisible();
  const favorite = page.getByRole("button", { name: "加入收藏" });
  await favorite.click();
  await expect(page.getByRole("button", { name: "移除收藏" })).toHaveAttribute("aria-pressed", "true");
  await page.goto("/motorcycles?view=favorites");
  await expect(page.getByRole("heading", { name: "找到下一台值得出手的機車" })).toBeVisible();
  await expect(page.getByRole("link", { name: "SYM HM12VB", exact: true })).toBeVisible();
});

test("judicial no-photo records use an explicit text state instead of a generic vehicle graphic", async ({ page }) => {
  await page.goto("/motorcycles/fixture-judicial-ksd-2894");
  await expect(page.getByLabel("官方未提供照片")).toBeVisible();
  await expect(page.getByText("NO ATTACHMENT")).toBeVisible();
  await expect(page.locator(".detail-media img")).toHaveCount(0);
});

test("nationwide source and disposal-origin filters are bookmarkable", async ({ page }) => {
  await page.goto("/motorcycles?source=pcc&origin=IMPOUNDED_UNCLAIMED");
  await expect(page.getByRole("link", { name: "逾期未領回機車 4 輛", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "花蓮地院報廢機車標售批次", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("資料來源")).toHaveValue("pcc");
  await expect(page.getByLabel("處分性質")).toHaveValue("IMPOUNDED_UNCLAIMED");
  await page.goto("/motorcycles?source=judicial&origin=JUDICIAL_EXECUTION");
  await expect(page.getByRole("link", { name: "KYMCO SJ25HE", exact: true })).toBeVisible();
  await expect(page.locator(".moto-card").filter({ hasText: "KYMCO SJ25HE" }).getByText("司法院 22 地院動產法拍")).toBeVisible();
  await expect(page.getByLabel("資料來源")).toHaveValue("judicial");
  await page.getByRole("link", { name: "普通重型機車 NVX-2001", exact: true }).click();
  const judicialPdf = page.getByRole("link", { name: "查看這台機車的法院公告 PDF" });
  await expect(judicialPdf).toHaveAttribute("href", /DO_VIEWPDF\.htm\?filenm=%2Fctd%2F11508%2F03152010519\.005\.pdf/);
});

test("source health makes planned coverage explicit", async ({ page }) => {
  await page.goto("/sources");
  await expect(page.getByRole("heading", { name: "資料來源健康狀態" })).toBeVisible();
  await expect(page.getByText("PLANNED").first()).toBeVisible();
  await expect(page.locator("table").getByText("ACTIVE", { exact: true })).toHaveCount(0);
});

test("active, ended, and sorting controls are URL-backed", async ({ page }) => {
  await page.goto("/motorcycles?view=ended&sort=auction_desc");
  await expect(page.getByRole("link", { name: "已結束紀錄", exact: true })).toHaveClass(/active/);
  await expect(page.getByLabel("排序方式")).toHaveValue("auction_desc");
  await expect(page.getByText("截止不等於成交")).toBeVisible();
});
