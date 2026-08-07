---
name: keyword-validator
description: Use when validating whether a keyword/niche is worth building a content site or tool around. Triggers on "验证关键词" "选词判断" "keyword validation" "niche validation" "SERP analysis" "能不能做" or when user provides candidate keywords and asks about search volume, competition, or feasibility. Requires niche-google-trends-mcp and a Chrome instance with CDP on port 9223 (same as Google Trends MCP).
---

# Keyword Validator — 关键词选词判断工作流

对候选关键词执行四维自动化验证，输出结构化判断卡，回答"这个词能不能做"。

## 前置条件

1. **niche-google-trends-mcp** 已配置并运行（提供 Trends 对比能力）
2. **Chrome + CDP 端口 9223**（Google Trends MCP 启动时已自动开启）
3. **Patchright** 已安装（在 google-trends-mcp 的 venv 中）

验证方式：
```bash
curl -s "http://127.0.0.1:9223/json/version" | python3 -c "import sys,json; print(json.load(sys.stdin)['Browser'])"
```

如果 Chrome 未运行，让用户先启动 Google Trends MCP（它会自动拉起 Chrome）。

## 四维验证流程

对每个候选词，按顺序执行：

### Step 1: Google Trends 热度对比

用 `niche-google-trends-mcp` 的 `trends_compare` 工具：

- 将候选词与 **GPTs** 对比（GPTs 日均约 3000-5000 搜索量）
- timeframe 用 `3m`（3 个月看趋势走向）
- 判断标准：

| 曲线形态 | 含义 | 判断 |
|---|---|---|
| 持续上行 / 接近或超过 GPTs | 有搜索量 | 继续验证 |
| 平稳 | 存量词，有一定量 | 看竞争再定 |
| 下降 | 热度消退 | 谨慎 |
| 山形（暴涨→暴跌） | 陷阱词 | 不做 |
| 全部为 0 | 无人搜索 | 不做 |

### Step 2: Google Autocomplete 细分关键词

直接用 curl 调 Google Suggest API（不需要浏览器）：

```bash
curl -s "https://suggestqueries.google.com/complete/search?q=KEYWORD+&client=firefox&hl=en" \
  | python3 -c "import sys,json; [print(s) for s in json.load(sys.stdin)[1]]"
```

- 替换 `KEYWORD` 为候选词（空格用 `+` 连接）
- 结果即为该词的细分长尾词
- 细分词越多 → 越容易规划内容矩阵
- 注意检查搜索意图是否一致（如 "chart generator" 混杂了占星/数据图表两种意图）

### Step 3: Google SERP 首页竞争分析

通过 Patchright + CDP 连接已运行的 Chrome 实例，打开 Google 搜索页，提取前 10 结果的域名并分类。

**核心代码模式**（用 google-trends-mcp 的 venv 运行）：

```python
from patchright.async_api import async_playwright

pw = await async_playwright().start()
browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
context = browser.contexts[0]
page = await context.new_page()

await page.goto(f"https://www.google.com/search?q={query}&num=10&hl=en",
               wait_until="domcontentloaded", timeout=30000)
await asyncio.sleep(4)

results = await page.evaluate("""
    () => {
        const items = [];
        const seen = new Set();
        for (const link of document.querySelectorAll('a[href^="http"]')) {
            const href = link.getAttribute('href');
            if (!href || href.includes('google.com') || href.includes('gstatic.com')) continue;
            const h3 = link.querySelector('h3');
            if (!h3) continue;
            const title = h3.innerText.trim();
            if (!title || seen.has(href)) continue;
            seen.add(href);
            items.push({ url: href, title: title.substring(0, 100) });
        }
        return items.slice(0, 10);
    }
""")
```

**域名分类规则**（按领域调整）：

通用分类：
- **强竞争**：`fandom.com`, `wiki.gg`, `wikipedia.org`（wiki 类）；`game8.co`, `progameguides.com`, `pockettactics.com`（成熟攻略站）；行业头部 SaaS（`canva.com`, `adobe.com` 等）
- **中等竞争**：`ign.com`, `gamespot.com`, `polygon.com`（大媒体）；`etsy.com`, `amazon.com`（电商平台）
- **弱竞争**：`youtube.com`, `reddit.com`, `pinterest.com`（UGC 平台）；小站、个人博客、新工具站

**判断规则**：
- 强竞争 ≥ 7/10 → ❌ 首页竞争大，新手难切入
- 强竞争 ≤ 3/10 → ✅ 首页竞争弱，有机会
- 其他 → ⚠️ 中等竞争，看细分长尾词

**重要**：每次查询之间间隔 3-5 秒，避免触发 Google 反爬。每日不超过 50 次查询。

### Step 4: 域名可用性查询（可选）

```bash
# .com 域名 — 用 RDAP
curl -s -o /dev/null -w "%{http_code}" "https://rdap.verisign.com/com/v1/domain/TARGET.com"
# 200 = 已注册, 404 = 可用

# 或 whois
whois TARGET.com 2>&1 | grep -i "no match"
# 有输出 = 可用
```

## 输出格式：单词判断卡

对每个候选词输出：

```
【候选词】关键词
【Trends 趋势】涨/平/跌；与 GPTs 对比（约 x%）；曲线形态
【细分关键词】数量 + 列举前 5-10 个
【首页竞争】前 10 网站分类；强竞争占比 x/10
【做/不做】结论
【理由】1-3 条对应上述维度的依据
```

多个候选词时，额外输出汇总判断表：

```
| | 候选词 1 | 候选词 2 | 候选词 3 |
|---|---|---|---|
| Trends vs GPTs | | | |
| 细分关键词数量 | | | |
| 首页竞争（强/总） | | | |
| 做/不做 | | | |
```

## 按领域定制域名分类

SERP 竞争分析的域名分类需要按领域调整。以下是常见领域的分类模板：

### 游戏站
- 强：`fandom.com`, `wiki.gg`, `game8.co`, `progameguides.com`
- 中：`ign.com`, `gamespot.com`, `polygon.com`, `pcgamer.com`
- 弱：`youtube.com`, `reddit.com`, Steam 内页, 个人博客

### 工具类
- 强：`canva.com`, `adobe.com`, 行业头部 SaaS
- 中：`g2.com`, `capterra.com`, `zapier.com`（评测/聚合）
- 弱：独立工具站, `youtube.com`, 博客教程

### 电商/POD
- 强：品牌官网（`gildan.com`, `bellacanvas.com`）, POD 平台（`printful.com`, `printify.com`）
- 中：`etsy.com`, `amazon.com`
- 弱：独立博客, `youtube.com`, `pinterest.com`

用户提供新领域时，让用户补充该领域的强竞争域名列表，或从首次 SERP 结果中识别。

## 注意事项

1. **不要凭直觉判断**：所有结论必须基于 Trends 数据 + SERP 实际结果
2. **社媒火 ≠ Google 搜火**：TikTok/X/Discord 的热度不能作为判断依据
3. **陷阱词识别**：山形曲线（暴涨→暴跌）是典型陷阱，不做
4. **搜索意图检查**：通过 Autocomplete 结果判断搜索意图是否和预期一致
5. **查询频率控制**：SERP 抓取每次间隔 3-5 秒，每日上限约 50 次
6. **KD 数值无法免费获取**：SimilarWeb/Ahrefs/SEMrush 的 KD 都是付费功能，用 SERP 域名分类替代
