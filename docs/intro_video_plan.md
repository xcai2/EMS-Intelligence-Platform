# EMS Intelligence Platform — 3-Minute Intro Video Production Plan

---

## 1. 视频定位与风格

| 属性 | 内容 |
|------|------|
| 时长 | 2:50 – 3:10 |
| 语言 | 英语（正式、清晰、有节奏感） |
| 风格 | 产品演示 + 解说词驱动，类似 YC Demo Day pitch video |
| 受众 | 行业分析师、机构投资者、供应链策略师、学术评审 |
| 核心信息 | 把碎片化的 EMS 行业数据变成即时可用的决策智能 |

---

## 2. 视频脚本 / Transcript（约 3 分钟）

> 共约 430 词，语速 140 wpm ≈ 3 分钟。
> 每段标注时间节点、对应屏幕操作、以及 Playwright 脚本的等待时长。

---

### [0:00 – 0:25] HOOK

**🎬 屏幕：** 首页 Dashboard 慢速淡入

> "The electronics manufacturing services industry powers the devices, servers, and infrastructure that run the modern world.
>
> Companies like Flex, Jabil, Celestica, Benchmark, Sanmina, and Plexus collectively manufacture hundreds of billions of dollars of hardware every year — from AI servers to medical devices to automotive systems.
>
> Yet tracking their financial health, strategic bets, and competitive positioning requires hours of manual work across filings, earnings calls, and scattered news sources.
>
> We built the **EMS Intelligence Platform** to change that."

---

### [0:25 – 1:00] WHAT WE BUILT

**🎬 屏幕：** 鼠标缓慢划过左侧 Sidebar 全部 8 个导航项

> "Our platform is a full-stack financial intelligence system built specifically for the EMS sector.
>
> At its core is a **RAG-powered document engine** — thousands of pages of SEC filings are indexed in a vector database, making any passage instantly searchable.
>
> On top of that, we layer **live financial data**, **multi-source news intelligence**, and **AI-generated analysis** — all synthesized into eight integrated modules.
>
> And thanks to a persistent cache layer built across every page, the entire platform loads instantly — even after a server restart."

---

### [1:00 – 2:15] FEATURE WALKTHROUGH

> *(以下按 Sidebar 实际顺序演示，逐模块 8–12 秒)*

---

**[1:00 – 1:11] News**

**🎬 屏幕：** 点击 News → 滚动查看 Feed → 点击 "Data Center" 预设筛选

> "The **News** module aggregates stories from company IR feeds, SEC RSS, and the open web — all in one place. Click a topic preset like Data Center or AI Infrastructure, and the feed filters instantly. Every company gets an AI-generated weekly digest."

---

**[1:11 – 1:21] Analyst View**

**🎬 屏幕：** 点击 Analyst View → 展示 Executive Summary 卡片 + 评级 Feed

> "**Analyst View** synthesizes sell-side ratings, analyst coverage, and strategic consensus themes into an executive summary — refreshed with a single click. No more reading through twenty separate research notes."

---

**[1:21 – 1:35] AI Chat**

**🎬 屏幕：** 点击 AI Chat → 输入示例问题（如 "What is Flex's CapEx guidance for FY2026?"）→ 展示 RAG 回答 + 来源引用

> "The **AI Chat** interface lets you query the entire knowledge base in natural language. Choose between RAG mode — grounded in SEC filings — web search mode, or a hybrid of both. Filter by company, time period, and AI provider. It's like having a research analyst available around the clock."

---

**[1:35 – 1:55] Companies**

**🎬 屏幕：** 点击 Companies → 展示 6 家公司卡片 → 点击 Flex "View Detail" → 切换到 Financials tab → 切换到 CapEx tab，指向 Anomaly Insight

> "The **Companies** dashboard gives you an at-a-glance view of all six players — AI investment focus, sentiment scores, and CapEx anomaly alerts.
>
> Click into any company for a full deep-dive: five-year financials, CapEx trend analysis with automatic anomaly detection, investment focus breakdown from SEC filings, and real-time hiring signals."

---

**[1:55 – 2:05] Hyperscaler**

**🎬 屏幕：** 点击 Hyperscaler → 展示 Big 5 CapEx 对比柱状图 → 指向 YoY Growth 数字

> "The **Hyperscaler** tracker monitors capital expenditure from Amazon, Microsoft, Google, Meta, and Apple — updated via Gemini with Google Search grounding. This is the demand side of the EMS equation: where the hyperscalers spend tells you exactly where EMS growth is headed."

---

**[2:05 – 2:13] Facilities Map**

**🎬 屏幕：** 点击 Facilities Map → 旋转 3D 地球仪 → 点击一个设施点查看详情

> "The **Facilities Map** renders every manufacturing location across six continents on an interactive globe — with regional distribution analysis and competitor facility overlap detection."

---

**[2:13 – 2:20] Calendar**

**🎬 屏幕：** 点击 Calendar → 展示月视图 + 财报事件标记

> "The **Earnings Calendar** tracks upcoming and recent earnings releases and conference calls for all six companies — with direct links to IR pages and webcasts, so you never miss a reporting event."

---

**[2:20 – 2:28] Data Center**

**🎬 屏幕：** 点击 Data Center → 展示 Scheduler 状态 + 各公司文件下载进度

> "Behind the scenes, the **Data Center** manages automated SEC filing ingestion — scheduling downloads, tracking status by company and filing type, and keeping the knowledge base continuously up to date."

---

### [2:28 – 2:50] USE CASES

**🎬 屏幕：** 回到 Dashboard 全景，轻微放大动画

> "Who is this built for?
>
> **Equity analysts** benchmarking EMS valuations across six companies simultaneously. **Supply chain strategists** tracking capacity shifts and geographic expansion. **Corporate development teams** reading competitor AI investment signals from primary source documents. And **portfolio managers** connecting hyperscaler CapEx commitments to the manufacturers who build the hardware."

---

### [2:50 – 3:05] VALUE + CLOSE

**🎬 屏幕：** 慢速淡出，留白或项目名称字幕

> "What used to take a research team days of manual work now takes seconds.
>
> The EMS Intelligence Platform turns fragmented, hard-to-access data into clear, actionable intelligence — so analysts and decision-makers can focus on the insight, not the data hunt.
>
> This is research infrastructure purpose-built for one of the most strategically important corners of the global technology supply chain."

---

## 3. 制作方案

### 3.1 整体工作流

```
① 文稿定稿
    ↓
② ElevenLabs API → voiceover.mp3（AI 配音）
    ↓
③ Whisper API → subtitles.srt（自动字幕）
    ↓
④ Playwright 脚本 → screen_recording.webm（自动化录屏）
    ↓
⑤ FFmpeg → final_output.mp4（合成配音 + 字幕）
```

步骤 ②③⑤ 完全自动化，脚本一键完成。
步骤 ④ 也是一键运行，但需要你先启动本地开发服务器（`npm run dev` + `uvicorn`）。

---

### 3.2 AI 配音（ElevenLabs）

```bash
curl -X POST "https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "（粘贴完整文稿纯文本）",
    "model_id": "eleven_turbo_v2_5",
    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.2}
  }' \
  --output voiceover.mp3
```

推荐声音：`George`（Voice ID: `JBFqnCBsd6RMkjVDRZzb`），沉稳专业。
备选：`Rachel`（女声清晰自然），`Brian`（美式中性）。

---

### 3.3 字幕自动生成（Whisper）

```python
from openai import OpenAI
client = OpenAI()

with open("voiceover.mp3", "rb") as f:
    srt = client.audio.transcriptions.create(
        model="whisper-1", file=f, response_format="srt"
    )

with open("subtitles.srt", "w") as f:
    f.write(srt)
```

或本地无需付费运行：
```bash
pip install openai-whisper
whisper voiceover.mp3 --model medium --output_format srt --language en
```

---

### 3.4 自动化录屏（Playwright）

这是本方案最核心的部分。用 Playwright 脚本模拟鼠标操作，**完全不需要人工操作浏览器**。

#### 安装

```bash
npm install playwright
npx playwright install chromium
```

#### 录制脚本 `record_demo.js`

```javascript
const { chromium } = require('playwright');

const BASE_URL = 'http://localhost:3000';

// 时间节点（毫秒），与配音文稿对齐
const TIMING = {
  hook:        [0,     25000],  // 0:00 – 0:25
  whatWeBuilt: [25000, 60000],  // 0:25 – 1:00
  news:        [60000, 71000],  // 1:00 – 1:11
  analyst:     [71000, 81000],  // 1:11 – 1:21
  chat:        [81000, 95000],  // 1:21 – 1:35
  companies:   [95000, 115000], // 1:35 – 1:55
  hyperscaler: [115000,125000], // 1:55 – 2:05
  map:         [125000,133000], // 2:05 – 2:13
  calendar:    [133000,140000], // 2:13 – 2:20
  dataCenter:  [140000,148000], // 2:20 – 2:28
  useCases:    [148000,170000], // 2:28 – 2:50
  close:       [170000,185000], // 2:50 – 3:05
};

// 在页面注入可见鼠标光标（Playwright 默认不显示鼠标）
async function injectCursor(page) {
  await page.addStyleTag({
    content: `
      #pw-cursor {
        position: fixed; width: 24px; height: 24px; border-radius: 50%;
        background: rgba(59,130,246,0.6); border: 2px solid #2563EB;
        pointer-events: none; z-index: 999999;
        transform: translate(-50%, -50%);
        transition: left 0.15s ease, top 0.15s ease;
        box-shadow: 0 0 0 0 rgba(59,130,246,0.4);
      }
      #pw-cursor.click {
        animation: clickPulse 0.3s ease-out;
      }
      @keyframes clickPulse {
        0%   { box-shadow: 0 0 0 0 rgba(59,130,246,0.7); }
        100% { box-shadow: 0 0 0 16px rgba(59,130,246,0); }
      }
    `
  });
  await page.evaluate(() => {
    const cursor = document.createElement('div');
    cursor.id = 'pw-cursor';
    document.body.appendChild(cursor);
    document.addEventListener('mousemove', (e) => {
      cursor.style.left = e.clientX + 'px';
      cursor.style.top  = e.clientY + 'px';
    });
  });
}

// 带光标动画的点击
async function clickWithAnimation(page, selector) {
  const el = await page.locator(selector).first();
  const box = await el.boundingBox();
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y, { steps: 20 }); // 缓慢移动
  await page.evaluate(() => {
    document.getElementById('pw-cursor')?.classList.add('click');
    setTimeout(() => document.getElementById('pw-cursor')?.classList.remove('click'), 350);
  });
  await page.waitForTimeout(300);
  await el.click();
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: './', size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();
  await injectCursor(page);

  // ── [0:00] HOOK — 打开首页 ──────────────────────────────────────────────
  await page.goto(`${BASE_URL}/`);
  await sleep(3000);

  // ── [0:25] Sidebar 演示 — 慢速划过所有导航项 ───────────────────────────
  const navItems = ['news','analyst-view','chat','companies','ai-investments','map','calendar','data'];
  for (const item of navItems) {
    await page.mouse.move(80, 0, { steps: 5 });
    const link = page.locator(`a[href="/${item}"]`).first();
    const box  = await link.boundingBox();
    if (box) await page.mouse.move(box.x + box.width/2, box.y + box.height/2, { steps: 20 });
    await sleep(600);
  }
  await sleep(2000);

  // ── [1:00] NEWS ──────────────────────────────────────────────────────────
  await clickWithAnimation(page, 'a[href="/news"]');
  await sleep(2500);
  // 点击 "Data Center" 预设
  await clickWithAnimation(page, 'text=Data Center');
  await sleep(3000);

  // ── [1:11] ANALYST VIEW ──────────────────────────────────────────────────
  await clickWithAnimation(page, 'a[href="/analyst-view"]');
  await sleep(4000);
  // 慢速滚动查看卡片
  await page.mouse.wheel(0, 400);
  await sleep(3000);

  // ── [1:21] AI CHAT ───────────────────────────────────────────────────────
  await clickWithAnimation(page, 'a[href="/chat"]');
  await sleep(2000);
  // 点击输入框并输入示例问题
  await clickWithAnimation(page, 'input[placeholder], textarea[placeholder]');
  await page.keyboard.type("What is Flex's CapEx guidance for FY2026?", { delay: 60 });
  await sleep(2500);
  await page.keyboard.press('Enter');
  await sleep(4000); // 等待回答加载

  // ── [1:35] COMPANIES ─────────────────────────────────────────────────────
  await clickWithAnimation(page, 'a[href="/companies"]');
  await sleep(2500);
  // 鼠标悬停在 Flex 卡片上，然后点击 View Detail
  await clickWithAnimation(page, 'text=View Detail');
  await sleep(2000);
  // 切换到 Financials tab
  await clickWithAnimation(page, 'text=Financials');
  await sleep(2500);
  // 切换到 CapEx tab
  await clickWithAnimation(page, 'text=CapEx');
  await sleep(3000);
  // 慢速向下滚动到 Anomaly Insight
  await page.mouse.wheel(0, 600);
  await sleep(2500);

  // ── [1:55] HYPERSCALER ───────────────────────────────────────────────────
  await clickWithAnimation(page, 'a[href="/ai-investments"]');
  await sleep(4000);
  // 慢速滚动到 YoY 数据
  await page.mouse.wheel(0, 300);
  await sleep(3000);

  // ── [2:05] FACILITIES MAP ────────────────────────────────────────────────
  await clickWithAnimation(page, 'a[href="/map"]');
  await sleep(3000);
  // 在地球仪上拖动旋转（模拟）
  const globe = page.locator('canvas, .globe-container').first();
  const gBox  = await globe.boundingBox().catch(() => null);
  if (gBox) {
    await page.mouse.move(gBox.x + gBox.width * 0.5, gBox.y + gBox.height * 0.5);
    await page.mouse.down();
    await page.mouse.move(gBox.x + gBox.width * 0.7, gBox.y + gBox.height * 0.5, { steps: 30 });
    await page.mouse.up();
  }
  await sleep(2000);

  // ── [2:13] CALENDAR ──────────────────────────────────────────────────────
  await clickWithAnimation(page, 'a[href="/calendar"]');
  await sleep(3000);
  // 慢速滚动查看月视图
  await page.mouse.wheel(0, 200);
  await sleep(2500);

  // ── [2:20] DATA CENTER ───────────────────────────────────────────────────
  await clickWithAnimation(page, 'a[href="/data"]');
  await sleep(3000);
  await page.mouse.wheel(0, 300);
  await sleep(2500);

  // ── [2:28] USE CASES + CLOSE — 回到首页淡出 ──────────────────────────────
  await page.goto(`${BASE_URL}/`);
  await sleep(12000); // 停留到结尾

  await context.close();
  await browser.close();
  console.log('✅ Recording saved to ./video-*.webm');
})();
```

#### 运行方式

```bash
# 1. 确保开发服务器在运行
#    前端: npm run dev  (http://localhost:3000)
#    后端: uvicorn backend.main:app --port 8001

# 2. 运行录制脚本（约 3 分钟后自动退出）
node record_demo.js

# 3. 输出文件在当前目录 video-*.webm
```

---

### 3.5 合成最终视频（FFmpeg）

```bash
# 将 webm 转 mp4
ffmpeg -i video-*.webm -c:v libx264 -crf 18 screen_recording.mp4

# 合并配音（替换录制时的静音/系统声）
ffmpeg -i screen_recording.mp4 -i voiceover.mp3 \
  -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 \
  merged.mp4

# 烧录字幕
ffmpeg -i merged.mp4 \
  -vf "subtitles=subtitles.srt:force_style='FontName=Arial,FontSize=22,PrimaryColour=&HFFFFFF,OutlineColour=&H40000000,BorderStyle=3,Outline=1,Shadow=1,Alignment=2'" \
  final_output.mp4
```

---

### 3.6 一键生成脚本 `generate_video.py`

```python
"""
Usage:
  1. Start dev server: npm run dev + uvicorn backend.main:app
  2. export ELEVENLABS_API_KEY=... OPENAI_API_KEY=...
  3. python generate_video.py
"""
import subprocess, os, glob
from openai import OpenAI

TRANSCRIPT = open("transcript.txt").read()
VOICE_ID   = "JBFqnCBsd6RMkjVDRZzb"  # ElevenLabs George

def gen_voice():
    from elevenlabs.client import ElevenLabs
    el = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    audio = el.text_to_speech.convert(
        voice_id=VOICE_ID,
        text=TRANSCRIPT,
        model_id="eleven_turbo_v2_5",
        voice_settings={"stability": 0.5, "similarity_boost": 0.75, "style": 0.2},
    )
    with open("voiceover.mp3", "wb") as f:
        for chunk in audio: f.write(chunk)
    print("✅ voiceover.mp3")

def gen_subtitles():
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with open("voiceover.mp3", "rb") as f:
        srt = client.audio.transcriptions.create(
            model="whisper-1", file=f, response_format="srt"
        )
    open("subtitles.srt", "w").write(srt)
    print("✅ subtitles.srt")

def record_screen():
    print("▶ Starting Playwright recording (takes ~3 min)...")
    subprocess.run(["node", "record_demo.js"], check=True)
    webm = glob.glob("video-*.webm")[0]
    subprocess.run(["ffmpeg", "-y", "-i", webm, "-c:v", "libx264", "-crf", "18",
                    "screen_recording.mp4"], check=True)
    print("✅ screen_recording.mp4")

def merge():
    style = "FontName=Arial,FontSize=22,PrimaryColour=&HFFFFFF,OutlineColour=&H40000000,BorderStyle=3,Outline=1,Shadow=1,Alignment=2"
    subprocess.run(["ffmpeg", "-y", "-i", "screen_recording.mp4", "-i", "voiceover.mp3",
                    "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
                    "merged.mp4"], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", "merged.mp4",
                    "-vf", f"subtitles=subtitles.srt:force_style='{style}'",
                    "final_output.mp4"], check=True)
    print("✅ final_output.mp4 — done!")

if __name__ == "__main__":
    gen_voice()
    gen_subtitles()
    record_screen()   # 需要先启动开发服务器
    merge()
```

---

## 4. 操作检查清单

```
[ ] 1. 将文稿纯文本保存为 transcript.txt（去掉时间标注和画面注释）
[ ] 2. 设置环境变量 ELEVENLABS_API_KEY 和 OPENAI_API_KEY
[ ] 3. npm install playwright && npx playwright install chromium
[ ] 4. pip install elevenlabs openai
[ ] 5. 启动前端 (npm run dev) 和后端 (uvicorn)，确保数据已加载
[ ] 6. python generate_video.py（约等待 5 分钟：配音 + 字幕 + 3 分钟录制 + 合成）
[ ] 7. 检查 final_output.mp4：字幕对齐、点击节奏是否顺畅
[ ] 8. （可选）DaVinci Resolve 做片头淡入 + 片尾字幕卡
[ ] 9. 导出上传
```

---

## 5. 关于 Playwright 鼠标动画的说明

Playwright 默认录制中**不显示系统鼠标光标**，上述脚本通过 **CSS 注入的虚拟光标** 解决了这个问题：

- 蓝色半透明圆点跟随鼠标实时移动
- 点击时触发扩散波纹动画（`clickPulse`）
- 移动路径带 `steps` 参数，产生流畅的滑动轨迹，而非瞬移

如果想要更精美的光标效果（如箭头形状 + 高亮圈），可替换为 `playwright-mouse-helper` 包：

```bash
npm install playwright-mouse-helper
```

```javascript
const { installMouseHelper } = require('playwright-mouse-helper');
await installMouseHelper(page); // 一行替换上述 CSS 注入
```

---

## 6. 费用估算

| 工具 | 费用 |
|------|------|
| ElevenLabs（一个月 Creator）| $22 |
| OpenAI Whisper API | ~$0.02（3 分钟）|
| Playwright | 免费 |
| FFmpeg | 免费 |
| **合计** | **约 $22** |

> Whisper 也可完全本地运行（`pip install openai-whisper`），费用降为 $0。
> ElevenLabs 免费层 10,000 字符/月，本文稿约 13,000 字符，**略超**，可拆成两次请求或升级一个月。
