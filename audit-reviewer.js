const { chromium } = require('playwright');
const fs = require('fs');

const BASE = 'http://127.0.0.1:8080';
const FINDINGS = [];

function finding(hat, severity, title, page, whatHappened, expected, impact) {
  FINDINGS.push({ hat, severity, title, page, whatHappened, expected, impact });
}

// Helper to log observations
function log(msg) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
  });
  const page = await context.newPage();

  // =============================================
  // STEP 1: LOGIN
  // =============================================
  log('=== STEP 1: LOGIN ===');
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 10000 });
  log('Login page loaded');

  // Check login page has branding and fields
  const brandText = await page.textContent('.login-brand');
  log(`Login brand: ${brandText}`);

  // Fill credentials
  await page.fill('input[autocomplete="username"]', 'reviewer01');
  await page.fill('input[autocomplete="current-password"]', 'reviewer123');
  log('Credentials filled');

  // Click login
  await page.click('button:has-text("进入系统")');
  await page.waitForURL('**/reviewer', { timeout: 15000 });
  log('Logged in successfully, redirected to reviewer dashboard');

  // =============================================
  // STEP 2: REVIEWER DASHBOARD (个人看板)
  // =============================================
  log('\n=== STEP 2: REVIEWER DASHBOARD ===');
  await sleep(2000); // allow data to load

  const pageTitle = await page.textContent('h1');
  log(`Dashboard title: "${pageTitle}"`);

  if (pageTitle !== 'QC 个人看板') {
    finding('A', 'HIGH', 'Dashboard title mismatch',
      'Reviewer Dashboard',
      `Expected "QC 个人看板" but got "${pageTitle}"`,
      'Should show "QC 个人看板"',
      'Wrong page or layout issue');
  }

  // Check stat cards
  const statCards = await page.$$('.qc-stat-card');
  log(`Found ${statCards.length} stat cards`);

  const pendingText = await page.textContent('.qc-stat-card-blue strong');
  const inReviewText = await page.textContent('.qc-stat-card-orange strong');
  const doneText = await page.textContent('.qc-stat-card-green strong');
  const totalText = await page.textContent('.qc-stat-card-purple strong');
  log(`Stats - Pending: ${pendingText}, InReview: ${inReviewText}, Done: ${doneText}, Total: ${totalText}`);

  if (!pendingText || !inReviewText || !doneText || !totalText) {
    finding('A', 'MEDIUM', 'Dashboard stat cards missing data',
      'Reviewer Dashboard',
      'One or more stat cards show empty or missing values',
      'All stat cards should display numeric values',
      'Reviewer cannot assess workload at a glance');
  }

  // Check batch groups table
  const batchTable = await page.$('.el-table');
  if (batchTable) {
    const batchRows = await page.$$('.el-table__body-wrapper tbody tr');
    log(`Batch groups: ${batchRows.length} rows`);
    if (batchRows.length === 0) {
      // Could be empty state
      const emptyEl = await page.$('.el-empty');
      if (emptyEl) {
        log('Batch groups show empty state');
      } else {
        finding('B', 'LOW', 'No batch data but no empty-state indicator',
          'Reviewer Dashboard',
          'Batch table has zero rows but no ElEmpty component visible',
          'Should show "暂无分配到你的任务" when no tasks assigned',
          'Confusing for new reviewers');
      }
    }
  }

  // Check "开始质检" button
  const startButton = await page.$('button:has-text("开始质检")');
  if (!startButton) {
    const noTaskButton = await page.$('button:has-text("暂无待质检任务")');
    if (noTaskButton) {
      log('No tasks available for review - this is expected if DB is empty');
      finding('B', 'LOW', 'No tasks assigned to reviewer',
        'Reviewer Dashboard',
        '按钮显示"暂无待质检任务"，无可用质检任务',
        '系统应有任务并分配给审核员',
        'If this is a fresh system, admin should assign tasks first');
    } else {
      finding('A', 'HIGH', 'Start QC button missing',
        'Reviewer Dashboard',
        'Neither "开始质检" nor "暂无待质检任务" button found on dashboard',
        'Should show one of these buttons',
        'Reviewer cannot start their workflow');
    }
  } else {
    const isDisabled = await startButton.getAttribute('disabled');
    log(`Start QC button disabled: ${isDisabled}`);
  }

  // =============================================
  // STEP 3: TASK POOL (人工质检入口)
  // =============================================
  log('\n=== STEP 3: TASK POOL ===');
  await page.goto(`${BASE}/task-pool`, { waitUntil: 'networkidle' });
  await sleep(2000);

  const taskPoolTitle = await page.textContent('h1');
  log(`Task pool title: "${taskPoolTitle}"`);

  if (taskPoolTitle !== '我的质检任务') {
    finding('A', 'HIGH', 'Task pool title mismatch for reviewer',
      'Task Pool',
      `Expected "我的质检任务" but got "${taskPoolTitle}"`,
      'Reviewer should see "我的质检任务"',
      'Role-based display may be broken');
  }

  // Check filter tabs (全部/待处理/进行中/已完成)
  const filterTabs = await page.$$('.el-radio-button');
  log(`Filter tabs found: ${filterTabs.length}`);
  const tabLabels = [];
  for (const tab of filterTabs) {
    const label = await tab.textContent();
    tabLabels.push(label.trim());
  }
  log(`Tab labels: ${tabLabels.join(', ')}`);

  if (!tabLabels.includes('全部') || !tabLabels.includes('待处理') || !tabLabels.includes('进行中') || !tabLabels.includes('已完成')) {
    finding('A', 'MEDIUM', 'Task pool missing filter tabs',
      'Task Pool',
      `Available tabs: ${tabLabels.join(', ')}`,
      'Should have 全部/待处理/进行中/已完成',
      'Cannot filter tasks by status');
  }

  // Check if tasks exist
  const taskRows = await page.$$('.el-table__body-wrapper tbody tr');
  log(`Task rows in pool: ${taskRows.length}`);

  if (taskRows.length > 0) {
    // Click first task's "进入质检" link
    const qcLink = await page.$('.el-table__body-wrapper tbody tr a:has-text("进入质检")');
    if (qcLink) {
      log('Found "进入质检" link, clicking...');
      await qcLink.click();
      await page.waitForURL('**/manual-qc/**', { timeout: 15000 });
      log('Navigated to manual QC workspace');
    } else {
      log('No "进入质检" link found in task table');
      finding('B', 'MEDIUM', 'No QC entry link in task pool',
        'Task Pool',
        'Task rows exist but no "进入质检" link visible',
        'Each task should have a clickable entry point',
        'Friction: reviewer must navigate differently to start QC');
    }
  } else {
    log('No task rows - navigating to manual QC directly requires an episode ID');
    // Try to fetch any available episode from the API
    finding('B', 'HIGH', 'No reviewable tasks in task pool',
      'Task Pool',
      'Task pool shows zero tasks',
      'Should have at least some tasks assigned',
      'System may not have data loaded - cannot complete full QA');
  }

  // =============================================
  // STEP 4: MANUAL QC WORKSPACE (if we got there)
  // =============================================
  const currentUrl = page.url();
  if (currentUrl.includes('/manual-qc/')) {
    log('\n=== STEP 4: MANUAL QC WORKSPACE ===');
    await sleep(3000); // allow video and data to load

    // Check page title
    const qcTitle = await page.textContent('h1');
    log(`QC workspace title: "${qcTitle}"`);

    // Check lock panel
    const lockPanel = await page.$('.lock-panel');
    if (lockPanel) {
      const lockText = await lockPanel.textContent();
      log(`Lock panel: ${lockText.trim().substring(0, 100)}`);
    }

    // Check video player existence
    const videos = await page.$$('video');
    log(`Video elements found: ${videos.length}`);

    if (videos.length === 0) {
      finding('A', 'HIGH', 'No video elements in manual QC workspace',
        'Manual QC',
        'Video elements missing from the video grid',
        'Should have at least one video player',
        'Core QC feature broken');
    } else {
      // Check download attribute / controls
      for (let i = 0; i < videos.length; i++) {
        const video = videos[i];
        const hasDownload = await video.getAttribute('download');
        const hasControls = await video.getAttribute('controls');
        const hasPip = await video.getAttribute('disablePictureInPicture');
        const src = await video.getAttribute('src');
        log(`Video ${i}: download=${hasDownload}, controls=${hasControls}, disablePictureInPicture=${hasPip}, src=${src?.substring(0, 80)}`);

        if (hasDownload !== null) {
          finding('A', 'HIGH', 'Video has download attribute',
            'Manual QC',
            `Video element #${i} has download attribute set to "${hasDownload}"`,
            'Videos should NOT have download attribute - reviewers should not download raw data',
            'Security/data-leak risk');
        }

        if (hasControls === null || hasControls === 'false') {
          // Fine - native controls may be hidden
        } else if (hasControls !== 'false') {
          finding('B', 'LOW', 'Native video controls visible',
            'Manual QC',
            `Video #${i} has native controls attribute: ${hasControls}`,
            'Native controls should be hidden; custom playback controls are used',
            'Duplicate controls may confuse reviewers');
        }

        if (hasPip !== null) {
          log(`Video #${i} has disablePictureInPicture attribute`);
        } else {
          finding('B', 'MEDIUM', 'Picture-in-picture not disabled',
            'Manual QC',
            `Video #${i} missing disablePictureInPicture attribute`,
            'PiP should be disabled to prevent reviewers from watching videos outside the QC context',
            'Reviewers could bypass QC workflow by watching in PiP');
        }
      }
    }

    // Check variant switching (RGB/Depth)
    // Element Plus el-radio-button renders label as text content, not value attribute
    const rgbBtn = await page.$('.el-radio-button:has-text("RGB")');
    const depthBtn = await page.$('.el-radio-button:has-text("Depth Colormap")') || await page.$('.el-radio-button:has-text("Depth")');
    if (rgbBtn && depthBtn) {
      log('Variant switching buttons found (RGB/Depth)');
      // Try switching to depth
      await depthBtn.click({ force: true });
      await sleep(1500);
      log('Switched to Depth variant');
      await rgbBtn.click({ force: true });
      await sleep(1500);
      log('Switched back to RGB');
    } else {
      finding('B', 'MEDIUM', 'Variant switching buttons missing',
        'Manual QC',
        `RGB button: ${!!rgbBtn}, Depth button: ${!!depthBtn}`,
        'Should have toggle between RGB and Depth colormap views',
        'Cannot review depth data');
    }

    // Check refresh button
    const refreshBtn = await page.$('button:has-text("刷新预览")');
    if (refreshBtn) {
      log('Refresh preview button found');
      const refreshDisabled = await refreshBtn.getAttribute('disabled');
      log(`Refresh button disabled: ${refreshDisabled}`);
    }

    // Check timeline/playback controls
    const playButton = await page.$('button:has-text("播放")');
    const pauseButton = await page.$('button:has-text("暂停")');
    const prevFrameBtn = await page.$('button:has-text("上一帧")');
    const nextFrameBtn = await page.$('button:has-text("下一帧")');
    const minus1sBtn = await page.$('button:has-text("-1s")');
    const plus1sBtn = await page.$('button:has-text("+1s")');

    log(`Playback controls: play=${!!playButton}, pause=${!!pauseButton}, prev-frame=${!!prevFrameBtn}, next-frame=${!!nextFrameBtn}, -1s=${!!minus1sBtn}, +1s=${!!plus1sBtn}`);

    if (!playButton && !pauseButton) {
      finding('A', 'HIGH', 'Play/pause controls missing',
        'Manual QC',
        'Neither play nor pause button found',
        'Should have a toggle play/pause button',
        'Core playback function unavailable');
    }

    // Try playing video
    if (playButton) {
      await playButton.click();
      await sleep(2000);
      log('Clicked play');
      // Check if it changed to pause
      const pauseAfterPlay = await page.$('button:has-text("暂停")');
      if (pauseAfterPlay && pauseButton) {
        log('Play button changed to Pause - playback started');
        await pauseAfterPlay.click();
        await sleep(500);
      }
    }

    // Test frame stepping
    if (nextFrameBtn) {
      const frameBefore = await page.textContent('.timeline-header strong');
      log(`Frame before stepping: ${frameBefore}`);
      await nextFrameBtn.click();
      await sleep(500);
      const frameAfter = await page.textContent('.timeline-header strong');
      log(`Frame after stepping: ${frameAfter}`);
    }

    // Check slider
    const slider = await page.$('.el-slider');
    if (!slider) {
      finding('B', 'MEDIUM', 'Timeline slider missing',
        'Manual QC',
        'ElSlider component not found in timeline card',
        'Should have a frame scrubber slider',
        'Cannot seek to specific frames');
    }

    // Check timeline segments (anomaly ranges)
    const segmentChips = await page.$$('.segment-chip');
    log(`Timeline segment chips: ${segmentChips.length}`);

    if (segmentChips.length > 0) {
      for (const chip of segmentChips) {
        const chipText = await chip.textContent();
        const chipClasses = await chip.getAttribute('class');
        log(`  Segment: "${chipText.trim()}" [${chipClasses}]`);
      }
    }

    // Check L3 metric cards
    const scoreRing = await page.$('.score-ring');
    if (scoreRing) {
      const scoreText = await scoreRing.textContent();
      log(`Score ring: ${scoreText.trim()}`);
    }

    const metricItems = await page.$$('.metric-item');
    log(`Metric items: ${metricItems.length}`);

    if (metricItems.length > 0) {
      const metricLabels = [];
      for (const item of metricItems) {
        const label = await item.textContent();
        metricLabels.push(label.trim().substring(0, 60));
      }
      log(`Metric labels: ${metricLabels.join(' | ')}`);

      // Check if Q_motion is in the score ring
      if (scoreRing) {
        const scoreRingText = await scoreRing.textContent();
        if (!scoreRingText.toLowerCase().includes('q_motion') && !scoreRingText.toLowerCase().includes('motion')) {
          finding('A', 'HIGH', 'Q_motion not shown in score ring',
            'Manual QC',
            `Score ring shows: "${scoreRingText.trim()}" but should prioritize Q_motion`,
            'Code comments say "评分环固定展示综合质量分 Q_motion"',
            'Wrong metric displayed as the primary quality indicator');
        }
      }

      // Check sorting by severity
      const levels = [];
      for (const item of metricItems) {
        const cls = await item.getAttribute('class');
        if (cls.includes('bad')) levels.push('bad');
        else if (cls.includes('warn')) levels.push('warn');
        else if (cls.includes('good')) levels.push('good');
        else levels.push('unknown');
      }
      log(`Metric levels (in order): ${levels.join(', ')}`);

      // Verify sorted: bad first, then warn, then good
      let sortedBySeverity = true;
      let lastLevel = 0; // 0=bad, 1=warn, 2=good
      const levelMap = { bad: 0, warn: 1, good: 2, unknown: 3 };
      for (const level of levels) {
        const current = levelMap[level] ?? 3;
        if (current < lastLevel) {
          sortedBySeverity = false;
          break;
        }
        lastLevel = current;
      }

      if (!sortedBySeverity) {
        finding('A', 'MEDIUM', 'Metric cards not sorted by severity',
          'Manual QC',
          `Metrics appear in order: ${levels.join(', ')}. Should be: bad first, then warn, then good`,
          'Code compute property "sortedMetricCards" sorts by severity',
          'Harder to spot critical issues when metrics are out of order');
      }
    } else {
      finding('A', 'MEDIUM', 'No metric cards displayed',
        'Manual QC',
        'Zero metric items in the score sidebar',
        'Should show L3 metric cards (Q_motion, etc.)',
        'Key QC reference data missing');
    }

    // Check telemetry curve chart
    const chartCanvas = await page.$('canvas');
    if (chartCanvas) {
      log('Chart.js canvas found for telemetry curve');
    } else {
      log('Chart canvas not found - may show "加载中" state or no data');
    }

    // Check arm/hand toggle
    const armBtn = await page.$('.el-radio-button[value="arm"]');
    const handBtn = await page.$('.el-radio-button[value="hand"]');
    if (armBtn && handBtn) {
      log('Arm/Hand toggle buttons found');
      const armDisabled = await armBtn.getAttribute('disabled');
      const handDisabled = await handBtn.getAttribute('disabled');
      log(`Arm disabled: ${armDisabled}, Hand disabled: ${handDisabled}`);
    } else {
      finding('B', 'LOW', 'Arm/Hand toggle buttons not found',
        'Manual QC',
        'Telemetry curve section lacks arm/hand radio buttons',
        'Should have toggle between mechanical arm and dexterous hand',
        'Cannot switch between joint dimension views');
    }

    // Check claim/release lock flow
    const claimBtn = await page.$('button:has-text("认领任务")');
    const releaseBtn = await page.$('button:has-text("释放锁")');
    const reClaimBtn = await page.$('button:has-text("重新认领")');

    if (reClaimBtn) {
      log('Already claimed - "重新认领" button found');
      // Test release then claim
      if (releaseBtn) {
        log('Clicking "释放锁"...');
        await releaseBtn.click({ force: true });
        await sleep(2500);
        const claimAfterRelease = await page.$('button:has-text("认领任务")');
        if (claimAfterRelease) {
          log('Lock released successfully, "认领任务" button appeared');
          await claimAfterRelease.click({ force: true });
          await sleep(2500);
          const reclaimAfterClaim = await page.$('button:has-text("重新认领")');
          if (reclaimAfterClaim || await page.$('button:has-text("释放锁")')) {
            log('Claim/release flow works correctly');
          }
        }
      }
    } else if (claimBtn) {
      log('Not yet claimed - clicking "认领任务"...');
      // Use force:true because sticky sidebar may intercept pointer events
      await claimBtn.click({ force: true });
      await sleep(2500);
      const afterClaim = await page.$('button:has-text("释放锁")') || await page.$('button:has-text("重新认领")');
      if (afterClaim) {
        log('Claim successful!');
      } else {
        finding('A', 'HIGH', 'Claim task flow broken',
          'Manual QC',
          'Clicked "认领任务" but lock was not acquired (no "释放锁" or "重新认领" button appeared)',
          'Claiming should acquire the review lock and update the UI',
          'Reviewer cannot submit QC results');
      }
    }

    // Check submit QC result
    const submitBtn = await page.$('button:has-text("提交结果")');
    if (submitBtn) {
      const submitDisabled = await submitBtn.getAttribute('disabled');
      log(`Submit button disabled: ${submitDisabled}`);

      if (submitDisabled === null) {
        // Try submitting with pass
        log('Submit button enabled, attempting pass submission...');
        await submitBtn.click();
        await sleep(2000);
        // Check for success message
        const successMsg = await page.$('.el-message--success');
        if (successMsg) {
          log('Pass submission successful!');
        }
      } else {
        // May need to claim first
        log('Submit button disabled - likely need to claim task first');
      }

      // Check reason code picker
      const passRadioBtn = await page.$('.el-radio-button:has-text("Pass")');
      const failRadioBtn = await page.$('.el-radio-button:has-text("Fail")');
      if (passRadioBtn && failRadioBtn) {
        log('Pass/Fail radio buttons found');
        // Try switching to fail
        await failRadioBtn.click({ force: true });
        await sleep(1000);
        const reasonSelect = await page.$('.el-select');
        if (reasonSelect) {
          log('Reason code selector appeared after selecting Fail');
        } else {
          finding('A', 'HIGH', 'Reason code selector not shown for Fail',
            'Manual QC',
            'Selected "Fail" but no reason code dropdown appeared',
            'Fail results must include a primary reason code',
            'Cannot submit fail results properly');
        }
        // Switch back to pass
        if (passRadioBtn) await passRadioBtn.click({ force: true });
      }
    } else {
      finding('A', 'HIGH', 'Submit button missing',
        'Manual QC',
        '"提交结果" button not found in the QC conclusion card',
        'Should have a submit button for QC results',
        'Core workflow completion impossible');
    }

    // Check revision history
    const revisions = await page.$$('.revision-item');
    log(`Revision history entries: ${revisions.length}`);

    // Check that there are NO download buttons on videos
    const downloadButtons = await page.$$('a[download], button:has-text("下载"), button:has-text("Download"), .el-button:has-text("下载")');
    if (downloadButtons.length > 0) {
      finding('A', 'HIGH', 'Download buttons found on QC page',
        'Manual QC',
        `Found ${downloadButtons.length} download element(s) on page`,
        'No download functionality should be available to reviewers',
        'Unauthorized data exfiltration risk');
    } else {
      log('No download buttons found - good');
    }

    // Check note textarea
    const noteTextarea = await page.$('textarea');
    if (noteTextarea) {
      log('Note textarea found');
      await noteTextarea.fill('Test note from automated review');
      await sleep(300);
      const noteValue = await noteTextarea.inputValue();
      log(`Note textarea accepts input: ${noteValue.length > 0}`);
    }
  }

  // =============================================
  // STEP 5: ACCESS CONTROL - Admin-only pages
  // =============================================
  log('\n=== STEP 5: ACCESS CONTROL ===');

  const adminPages = [
    { path: '/settings', expected: '/reviewer', name: 'Settings' },
    { path: '/accounts', expected: '/reviewer', name: 'Accounts' },
    { path: '/database', expected: '/reviewer', name: 'Database' },
    { path: '/task-types', expected: '/reviewer', name: 'Task Types' },
    { path: '/qc-history', expected: '/reviewer', name: 'QC History' },
    { path: '/dashboard', expected: '/reviewer', name: 'Admin Dashboard' },
  ];

  for (const adminPage of adminPages) {
    log(`Testing access to ${adminPage.path}...`);
    await page.goto(`${BASE}${adminPage.path}`, { waitUntil: 'networkidle' });
    await sleep(1500);
    const redirectedUrl = page.url();

    if (redirectedUrl.includes(adminPage.expected)) {
      log(`  CORRECT: Redirected to ${adminPage.expected}`);
    } else if (redirectedUrl.includes(adminPage.path)) {
      finding('A', 'CRITICAL', `Reviewer can access admin page: ${adminPage.name}`,
        adminPage.name,
        `Navigated to ${adminPage.path} and was NOT redirected away. URL: ${redirectedUrl}`,
        `Should redirect to /reviewer since reviewer role lacks permission for ${adminPage.path}`,
        'Role-based access control (RBAC) is broken - reviewers can access admin-only functionality');
    } else {
      finding('A', 'MEDIUM', `Unexpected redirect for ${adminPage.name}`,
        adminPage.name,
        `Navigated to ${adminPage.path} and was redirected to ${redirectedUrl} (expected ${adminPage.expected})`,
        `Should redirect to ${adminPage.expected}`,
        'Redirect logic may have bugs');
    }
  }

  // =============================================
  // STEP 6: ADDITIONAL CHECKS
  // =============================================
  log('\n=== STEP 6: ADDITIONAL CHECKS ===');

  // Go back to task pool and test filter tabs
  await page.goto(`${BASE}/task-pool`, { waitUntil: 'networkidle' });
  await sleep(1500);

  // Test clicking "待处理" tab
  const pendingTab = await page.$('.el-radio-button:has-text("待处理")');
  if (pendingTab) {
    await pendingTab.click();
    await sleep(1000);
    log('Clicked "待处理" filter tab');
  }

  // Test clicking "进行中" tab
  const inReviewTab = await page.$('.el-radio-button:has-text("进行中")');
  if (inReviewTab) {
    await inReviewTab.click();
    await sleep(1000);
    log('Clicked "进行中" filter tab');
  }

  // Test clicking "已完成" tab
  const doneTab = await page.$('.el-radio-button:has-text("已完成")');
  if (doneTab) {
    await doneTab.click();
    await sleep(1000);
    log('Clicked "已完成" filter tab');
  }

  // Check for ElMessage/notification after interactions
  const messages = await page.$$('.el-message');
  log(`Visible ElMessage notifications: ${messages.length}`);

  // Check the AppLayout sidebar/navigation
  await page.goto(`${BASE}/reviewer`, { waitUntil: 'networkidle' });
  await sleep(1500);

  // Check sidebar links
  const sidebarLinks = await page.$$('.el-menu-item, .sidebar a, nav a');
  log(`Navigation links found: ${sidebarLinks.length}`);
  for (const link of sidebarLinks) {
    const text = await link.textContent();
    log(`  Nav: ${text.trim().substring(0, 50)}`);
  }

  // Check logout functionality
  const logoutBtn = await page.$('button:has-text("退出"), .logout-btn, button:has-text("登出")');
  if (logoutBtn) {
    log('Logout button found');
  } else {
    finding('B', 'MEDIUM', 'No logout button visible',
      'AppLayout',
      'Could not find logout/退出 button in the navigation',
      'Should have a way to log out',
      'Reviewer cannot easily switch accounts or secure their session');
  }

  // Take a screenshot for documentation
  await page.screenshot({ path: '/tmp/reviewer-dashboard.png', fullPage: true });
  log('Screenshot saved to /tmp/reviewer-dashboard.png');

  // =============================================
  // REPORT
  // =============================================
  console.log('\n\n');
  console.log('='.repeat(80));
  console.log('                    REVIEWER QA AUDIT REPORT');
  console.log('='.repeat(80));
  console.log(`Total findings: ${FINDINGS.length}\n`);

  if (FINDINGS.length === 0) {
    console.log('  No issues found! All checks passed.');
  } else {
    // Group by severity
    const critical = FINDINGS.filter(f => f.severity === 'CRITICAL');
    const high = FINDINGS.filter(f => f.severity === 'HIGH');
    const medium = FINDINGS.filter(f => f.severity === 'MEDIUM');
    const low = FINDINGS.filter(f => f.severity === 'LOW');

    console.log(`  CRITICAL: ${critical.length}`);
    console.log(`  HIGH:     ${high.length}`);
    console.log(`  MEDIUM:   ${medium.length}`);
    console.log(`  LOW:      ${low.length}`);
    console.log();

    for (const f of FINDINGS) {
      console.log(`[${f.hat}] [${f.severity}] ${f.title}`);
      console.log(`  Page: ${f.page}`);
      console.log(`  What happened: ${f.whatHappened}`);
      console.log(`  Expected: ${f.expected}`);
      console.log(`  Impact: ${f.impact}`);
      console.log();
    }
  }
  // Save findings to JSON
  fs.writeFileSync('/tmp/reviewer-audit-findings.json', JSON.stringify(FINDINGS, null, 2));
  console.log('Findings saved to /tmp/reviewer-audit-findings.json');

  await browser.close();
  console.log('\nAudit complete.');
})();
