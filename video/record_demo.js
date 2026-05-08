// Playwright automated demo recording for EMS Intelligence Platform
// Run: node record_demo.js
// Prerequisites: node record_demo.js (frontend on :3000, backend on :8001)

const { chromium } = require('playwright');
const path = require('path');

const BASE_URL = 'http://localhost:3000';
const OUTPUT_DIR = path.join(__dirname, 'output');

const fs = require('fs');
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

// ── Cursor helpers ──────────────────────────────────────────────────────────

const CURSOR_CSS = `
  #pw-cursor {
    position: fixed;
    width: 26px; height: 26px; border-radius: 50%;
    background: rgba(59, 130, 246, 0.55);
    border: 2.5px solid #2563EB;
    pointer-events: none;
    z-index: 2147483647;
    transform: translate(-50%, -50%);
    box-shadow: 0 0 0 0 rgba(59,130,246,0.4);
    transition: background 0.1s;
  }
  #pw-cursor.click {
    animation: pwPulse 0.35s ease-out forwards;
  }
  @keyframes pwPulse {
    0%   { box-shadow: 0 0 0 0   rgba(59,130,246,0.7); }
    100% { box-shadow: 0 0 0 18px rgba(59,130,246,0);   }
  }
`;

const CURSOR_JS = `
  (function() {
    if (document.getElementById('pw-cursor')) return;
    const style = document.createElement('style');
    style.textContent = ${JSON.stringify(CURSOR_CSS)};
    document.head.appendChild(style);
    const cursor = document.createElement('div');
    cursor.id = 'pw-cursor';
    document.body.appendChild(cursor);
    document.addEventListener('mousemove', function(e) {
      cursor.style.left = e.clientX + 'px';
      cursor.style.top  = e.clientY + 'px';
    });
  })();
`;

async function injectCursor(page) {
  try { await page.evaluate(CURSOR_JS); } catch {}
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// Move mouse smoothly to (x, y)
async function moveTo(page, x, y, steps = 25) {
  await page.mouse.move(x, y, { steps });
}

// Click a selector with cursor highlight animation
async function click(page, selector, options = {}) {
  const locator = page.locator(selector).first();
  await locator.waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
  const box = await locator.boundingBox().catch(() => null);
  if (!box) { await locator.click(options).catch(() => {}); return; }
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await moveTo(page, x, y, 30);
  await page.evaluate(() => {
    const c = document.getElementById('pw-cursor');
    if (c) { c.classList.remove('click'); void c.offsetWidth; c.classList.add('click'); }
  });
  await sleep(250);
  await locator.click(options).catch(() => {});
  await sleep(150);
}

// Navigate and re-inject cursor (lost on full navigation)
async function goto(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await sleep(800);
  await injectCursor(page);
}

// Slow scroll
async function scroll(page, deltaY, steps = 5) {
  const dy = deltaY / steps;
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, dy);
    await sleep(120);
  }
}

// Pan mouse across the sidebar nav items slowly
async function panSidebar(page) {
  const navLinks = ['/news', '/analyst-view', '/chat', '/companies', '/ai-investments', '/map', '/calendar', '/data'];
  for (const href of navLinks) {
    const locator = page.locator(`a[href="${href}"]`).first();
    const box = await locator.boundingBox().catch(() => null);
    if (box) {
      await moveTo(page, box.x + box.width / 2, box.y + box.height / 2, 20);
      await sleep(600);
    }
  }
}

// ── Main script ─────────────────────────────────────────────────────────────

(async () => {
  console.log('Launching browser…');
  const browser = await chromium.launch({
    headless: false,
    args: ['--start-maximized'],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: {
      dir: OUTPUT_DIR,
      size: { width: 1440, height: 900 },
    },
  });

  // Re-inject cursor after every navigation
  context.on('page', async (page) => {
    page.on('load', () => injectCursor(page).catch(() => {}));
  });

  const page = await context.newPage();
  page.on('load', () => injectCursor(page).catch(() => {}));

  // ── PRE-WARM: visit key pages so localStorage cache is seeded ──────────────
  // Without this, Companies/Detail pages fetch from backend on first visit,
  // causing visible loading spinners during the actual demo recording.
  console.log('[pre-warm] Seeding localStorage cache…');
  await goto(page, BASE_URL + '/companies');
  await sleep(5000); // wait for all 3 fetch waves to complete
  await goto(page, BASE_URL + '/companies/flex');
  await sleep(5000); // wait for overview + financials + capex + hiring tabs
  await goto(page, BASE_URL + '/analyst-view');
  await sleep(4000);
  await goto(page, BASE_URL + '/ai-investments');
  await sleep(3000);
  console.log('[pre-warm] Done — starting actual recording');

  // ── [0:00 – 0:25] HOOK — Dashboard landing ───────────────────────────────
  console.log('[0:00] Hook — landing page');
  await goto(page, BASE_URL + '/');
  await sleep(2000);
  // Slow pan across the center area
  await moveTo(page, 720, 450, 40);
  await sleep(22000); // hold for voiceover

  // ── [0:25 – 1:00] WHAT WE BUILT — pan sidebar ───────────────────────────
  console.log('[0:25] What we built — sidebar pan');
  await panSidebar(page);
  await sleep(2000);
  await panSidebar(page); // second pass for full 35s
  await sleep(5000);

  // ── [1:00 – 1:11] NEWS ───────────────────────────────────────────────────
  console.log('[1:00] News');
  await goto(page, BASE_URL + '/news');
  await sleep(3000);
  // Scroll down to see feed
  await scroll(page, 300, 6);
  await sleep(1500);
  // Click "Data Center" preset button
  await click(page, 'button:has-text("Data Center")');
  await sleep(3000);

  // ── [1:11 – 1:21] ANALYST VIEW ───────────────────────────────────────────
  console.log('[1:11] Analyst View');
  await goto(page, BASE_URL + '/analyst-view');
  await sleep(4000);
  // Scroll down slightly to reveal executive summary cards
  await scroll(page, 250, 5);
  await sleep(4000);

  // ── [1:21 – 1:35] AI CHAT ────────────────────────────────────────────────
  console.log('[1:21] AI Chat');
  await goto(page, BASE_URL + '/chat');
  await sleep(2500);
  // Type question in chat input
  const chatInput = page.locator('textarea, input[placeholder*="Ask"], input[placeholder*="CapEx"]').first();
  await chatInput.waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
  const chatBox = await chatInput.boundingBox().catch(() => null);
  if (chatBox) {
    await moveTo(page, chatBox.x + chatBox.width / 2, chatBox.y + chatBox.height / 2, 20);
    await sleep(400);
    await chatInput.click().catch(() => {});
    await sleep(300);
  }
  await page.keyboard.type(
    "Compare the capital expenditures (CapEx) of Flex, Jabil, Celestica, Sanmina, Plexus, and Benchmark over the last five fiscal years (FY2020–2024). Present the data in a table",
    { delay: 38 }  // ~6s to type the full question
  );
  await sleep(1000);
  await page.keyboard.press('Enter');
  await sleep(9000); // wait for multi-company table to render

  // ── [1:35 – 1:55] COMPANIES ──────────────────────────────────────────────
  // localStorage cache is already warm from pre-warm step — should load instantly
  console.log('[1:35] Companies');
  await goto(page, BASE_URL + '/companies');
  await sleep(1500); // instant from cache
  // Hover over Flex card
  const flexCard = page.locator('text=FLEX').first();
  const flexBox = await flexCard.boundingBox().catch(() => null);
  if (flexBox) await moveTo(page, flexBox.x + flexBox.width / 2, flexBox.y + 40, 25);
  await sleep(1500);
  // Click View Details for Flex
  await click(page, 'a[href="/companies/flex"]');
  await sleep(1500); // instant from cache
  // Click Financials tab
  await click(page, 'button:has-text("Financials")');
  await sleep(2000);
  // Click CapEx tab
  await click(page, 'button:has-text("CapEx")');
  await sleep(2000);
  // Scroll down to anomaly section
  await scroll(page, 500, 6);
  await sleep(2500);

  // ── [1:55 – 2:05] HYPERSCALER ────────────────────────────────────────────
  console.log('[1:55] Hyperscaler');
  await goto(page, BASE_URL + '/ai-investments');
  await sleep(4000);
  // Scroll to YoY growth numbers
  await scroll(page, 300, 5);
  await sleep(4000);

  // ── [2:05 – 2:13] FACILITIES MAP ─────────────────────────────────────────
  console.log('[2:05] Facilities Map');
  await goto(page, BASE_URL + '/map');
  await sleep(4000);
  // Drag globe to rotate
  const globe = page.locator('canvas').first();
  const gBox = await globe.boundingBox().catch(() => null);
  if (gBox) {
    const cx = gBox.x + gBox.width * 0.5;
    const cy = gBox.y + gBox.height * 0.5;
    await moveTo(page, cx, cy, 15);
    await page.mouse.down();
    await moveTo(page, cx + gBox.width * 0.22, cy, 35);
    await page.mouse.up();
  }
  await sleep(2500);

  // ── [2:13 – 2:20] CALENDAR ───────────────────────────────────────────────
  console.log('[2:13] Calendar');
  await goto(page, BASE_URL + '/calendar');
  await sleep(3500);
  // Scroll to show events
  await scroll(page, 200, 4);
  await sleep(2500);

  // ── [2:20 – 2:28] DATA CENTER ────────────────────────────────────────────
  console.log('[2:20] Data Center');
  await goto(page, BASE_URL + '/data');
  await sleep(3000);
  await scroll(page, 300, 5);
  await sleep(2500);

  // ── [2:28 – 3:05] USE CASES + CLOSE — back to dashboard ─────────────────
  console.log('[2:28] Use cases + close');
  await goto(page, BASE_URL + '/');
  await sleep(2000);
  // Pan sidebar one more time for visual close
  await panSidebar(page);
  await sleep(10000); // hold on dashboard for closing voiceover

  console.log('Recording complete — closing browser');
  await context.close();
  await browser.close();

  // Rename output
  const files = fs.readdirSync(OUTPUT_DIR).filter(f => f.endsWith('.webm'));
  if (files.length > 0) {
    const src = path.join(OUTPUT_DIR, files[files.length - 1]);
    const dst = path.join(OUTPUT_DIR, 'screen_recording.webm');
    fs.renameSync(src, dst);
    console.log(`✅ Saved: output/screen_recording.webm`);
  }
})();
