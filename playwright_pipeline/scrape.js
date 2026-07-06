const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const keywords = (process.env.KEYWORDS || process.argv[2] || '주식').split(',');
  const out = [];
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage();

  for (const kw of keywords) {
    const q = kw.trim();
    await page.goto(`https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`);
    await page.waitForTimeout(2000);
    const items = await page.$$eval('ytd-video-renderer', nodes => nodes.slice(0,10).map(n => {
      const a = n.querySelector('#video-title');
      const url = a ? a.href : null;
      const title = a ? a.textContent.trim() : null;
      const meta = n.querySelector('#metadata-line') ? n.querySelector('#metadata-line').innerText.trim() : null;
      return { title, url, meta };
    }));
    out.push({ keyword: q, items });
  }

  const outdir = '/data';
  if (!fs.existsSync(outdir)) fs.mkdirSync(outdir, { recursive: true });
  const filename = `${outdir}/youtube_${Date.now()}.json`;
  fs.writeFileSync(filename, JSON.stringify(out, null, 2));
  console.log('Saved', filename);
  await browser.close();
})();
