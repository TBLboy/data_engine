const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
  const page = await context.newPage();

  // Login as reviewer01
  await page.goto('http://127.0.0.1:8080/login', { waitUntil: 'networkidle' });
  await page.fill('input[autocomplete="username"]', 'reviewer01');
  await page.fill('input[autocomplete="current-password"]', 'reviewer123');
  await page.click('button:has-text("进入系统")');
  await page.waitForURL('**/reviewer', { timeout: 15000 });

  // Try accessing settings page
  console.log('Testing /settings access...');
  await page.goto('http://127.0.0.1:8080/settings', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  console.log(`Current URL: ${page.url()}`);

  if (page.url().includes('/settings')) {
    await page.waitForTimeout(1000);
    const bodyText = await page.textContent('body');
    console.log(`Settings page body (first 800 chars): ${bodyText.substring(0, 800)}`);
    await page.screenshot({ path: '/tmp/settings-accessed-by-reviewer.png', fullPage: true });
    console.log('CRITICAL: Reviewer can access settings! Screenshot saved.');
  } else {
    console.log(`Redirected to: ${page.url()}`);
  }

  // Now test the claim flow more carefully
  console.log('\nTesting claim flow on manual QC...');
  await page.goto('http://127.0.0.1:8080/task-pool', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  const qcLink = await page.$('a:has-text("进入质检")');
  if (qcLink) {
    await qcLink.click();
    await page.waitForURL('**/manual-qc/**', { timeout: 15000 });
    await page.waitForTimeout(3000);
    console.log(`On manual QC page: ${page.url()}`);

    // Check if the lock panel button is truly visible or obscured
    const claimBtn = await page.$('button:has-text("认领任务")');
    if (claimBtn) {
      const box = await claimBtn.boundingBox();
      console.log(`Claim button boundingBox: ${JSON.stringify(box)}`);

      // Check if it's visible in viewport
      const isVisible = await claimBtn.isVisible();
      console.log(`Claim button isVisible: ${isVisible}`);

      // Check what element is at the center of the claim button
      if (box) {
        const elAtPoint = await page.evaluate(({ x, y }) => {
          const el = document.elementFromPoint(x + 50, y + 15);
          return el ? `${el.tagName}.${el.className}` : 'null';
        }, { x: box.x, y: box.y });
        console.log(`Element at claim button center: ${elAtPoint}`);
      }

      // Try clicking via JS directly
      console.log('Clicking claim via evaluate...');
      await page.evaluate(() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
          if (btn.textContent.includes('认领任务')) {
            btn.click();
            console.log('Clicked claim button via JS');
            return;
          }
        }
      });
      await page.waitForTimeout(3000);

      // Check if lock was acquired
      const lockPanelText = await page.textContent('.lock-panel');
      console.log(`Lock panel after claim attempt: ${lockPanelText?.substring(0, 200)}`);

      // Check network for claim API response
      const releaseBtn = await page.$('button:has-text("释放锁")');
      const reClaimBtn2 = await page.$('button:has-text("重新认领")');
      console.log(`After claim: releaseBtn=${!!releaseBtn}, reClaimBtn=${!!reClaimBtn2}`);

      if (!releaseBtn && !reClaimBtn2) {
        console.log('Claim still failed even with JS click. Checking API...');
        // This might mean the API rejected the claim
      }
    }

    // Check telemetry chart loading
    console.log('\nChecking telemetry chart...');
    const canvas = await page.$('canvas');
    console.log(`Canvas found: ${!!canvas}`);

    const chartSection = await page.$('.qc-card:has-text("遥操作")');
    if (chartSection) {
      const chartText = await chartSection.textContent();
      console.log(`Chart section text: ${chartText.substring(0, 300)}`);
    }

    // Check arm/hand buttons more carefully
    const allRadioButtons = await page.$$('.el-radio-button');
    console.log(`\nAll radio buttons on page:`);
    for (const rb of allRadioButtons) {
      const text = await rb.textContent();
      const disabled = await rb.getAttribute('disabled');
      const classes = await rb.getAttribute('class');
      console.log(`  "${text.trim()}" disabled=${disabled} class=${classes}`);
    }

    await page.screenshot({ path: '/tmp/manual-qc-fullpage.png', fullPage: true });
  }

  await browser.close();
  console.log('\nInvestigation complete.');
})();
