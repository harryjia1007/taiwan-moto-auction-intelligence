# 政府電子採購網財物變賣

官方入口：<https://web.pcc.gov.tw/opas/aspam/public/indexAspam>

`pcc` adapter 使用公開 GET 查詢的 `searchAssetsName` 欄位，以「機車、汽機車、電動機車、重型機車」發現全國公告；再依結果列的官方主鍵讀取公開明細。搜尋結果中的「電力機車」鐵路車輛會排除。

明細解析機關、案號、公告次數、公告／截止日期、底價、保證金、資格、標的所在地、查看時間與附加說明。重要欄位保存逐字官方證據。投標資格含廢機動車輛回收資格時標為 `LICENSED_RECYCLER_ONLY`。

處分性質依公告文字判定，不依刊登機關猜測：

- 交通違規移置、逾期未領回：`IMPOUNDED_UNCLAIMED`
- 扣押、沒收、沒入：`CRIMINAL_SEIZURE_OR_FORFEITURE`
- 明確報廢／廢機車：`SCRAP_DISPOSAL`
- 其餘公有財物變賣：`PUBLIC_ASSET_DISPOSAL`

若頁面沒有分列車牌、引擎或車身號碼，不建立虛構車輛；保留為可搜尋的整批 lot。外部機關附件網址只保留為證據，必須先把該官方網域登錄到專屬來源後才會下載。
