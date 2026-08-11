---
name: keyword-validator
description: Use when validating whether a keyword/niche is worth building a content site or tool around. Triggers on "验证关键词" "选词判断" "keyword validation" "niche validation" "SERP analysis" "能不能做" or when user provides candidate keywords and asks about search volume, competition, or feasibility. Requires niche-google-trends-mcp, Keywords Everywhere Chrome extension, and a Chrome instance with CDP on port 9223 (same as Google Trends MCP).
---

# Keyword Validator — 关键词选词判断 + 内容规划工作流

从候选词发现到页面矩阵规划的完整闭环。分两大阶段：**选词判断**（能不能做）→ **内容规划**（做什么页面）。

## 前置条件

1. **niche-google-trends-mcp** 已运行（提供 Trends 对比 + Related Queries）
2. **Chrome + CDP 端口 9223**（Google Trends MCP 启动时已自动开启）
3. **Patchright**（在 google-trends-mcp 的 venv 中：`/path/to/google-trends-mcp/.venv/bin/python`）
4. **Keywords Everywhere Chrome 扩展**已安装（免费，提供竞品流量数据）

验证环境：
```bash
curl -s "http://127.0.0.1:9223/json/version" | python3 -c "import sys,json; print(json.load(sys.stdin)['Browser'])"
```

---

# 第一阶段：选词判断

## Step 1: 候选词发现

从 Steam 新品榜捞 3-5 个候选游戏词：

```bash
curl -s --compressed -H "User-Agent: Mozilla/5.0" \
  "https://store.steampowered.com/api/featuredcategories" \
  | python3 -c "
import sys,json; data=json.load(sys.stdin)
for item in data.get('new_releases',{}).get('items',[])[:15]:
    print(f\"  {item.get('name')} (appid:{item.get('id')})\")
print()
for item in data.get('top_sellers',{}).get('items',[])[:15]:
    print(f\"  {item.get('name')} (appid:{item.get('id')})\")
"
```

挑选标准：新上线 + 玩家数上升 + 非硬件/DLC。

## Step 2: Google Trends 热度验证

用 `niche-google-trends-mcp` 的 `trends_compare` 工具，将候选词与 **GPTs** 对比：

- timeframe: `1m`（看当前热度）或 `3m`（看趋势走向）
- 基准：GPTs 日均约 3000-5000 搜索量

| 曲线形态 | 含义 | 判断 |
|---|---|---|
| 持续上行 / 接近或超过 GPTs | 有搜索量且在涨 | ✅ 继续 |
| 平稳 | 存量词 | 看竞争再定 |
| 下降 | 热度消退 | 谨慎 |
| 山形（暴涨→暴跌） | 陷阱词 | ❌ 不做 |
| 全部为 0 | 无人搜索 | ❌ 不做 |

## Step 3: SERP 竞争分析 + Keywords Everywhere 数据

这是最关键的一步。通过 Patchright 打开 Google 搜索页，**同时提取**：
1. SERP 前 10 结果的域名和标题
2. Keywords Everywhere 扩展注入的竞品流量数据

### 3.1 SERP 抓取 + KE 数据提取

```python
# 等待 12-15 秒让 KE 扩展注入数据
await page.goto(f"https://www.google.com/search?q={query}&num=10&hl=en",
               wait_until="domcontentloaded", timeout=30000)
await asyncio.sleep(12)

# 提取 SERP 结果
results = await page.evaluate("""() => {
    const items = [], seen = new Set();
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
}""")

# 提取 Keywords Everywhere 注入的数据
ke_data = await page.evaluate("""() => {
    const data = { difficulty: {}, serp_metrics: [], related: [], longtail: [] };
    
    // SEO Difficulty 评分
    const diffRoot = document.getElementById('xt-difficulty-root');
    if (diffRoot) {
        const text = diffRoot.innerText;
        const seoMatch = text.match(/SEO Difficulty\\s*(\\d+)\\/100/);
        const offMatch = text.match(/Off-Page Difficulty\\s*(\\d+)\\/100/);
        const onMatch = text.match(/On-Page Difficulty\\s*(\\d+)\\/100/);
        data.difficulty = {
            seo: seoMatch ? parseInt(seoMatch[1]) : null,
            offPage: offMatch ? parseInt(offMatch[1]) : null,
            onPage: onMatch ? parseInt(onMatch[1]) : null
        };
    }
    
    // 每个 SERP 结果的流量数据
    const trafficEls = document.querySelectorAll('.xt-ke-value.xt-ke-traf-vals');
    const kwEls = document.querySelectorAll('.xt-ke-value.xt-ke-kw-vals');
    for (let i = 0; i < trafficEls.length; i++) {
        data.serp_metrics.push({
            traffic: trafficEls[i]?.innerText || '',
            keywords: kwEls[i]?.innerText || ''
        });
    }
    
    // Related Keywords
    document.querySelectorAll('.xt-widget-table-td-keyword').forEach(el => {
        const text = el.innerText?.trim();
        if (text) data.related.push(text);
    });
    
    return data;
}""")
```

### 3.2 KE 提供的免费数据说明

| 数据 | 含义 | 来源 |
|---|---|---|
| Search traffic: X/mo | 该竞品页面每月从搜索获得的实际访问量 | KE 扩展免费 |
| website: X/mo | 该竞品整站每月总搜索流量 | KE 扩展免费 |
| Keywords: N | 该竞品页面排了多少关键词 | KE 扩展免费 |
| MOZ DA | 域名权重（0-100，越高越难竞争） | KE 扩展免费 |
| Ref Dom / Ref Links | 反向链接域名数/链接数 | KE 扩展免费 |
| SEO Difficulty | 综合难度评分（KE 自算，仅参考） | KE 扩展免费 |
| On-Page Difficulty | 内容质量难度（低=内容弱，有机会超越） | KE 扩展免费 |
| Related Keywords | 相关词列表（无搜索量） | KE 扩展免费 |
| Long-Tail Keywords | 长尾词列表（无搜索量） | KE 扩展免费 |
| 精确搜索量 / CPC | 需要购买 credits | KE 付费 |

### 3.3 竞争判断标准（基于实际数据）

**用竞品页面流量判断**——比域名分类更可靠：

| 首页竞品页面月流量 | 说明 | 判断 |
|---|---|---|
| 大部分 <100/mo | 竞品也没什么流量，说明词本身小或内容差 | 看 Trends 热度决定 |
| 100-1000/mo | 有一定流量但不大 | ✅ 可以做，做得好能超 |
| 1000-10000/mo | 流量可观 | ⚠️ 看竞品 DA，DA<50 有机会 |
| >10000/mo | 大流量词 | 看 On-Page Difficulty，低则有机会 |

**用 MOZ DA 判断能不能超越**：
- DA < 30：小站，可以直接竞争
- DA 30-60：中等站，需要优质内容 + 时间
- DA > 60：大站（IGN/Reddit/Fandom），正面硬刚困难，做差异化

### 3.4 域名分类（辅助判断）

仍然保留类型分类作为快速参考：

**游戏领域**：
- 强竞争：`fandom.com`, `wiki.gg`, `game8.co`, `progameguides.com`
- 中竞争：`ign.com`, `gamespot.com`, `polygon.com`, `pcgamer.com`
- 弱竞争：`youtube.com`, `reddit.com`, Steam 内页, 独立小站

**重要**：域名分类只是辅助。实际判断以 KE 提供的竞品流量 + DA 数据为准。

## Step 4: Google Autocomplete 细分关键词

```bash
curl -s "https://suggestqueries.google.com/complete/search?q=KEYWORD+&client=firefox&hl=en" \
  | python3 -c "import sys,json; [print(s) for s in json.load(sys.stdin)[1]]"
```

扩展查询（加后缀）：
```bash
for suffix in "codes" "guide" "tier list" "wiki" "map" "characters" "build" "boss" "walkthrough"; do
  curl -s "https://suggestqueries.google.com/complete/search?q=KEYWORD+${suffix}+&client=firefox&hl=en"
  sleep 1
done
```

注意检查搜索意图是否一致。

## 输出：判断卡

```
【候选词】关键词
【Trends 热度】vs GPTs 约 x%（日估 ~N 次）；曲线形态
【SERP 竞争】
  - 首页竞品流量分布：[X/mo, Y/mo, Z/mo ...]
  - 竞品 DA 分布：[DA1, DA2, DA3 ...]
  - On-Page Difficulty: N/100
  - 强竞争站占比：x/10
【细分关键词】N 个（列举前 5-10）
【做/不做】结论
【理由】基于 Trends + 竞品流量 + DA 的具体依据
```

---

# 第二阶段：内容规划（确认"做"之后）

## Step 5: 需求挖掘

### 5.1 三来源汇总

对已确认的主词，从三来源挖全部长尾词：

1. **Google Suggest**：主词 + 16 个常见后缀各跑一轮
2. **Google Trends Related Queries**：通过 Patchright 拦截 Trends API（`/widgetdata/relatedsearches`）获取 TOP + RISING 完整列表
3. **Keywords Everywhere 扩展**：从 Step 3 的 SERP 页面提取 Related Keywords + Long-Tail Keywords 列表

### 5.2 用 Trends 实测量化每个细分词

对关键长尾词批量跑 `trends_compare`（每次最多 5 个词 + GPTs），得到相对热度排序。

### 5.3 用 KE 扩展获取竞品流量

对重要细分词，逐个打开 Google SERP（间隔 3-5 秒），等待 KE 注入后提取：
- 首页各竞品的月搜索流量
- Related/Long-tail 补充词

## Step 6: 生成关键词.md + keywords.json

### 关键词.md 格式

```markdown
# 关键词.md —— 游戏名：<主词>

## 来源1：Google Suggest
- ...

## 来源2：Google Trends Related（TOP + RISING）
- ...（附飙升百分比）

## 来源3：Keywords Everywhere（Related + Long-tail）
- ...

## 来源4：SimilarWeb（待用户补充/不可用）
- ...
```

### keywords.json 硬规则

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
| R10 | MECE-相互独立 + 完全穷尽 |
| R11 | 每分类内流量大的关键词排前面 |
| R12 | 输出**纯 JSON**，禁止附加说明 |

自检：总数 10-20 → 有 guide → Codes ≤1 → 无空泛分类 → 全英文 → 命名统一 → MECE → 降序 → 纯 JSON。

## Step 7: 页面矩阵规划

### 优先级定级（基于实际数据，非拍脑袋）

| 优先级 | 数据标准 |
|---|---|
| P0 | Trends 实测 vs GPTs > 10% **且** 竞品页面流量证实有量 |
| P1 | Trends 实测 vs GPTs 2-10% **或** KE Related 中出现 |
| P2 | 仅 Google Suggest 出现，无 Trends/流量数据 |

### 页面矩阵表格式

| # | 页面类型 | 关键词 | 热度数据 | 竞品最高月流量 | 优先级 | 用户问题 |
|---|---|---|---|---|---|---|
| 1 | 首页 | 主词 | Trends 实测值 | — | P0 | 游戏介绍/导航 |
| 2 | 攻略页 | xxx guide | Trends X% | Y/mo | P0 | ... |
| ... | ... | ... | ... | ... | ... | ... |

### 站点结构

规划 URL 目录结构 + 导航逻辑：
- 顶部导航：按 keywords.json 的 category 分组
- 首页卡片：P0 页面直达入口
- 导航页：细分过多的类目（如角色/装备）用列表页聚合

## Step 8（可选）: 域名推荐

### 域名规则
- 首选 `.wiki`，备选 `.com .org .net .online .site`
- 避坑 `.cc .xyz`

### 自动检查可用性
```bash
# .com
curl -s -o /dev/null -w "%{http_code}" "https://rdap.verisign.com/com/v1/domain/TARGET.com"
# 200=已注册, 404=可用

# 其他
whois TARGET.wiki 2>&1 | grep -i "no match\|not found"
```

## Step 9（可选）: Cloudflare 绑定

用户购买域名后，通过 Cloudflare API 自动化：

```bash
CF_TOKEN="用户的API Token"
# 创建 Zone → 获取 Nameserver → 删除默认 DNS → 触发检查
curl -s -X POST "https://api.cloudflare.com/client/v4/zones" \
  -H "Authorization: Bearer $CF_TOKEN" -H "Content-Type: application/json" \
  --data "{\"name\":\"$DOMAIN\",\"type\":\"full\"}"
```

不可自动化：去 Spaceship 手动修改 Nameserver。

Cloudflare Pages 可直接部署网站（免费 500 次/月，无限带宽）。

---

# 第三阶段：建站执行

确认主词 + 页面矩阵后，进入实际建站。按 Task 0 → Task 1 → Task 2 → Task 3 顺序执行。

## Step 10: 项目准备（Task 0）

1. 建立项目目录结构：
```
{game}-wiki/
├─ content/
│  ├─ keywords.json          # 10-20 个内页关键词（Phase 2 产物）
│  ├─ 关键词素材.md           # 全部关键词素材归档
│  └─ home.json              # 首页内容 JSON
├─ public/                   # favicon 等静态资源
├─ styles/
│  └─ theme.css              # 亮/暗两套 HSL 主题变量
├─ locales/                  # 多语言（最多 4 门，必含英语）
└─ pages/                    # 首页 + 内页
```

2. 确认 `keywords.json` 就绪（Phase 2 产出）
3. 创建空的 `关键词素材.md` 骨架

## Step 11: 首页（Task 1）

### 需要收集的 4 样基础信息

| 信息 | 说明 | 获取方式 |
|---|---|---|
| SEO 元数据 | title(≤60) + description(140-160) + keywords(≤100) | 联网搜索生成 |
| 官方链接 | 官网/Discord/YouTube/Reddit/Steam | 搜索验证，只放可访问链接 |
| 主题色 | 亮/暗两套 HSL 色值，贴近游戏调性 | 参考官网/宣传图 |
| 多语言优先级 | 按 Trends 地区热度排序，最多 4 门含英语 | Phase 1 的地区数据 |

### 首页 JSON Schema

```json
{
  "metadata": { "title": "", "description": "", "keywords": "" },
  "officialLinks": { "site": "", "discord": "", "youtube": "", "reddit": "", "steam": "" },
  "theme": { "light": { "nav-theme": "", "nav-theme-light": "" }, "dark": { "nav-theme": "", "nav-theme-light": "" } },
  "languages": [],
  "home": {
    "hero": { "eyebrow": "", "title": "", "description": "", "stats": [], "cta1": {}, "cta2": {}, "cta3": {} },
    "start": { "cards": [{}, {}, {}, {}] },
    "aboutGame": { "paragraphs": [], "stats": [] },
    "finalCta": { "title": "", "primary": {}, "secondary": {} },
    "footer": { "about": "", "social": [], "legal": [] },
    "sidebarCodes": []
  }
}
```

### 首页字段规则

| 区块 | 规则 |
|---|---|
| hero | `stats` 为纯字符串数组；3 个 CTA 按钮 |
| start | 4 张卡片：第 1 张固定新手入门，后 3 张挑玩家最常搜的内容，类型互不重复 |
| aboutGame | 2-3 句玩法介绍 + label/value 数据对 |
| sidebarCodes | 2 条兑换码（无则填「暂无」） |

### 验收
- [ ] title ≤ 60，description 140-160，keywords ≤ 100
- [ ] 官方链接全部可访问
- [ ] 主题色亮/暗两套 HSL
- [ ] 多语言 ≤ 4 门含英语
- [ ] start.cards 恰 4 个且类型不重复

## Step 12: 网站图标（Task 2）

1. 生成 512x512 png 源图（AI 生成，贴合游戏风格）
2. 用 https://favicon.io/favicon-converter 转换
3. 得到 8 个文件放入 `/public`：

```
site.webmanifest / favicon.ico / android-chrome-512x512.png
android-chrome-192x192.png / apple-touch-icon.png
favicon-32x32.png / favicon-16x16.png / source-1024.png
```

## Step 13: 内页素材收集（Task 3）

### 核心原则

1. **事实必须有依据**：不编造不存在的人物/兑换码/关卡
2. **AI 用于整理，不用于凭空编造**：AI 做调研、过滤、结构化
3. **交叉验证**：同一信息至少 2 个来源确认
4. **参考不复制**：竞对只参考结构，不复制内容（版权合规）

### 每个关键词的素材收集流程

对 keywords.json 中的每个关键词，执行：

#### 13.1 Google 搜索
1. 搜索该关键词，选排名前 2 的网页
2. 复制核心内容到素材文档

#### 13.2 YouTube 搜索
1. 搜索该关键词，选 2 个较新+高播放的视频
2. 用字幕提取插件导出字幕
3. 提取关键内容到素材文档

#### 13.3 官网/Steam
1. 查找与该关键词相关的官方说明
2. 有信息则复制；若无实质信息注明"已跳过"

### 素材文档模板

```markdown
# {关键词}

## Google 素材
素材来源地址：
{URL 1}
{URL 2}
素材内容：
{网页内容}

## YouTube
素材来源地址：
{视频 URL 1}
{视频 URL 2}
素材内容：
{字幕提取关键内容}

## 游戏官网
素材来源地址：
{Steam/官网 URL}
素材内容：
{官方说明 或 "已跳过"}
```

### 信息渠道优先级

| 渠道 | 适合获取 | 注意 |
|---|---|---|
| YouTube | 试玩攻略、角色评测、操作教学 | UP 主比文章更早发布新游戏攻略 |
| Discord | 角色机制、更新说明、官方一手信息 | 海外游戏社区核心阵地 |
| Google 搜索 | 已有攻略文章、Wiki 页面 | 参考结构，不复制内容 |
| 竞对网站 | 页面结构参考、信息缺口发现 | 发现它们没做好的地方 |
| 官网/Steam | 基本介绍、角色列表、更新日志 | 最权威的事实来源 |

### 验收
- [ ] keywords.json 中每个关键词都有素材文档
- [ ] 每个素材文档含 Google/YouTube/官网 三板块
- [ ] 关键事实完成 ≥2 来源交叉验证
- [ ] 无编造内容，所有事实可溯源

---

## 注意事项

1. **不要凭直觉判断**：所有结论必须基于 Trends + 竞品流量 + DA 数据
2. **社媒火 ≠ Google 搜火**：TikTok/Discord 热度不能作为判断依据
3. **陷阱词识别**：山形曲线（暴涨→暴跌）= 不做
4. **搜索意图检查**：通过 Autocomplete 确认搜索意图一致
5. **查询频率控制**：SERP 抓取间隔 3-5 秒，每日上限约 50 次
6. **KE 评分仅参考**：SEO Difficulty 是 KE 自算模型，不透明；以竞品实际流量 + DA 为准
7. **页面唯一依据是搜索需求**：不为"看起来完整"做没人搜的页面
8. **优先级必须有数据支撑**：P0/P1/P2 必须标注依据（Trends 值 / 竞品流量 / 仅 Suggest）
9. **事实必须有依据**：游戏攻略内容不得编造，必须来自真实信息源
10. **交叉验证**：同一信息至少 2 个来源确认
11. **参考不复制**：竞对内容只参考结构和发现缺口，不直接复制（版权合规）

## 数据来源可信度层级

| 层级 | 数据来源 | 能证明什么 | 局限 |
|---|---|---|---|
| 1（最可信） | KE 竞品页面月流量 | 该词有多少真实流量可抢 | KE 估算可能有误差 |
| 2 | Trends 实测对比 | 词之间的相对热度排序 | 绝对值基于 GPTs 推算（±50%） |
| 3 | Trends Related（TOP/飙升） | 词在主词生态中的权重 | 只有相对分，无绝对量 |
| 4 | Google Suggest | 有真实搜索行为 | 无量化，不能区分 10/天还是 10000/天 |
| 5（最弱） | KE SEO Difficulty 评分 | 竞争难度参考 | 算法不透明，仅辅助 |

## 全流程总览

```
Phase 1: 选词判断
  Step 1  候选词发现（Steam API）
  Step 2  Trends 热度验证（vs GPTs）
  Step 3  SERP 竞争分析 + KE 竞品流量
  Step 4  Autocomplete 细分词

Phase 2: 内容规划
  Step 5  三来源挖词（Suggest + Trends Related + KE）
  Step 6  关键词.md + keywords.json
  Step 7  页面矩阵（数据定优先级）

Phase 3: 建站准备
  Step 8  域名推荐 + 可用性检查
  Step 9  Cloudflare 绑定（API 半自动）

Phase 4: 建站执行
  Step 10  项目目录准备
  Step 11  首页（SEO + 官方链接 + 主题色 + 多语言 + JSON）
  Step 12  Favicon 生成
  Step 13  内页素材收集（Google + YouTube + 官网，交叉验证）
```
