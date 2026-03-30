AIEarn.today — 完整架設說明
🗂 檔案結構
```
aiearn-today/
├── index.html          # 英文首頁
├── index-zh.html       # 中文首頁
├── news-zh.html        # 每日新聞頁（中文，自動更新）
├── fetch_news.py       # 自動更新 Python 腳本
├── requirements.txt    # Python 套件清單
├── _archive/           # 每日文章 JSON 備份（自動生成）
└── .github/
    └── workflows/
        └── daily-update.yml  # GitHub Actions 自動排程
```
---
🚀 今天就能上線：完整步驟
Step 1 — 購買網域
推薦在以下購買 `.com`（約US$10-12/年）：
Namecheap — namecheap.com（最便宜）
Cloudflare Registrar — cloudflare.com（at-cost，最划算）
Google Domains → 現已移轉至 Squarespace
網域建議：`aiearn.today`、`aiearntools.com`、`makeaimoneytoday.com`
---
Step 2 — 建立 GitHub Repository
到 github.com 建立新 repo
命名：`aiearn-today`（或你的網域名）
設定為 Public（GitHub Pages 免費版需要 Public）
上傳所有檔案：
```bash
   git init
   git add .
   git commit -m "初始上傳 AIEarn.today"
   git remote add origin https://github.com/你的帳號/aiearn-today.git
   git push -u origin main
   ```
---
Step 3 — 開啟 GitHub Pages（免費主機）
進入 repo → Settings → Pages
Source：選 `main` branch，`/ (root)` 資料夾
點 Save → 幾分鐘後網站上線
預設網址：`https://你的帳號.github.io/aiearn-today/`
---
Step 4 — 綁定自訂網域
在 GitHub Pages 設定中輸入你的網域（如 `aiearn.today`）
到 Namecheap / Cloudflare DNS 新增以下記錄：
```
   類型：A    主機名：@    值：185.199.108.153
   類型：A    主機名：@    值：185.199.109.153
   類型：A    主機名：@    值：185.199.110.153
   類型：A    主機名：@    值：185.199.111.153
   類型：CNAME  主機名：www  值：你的帳號.github.io
   ```
等待 DNS 生效（通常 5-30 分鐘）
GitHub 會自動啟用 HTTPS
---
Step 5 — 設定 ANTHROPIC_API_KEY（自動更新必需）
到 console.anthropic.com 申請 API Key
在 GitHub repo → Settings → Secrets and variables → Actions
點 "New repository secret"
Name：`ANTHROPIC_API_KEY`
Value：貼上你的 API key
點 Add secret
---
Step 6 — 測試自動更新
到 GitHub repo → Actions
找到 "每日AI新聞自動更新"
點 "Run workflow" 手動測試
看執行 log，確認抓到文章並成功 commit
成功後每天早上 08:00 自動執行
---
📊 預估成本
項目	費用	說明
網域 .com	~US$12/年	Namecheap 或 Cloudflare
GitHub Pages	免費	靜態網站主機
GitHub Actions	免費	每月 2000 分鐘免費
Anthropic API	~US$1-3/月	每天約跑 100-300 tokens
總計	~US$13-15/年	基本上幾乎免費
---
💰 收入設定
Google AdSense 申請
網站上線後等 1-3 個月（需要有足夠內容和流量）
到 adsense.google.com 申請
審核通過後，將 AdSense 代碼貼入 HTML 的廣告位置區塊
HTML 中已預留廣告位，搜尋 `<!-- Google AdSense -->` 替換
Affiliate 連結
Jasper AI：去 jasper.ai/affiliate 申請，佣金 30%/月
Copy.ai：去 copy.ai/affiliate 申請，佣金 45% 首月
ElevenLabs：去 elevenlabs.io/affiliates 申請，佣金 22%/月
Udemy：透過 Impact.com 平台申請，佣金最高 15%
Coursera：透過 Coursera Affiliates 申請，佣金 10-45%
取得連結後，搜尋 HTML 中的 `href="#"` 替換成真實 Affiliate 連結
---
🔧 客製化
新增更多 RSS 來源
編輯 `fetch_news.py` 的 `RSS_FEEDS` 清單
調整更新時間
編輯 `.github/workflows/daily-update.yml` 的 `cron` 設定：
`'0 0 * * *'` = 台北早上 08:00（UTC 00:00）
`'0 1 * * *'` = 台北早上 09:00（UTC 01:00）
新增更多頁面
複製 `news-zh.html` 作為模板，每個頁面只需要調整 `id="article-list"` 區塊
---
📈 SEO 基礎設定
每個頁面已包含：
`<meta name="description">` — 搜尋引擎摘要
`<meta name="keywords">` — 關鍵字
`<link rel="alternate" hreflang>` — 中英文版本互相標記
Open Graph tags — 社群媒體分享預覽
建議後續設定：
到 search.google.com/search-console 提交 Sitemap
新增 `sitemap.xml`（可用工具自動生成）
新增 `robots.txt`
---
🆘 常見問題
Q: GitHub Actions 跑完但頁面沒更新？
A: 確認 `ANTHROPIC_API_KEY` 有設定。到 Actions 看執行 log。
Q: fetch_news.py 本機測試
```bash
pip install anthropic feedparser
export ANTHROPIC_API_KEY="sk-ant-..."
python fetch_news.py
```
Q: 網域 DNS 設定後多久生效？
A: Cloudflare 通常 5 分鐘，一般 DNS 最多 24 小時。
Q: GitHub Pages 支援哪些檔案格式？
A: 純靜態檔案：HTML, CSS, JS, 圖片。不支援 PHP/Node 等後端。
