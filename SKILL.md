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

## Step 5（确认做之后）：域名推荐

当用户确认某个主词"做"，自动给出域名推荐。**购买由用户自行操作。**

### 域名推荐规则

| 规则 | 说明 |
|---|---|
| 首选后缀 | `.wiki`（内容站最佳语义） |
| 备选后缀 | `.com` `.org` `.net` `.online` `.site` |
| 避坑后缀 | `.cc` `.xyz`（被灰产玩坏，搜索引擎减分） |
| 域名格式 | 主词直接拼接，如 `palworld.wiki`、`schedule1guide.com` |

### 域名可用性自动检查

对每个推荐域名，自动检查是否可注册：

```bash
# .com 域名 — RDAP 协议
curl -s -o /dev/null -w "%{http_code}" "https://rdap.verisign.com/com/v1/domain/TARGET.com"
# 200 = 已注册, 404 = 可用

# .net 域名
curl -s -o /dev/null -w "%{http_code}" "https://rdap.verisign.com/net/v1/domain/TARGET.net"

# 其他后缀 — whois
whois TARGET.wiki 2>&1 | grep -i "no match\|not found"
# 有输出 = 可用
```

### 输出格式

```
推荐域名（按优先级）：
  1. keyword.wiki     — ✅ 可用 / ❌ 已注册
  2. keyword.com      — ✅ 可用 / ❌ 已注册
  3. keywordguide.com — ✅ 可用 / ❌ 已注册

购买平台：https://www.spaceship.com（支持支付宝）
避坑：不要买 .cc / .xyz 后缀
```

购买操作由用户自行完成。

## Step 6（确认做之后）：Cloudflare 绑定

域名购买后，通过 Cloudflare API 自动化完成大部分绑定操作。

### Cloudflare 能做什么

| 能力 | 免费账号 | 说明 |
|---|---|---|
| DNS 托管 | ✅ | 全球 CDN 加速 |
| SSL 证书 | ✅ | 自动签发 |
| **Cloudflare Pages** | ✅ | 网站部署（类似 Vercel），500 次部署/月 |
| DDoS 防护 | ✅ | 基础防护 |
| 缓存 | ✅ | 静态资源缓存 |

**Cloudflare Pages 同时提供网站部署服务**：支持 Next.js、Astro、Hugo 等框架，可以把内容站直接部署在 Cloudflare 上，不需要额外服务器。

### API 自动化流程

**前置条件**：用户需要提供 Cloudflare API Token（在 https://dash.cloudflare.com/profile/api-tokens 创建）。

可自动化的步骤（通过 Cloudflare API）：

```bash
CF_TOKEN="用户的API Token"
DOMAIN="target-domain.com"

# 1. 添加域名到 Cloudflare（创建 Zone）
curl -s -X POST "https://api.cloudflare.com/client/v4/zones" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  --data "{\"name\":\"$DOMAIN\",\"type\":\"full\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Zone ID: {d[\"result\"][\"id\"]}'); print(f'Nameservers: {d[\"result\"][\"name_servers\"]}')"

# 2. 获取分配的 Nameserver（从上一步结果中提取）
# 结果示例：["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"]

# 3. 删除默认 DNS 记录（如有）
ZONE_ID="从步骤1获取"
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
  -H "Authorization: Bearer $CF_TOKEN" \
  | python3 -c "import sys,json; [print(r['id']) for r in json.load(sys.stdin)['result']]"
# 对每个 record_id 执行 DELETE

# 4. 触发 Nameserver 检查
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/activation_check" \
  -H "Authorization: Bearer $CF_TOKEN"
```

### 不可自动化的步骤（需用户手动）

**修改 Nameserver**：Spaceship.com 没有公开 API，用户需要手动操作：

1. 打开 https://www.spaceship.com/zh/application/domain-list-application/
2. 找到域名 → **Nameservers & DNS** → **Change**
3. 填入 Cloudflare 分配的 2 个 nameserver
4. 保存，等待 10 分钟生效

### Cloudflare Pages 部署（可选，后续建站时用）

确认域名绑定成功后，可用 Cloudflare Pages 部署网站：

```bash
# 通过 Wrangler CLI 部署
npx wrangler pages deploy ./dist --project-name=my-site

# 或者连接 Git 仓库自动部署（在 Cloudflare 控制台设置）
```

免费额度：500 次部署/月，无限带宽，自定义域名。

## Step 7（建站前）：需求挖掘与页面规划

确定主词 + 域名之后，进入内容规划阶段。核心产出：`关键词.md`（原始汇总）+ `keywords.json`（结构化）+ 最小页面集。

### 核心原则

- **页面唯一依据是搜索需求**，不是"看起来完整"。不为完整性做没人搜的页面。
- 用户搜的是具体问题（codes、tier list、某角色怎么获得），用不同页面分别承接。
- 第一版只做最核心页面：**首页 + 10-20 个长尾内页**。

### 7.1 从三来源挖长尾词

#### 来源 1：Google Autocomplete（自动化）

```bash
# 主词补全
curl -s "https://suggestqueries.google.com/complete/search?q=GAME_NAME+&client=firefox&hl=en"

# 主词 + 常见后缀补全（扩展更多长尾）
for suffix in "codes" "guide" "tier list" "wiki" "map" "characters" "update" "reddit"; do
  curl -s "https://suggestqueries.google.com/complete/search?q=GAME_NAME+${suffix}+&client=firefox&hl=en"
  sleep 1
done
```

#### 来源 2：Google Trends 相关查询（自动化）

使用 `niche-google-trends-mcp` 的 `trends_related_queries` 工具：

```
trends_related_queries(keyword="GAME_NAME", timeframe="1m")
```

返回 `rising`（飙升词）和 `top`（高频词）两个列表。全部记录。

> 注意：当前 MCP 的 related_queries 可能返回空 query 字段（已知 bug）。
> 备选方案：通过 Patchright + CDP 打开 Trends 页面，拦截 `/widgetdata/relatedsearches` API 响应直接解析。

#### 来源 3：SimilarWeb 关键词（需用户补充）

SimilarWeb Keyword Generator 是付费功能，无法自动获取。

处理方式：
- 标注"待用户补充"
- 让用户手动去 SimilarWeb 复制第 1 页关键词列表
- 用户粘贴后再整合

### 7.2 汇总为「关键词.md」

将三来源全部长尾词汇总为一个文件，按来源分组：

```markdown
# 关键词.md —— 游戏名：<主游戏词>

## 来源1：Google Autocomplete
- game_name codes
- game_name tier list
- game_name guide
- ...

## 来源2：Google Trends 相关查询
- game_name codes（飙升）
- game_name new update（飙升）
- game_name tier list（+800%）
- ...

## 来源3：SimilarWeb（待用户补充 / 用户已提供）
- ...
```

### 7.3 生成 keywords.json

基于关键词.md，按以下硬规则生成结构化 JSON：

#### 硬规则清单

| # | 规则 |
|---|---|
| R1 | 最终关键词总数 **10-20 个** |
| R2 | **必须有 guide 分类** |
| R3 | 若有 Codes 分类，其下**只能有 1 个关键词** |
| R4 | 分类禁止空泛（禁用 gameplay、general） |
| R5 | 过滤核心主词本身、非本主题词 |
| R6 | 同义词合并，保留搜索量最大/大众习惯的 |
| R7 | 全英文（非英文需翻译） |
| R8 | 可改拼写错误，**禁止扩写** |
| R9 | 关键词统一命名为 **"游戏主题名 xxxx"** |
| R10 | MECE-相互独立：分类间无包含关系；同分类内无同义/单复数重复 |
| R11 | MECE-完全穷尽：一个分类下覆盖该分类所有有效需求 |
| R12 | 每分类内，流量大的关键词排前面 |
| R13 | 严禁遗漏任何有效关键词 |
| R14 | 输出**纯 JSON**，禁止附加说明文字 |

#### 输出格式

```json
{
  "categories": [
    {
      "category": "Guide",
      "keywords": ["game_name guide", "game_name beginner guide"]
    },
    {
      "category": "Codes",
      "keywords": ["game_name codes"]
    },
    {
      "category": "Tier List",
      "keywords": ["game_name tier list", "game_name best units"]
    }
  ]
}
```

#### 自检流程（生成后必跑）

1. 总数是否 10-20？（R1）
2. 是否有 guide 分类？（R2）
3. Codes 分类是否 ≤ 1 词？（R3）
4. 有无空泛分类？（R4）
5. 全英文？命名统一？（R7/R9）
6. MECE 是否违反？（R10/R11）
7. 分类内是否按流量降序？（R12）
8. 输出是否纯 JSON？（R14）

任一不通过 → 修正后重新输出。

### 7.4 最小页面集规划

基于 keywords.json 映射页面：

```
1. 首页 —— 承接主游戏词（游戏介绍/核心玩法/导航）
2. 内页01 —— game_name codes（category: Codes）
3. 内页02 —— game_name guide（category: Guide）
4. 内页03 —— game_name tier list（category: Tier List）
...
N. 导航页 —— 角色/道具批量展示（若细分过多，不逐个做独立页）

合计：首页 + 10-20 内页
```

规则：
- 一个有效关键词 = 一个内页
- 角色/道具类长尾若 > 10 个，归并为 1 个导航页
- 第一版只做核心页，不追求覆盖所有可能

### 7.5 交付物清单

- [ ] `关键词.md`（三来源原始汇总）
- [ ] `keywords.json`（通过全部自检）
- [ ] 最小页面集规划清单（首页 + N 内页，与 json 一一映射）
- [ ] 同义词合并后"还能做多少一词一页内容"的数量说明

---

## 注意事项

1. **不要凭直觉判断**：所有结论必须基于 Trends 数据 + SERP 实际结果
2. **社媒火 ≠ Google 搜火**：TikTok/X/Discord 的热度不能作为判断依据
3. **陷阱词识别**：山形曲线（暴涨→暴跌）是典型陷阱，不做
4. **搜索意图检查**：通过 Autocomplete 结果判断搜索意图是否和预期一致
5. **查询频率控制**：SERP 抓取每次间隔 3-5 秒，每日上限约 50 次
6. **KD 数值无法免费获取**：SimilarWeb/Ahrefs/SEMrush 的 KD 都是付费功能，用 SERP 域名分类替代
7. **Cloudflare API Token**：首次使用时需要用户提供，后续复用
8. **页面唯一依据是搜索需求**：不为"看起来完整"做没人搜的页面
9. **SimilarWeb 数据滞后约 3 天**：不能作为唯一实时依据，需与 Autocomplete/Trends 交叉验证
