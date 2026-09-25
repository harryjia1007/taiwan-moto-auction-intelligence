# 行政執行署 CMS：GCP 臺灣區唯讀連線探針

正式 GitHub-hosted 排程曾在行政執行署 13 個分署的 `robots` 階段全部逾時。這只證明該 runner 的當次連線失敗，不證明官方拒絕連線，也不證明改放 GCP 一定成功。在變更正式排程前，可用本專案的 `python -m ingest.cms_gcp_probe` 在候選執行環境做一次受限檢查。

## 探針邊界

- 使用既有 `MojEnforcementCmsAdapter.healthcheck()`，先檢查程式內來源政策必須是 `ALLOW`，再依序讀取 13 個程式固定的官方分署 `robots.txt`（含核准的同站 `/robots` 導向）、官方宣告的同站 sitemap 與首頁。每一站仍遵守 robots、HTTPS host allowlist、MIME／大小上限、403／429 時該站停止，以及一秒一次的節流。
- 探針不持有資料庫憑證，因此**不會驗證資料庫內持久化的 `source_access_policies` 決策**；正式 `sync` 仍須執行既有 in-code 加 persisted 雙重政策檢查，兩者不可用這個探針互相替代。
- 不讀清單或案件明細，不接觸中央 CAPTCHA 查詢，不存 PDF、照片或原始網頁，不連 Supabase，不發布網站資料；不需要任何正式環境密鑰。
- 為控制測試時間，單次請求 5 秒、一次嘗試、每分署 15 秒、全部最多 210 秒；既有 3 個同類型連線失敗的斷路器可提前停止。程式只輸出一行固定欄位 JSON，含成功數、總數與分署代碼；不輸出 URL、公告、車牌、原始警告或例外文字。13/13 全部通過才以 exit code 0 結束，部分成功也回傳非零。
- 短逾時的單次失敗是「此環境未通過這次候選檢查」，不是網站沒有公告或永久不可用。遇 403、429、robots 改變或重複逾時，停止，先查來源規則與網路；不要改用代理、換 IP 或繞過限制。

本機可先驗證程式本身：

```sh
services/ingest/.venv/bin/python -m pytest -q services/ingest/tests/test_cms_gcp_probe.py
PYTHONPATH=services/ingest/src services/ingest/.venv/bin/python -m ingest.cms_gcp_probe
```

第二行會實際連線官方站，並不是離線測試；沒有網路或來源政策不可確認時會安全失敗。它也不是完整同步指令。

## GCP `asia-east1` 一次性驗證（須另行授權）

本次交付只有程式、離線測試與說明，**沒有建立 GCP 專案、容器倉庫、Job、排程或付費資源，也沒有執行 GCP 探針**。需要一個已由擁有人核准並設好帳務的 GCP 專案、已上傳且以本版程式建立的私人映像，以及一個沒有 Supabase 或發布權限的專用服務帳號。建置／上傳映像與執行 Job 可能產生 Cloud Build、Artifact Registry、Cloud Run、網路與記錄費用，不能保證為零；執行前先設定預算警示並檢查 [Cloud Run 價格](https://cloud.google.com/run/pricing)。

以下為**未執行的操作範例**（參照 Google 的 [Job 部署](https://docs.cloud.google.com/sdk/gcloud/reference/run/jobs/deploy)及[單次執行](https://docs.cloud.google.com/sdk/gcloud/reference/run/jobs/execute)參數）。只有在擁有人明確同意 GCP 試跑及其可能費用、填好三個占位值並核對映像內容後，才可複製執行。前置檢查會拒絕留白／占位值；映像需先從 `services/ingest/Dockerfile` 建置並上傳到該專案自己的 Artifact Registry，且不要在 Job 設定 Supabase 變數或密鑰。

```sh
export PROBE_PROJECT_ID='REPLACE_WITH_GCP_PROJECT_ID'
export PROBE_IMAGE='asia-east1-docker.pkg.dev/REPLACE_WITH_GCP_PROJECT_ID/REPLACE_WITH_REPOSITORY/REPLACE_WITH_IMAGE_TAG'
export PROBE_SERVICE_ACCOUNT='REPLACE_WITH_PROBE_SERVICE_ACCOUNT_EMAIL'

if [ -z "$PROBE_PROJECT_ID" ] || [ -z "$PROBE_IMAGE" ] || [ -z "$PROBE_SERVICE_ACCOUNT" ]; then
  echo '請先填入專案、映像與唯讀服務帳號'
  exit 1
fi
case "$PROBE_PROJECT_ID:$PROBE_IMAGE:$PROBE_SERVICE_ACCOUNT" in
  *REPLACE_WITH*|*' '* ) echo '請先替換所有占位值'; exit 1 ;;
esac

gcloud run jobs deploy cms-branch-preflight \
  --project="$PROBE_PROJECT_ID" \
  --region=asia-east1 \
  --image="$PROBE_IMAGE" \
  --service-account="$PROBE_SERVICE_ACCOUNT" \
  --command=python \
  --args=-m,ingest.cms_gcp_probe \
  --tasks=1 \
  --max-retries=0 \
  --task-timeout=300s \
  --cpu=1 \
  --memory=512Mi

gcloud run jobs execute cms-branch-preflight \
  --project="$PROBE_PROJECT_ID" \
  --region=asia-east1 \
  --wait
```

這裡沒有建立 Cloud Scheduler，也沒有設定 `ingest sync`、資料庫帳密或任何發布步驟；可在 GCP 主控台核對該次 Job 日誌中的單行 JSON 和非零／零退出狀態。若通過，還須獨立核對正式來源政策、13 站有界 discovery、資料庫 migration ledger、正式私有同步、artifact／snapshot 持久化與公開投影，才可能宣稱「行政執行署資料已修復」。**探針成功不等於找到任何案件，更不等於完整覆蓋行政執行署或正式網站已更新。**
