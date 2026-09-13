"use strict";
// Offline UI acceptance. All application API requests are intercepted; no providers run.
const { chromium } = require('./acquisition/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

async function main() {
  const root = path.resolve(__dirname, '../web/out');
  const shots = path.resolve(__dirname, 'build/phase3-screenshots');
  fs.mkdirSync(shots, {recursive:true});
  const server = http.createServer((req,res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const file = path.join(root, pathname === '/' ? 'index.html' : pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', ({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'})[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true});
    const context = await browser.newContext({viewport:{width:1280,height:860}, reducedMotion:'reduce', acceptDownloads:true, permissions:['clipboard-read','clipboard-write']});
    const page = await context.newPage();
    const errors = []; page.on('pageerror', e=>errors.push(e.message));
    let preferences = {modelProfile:'standard-2026-09',dbPath:'/example/history.sqlite3',maxTokens:500000,maxCost:'0.20',maxCalls:160,supportEnabled:true,challengeEnabled:false,sourceTarget:10,useSerpSearch:true,useExa:true,useOpenAlex:true,useArxiv:false,usePubmed:false,useCrossref:true};
    let saved = []; let run = null; let started = null; let checked = 0; let removed = 0; let detailed = false;
    const id='11111111-1111-4111-8111-111111111111';
    const progress = {status:'running',model_attempts:1,retrieval_attempts:2,usable_snapshots:1,candidates:1};
    const snapshot = () => ({run_id:id,db_path:preferences.dbPath,raw_claim:started.raw_claim,classification:run,stage:'discovery',current_research_round:1,progress_percent:25,message:run === 'cancelled' ? 'Cancelled; incomplete work is preserved.' : 'Finding sources for your question.',model_calls_used:1,retrieval_attempts_used:2,known_cost_subtotal_usd:'0.01',cost_usage_complete:false,conservative_reserved_cost_usd:'0.02',supporting:{...progress,stance:'supporting'},opposing:{...progress,stance:'opposing'},validation_errors:[],research_controls:{research_mode:'balanced',sources_per_stance_per_round:10,discovery_providers:['arxiv']},final_brief:run === 'released' ? '# Research Brief\n\nA validated example finding.\n' : null,rendered_brief_hash:run === 'released' ? 'a'.repeat(64) : null,v2_diagnostics:null});
    await page.route('**/api/**', async route => {
      const req=route.request(); const url=new URL(req.url()); const p=url.pathname; let body={}; let status=200;
      if(p==='/api/preferences') { if(req.method()==='POST') preferences=req.postDataJSON(); body=preferences; }
      else if(p==='/api/configuration') body={configured:saved.includes('mimo') && saved.includes('openai'),message:'Offline test configuration',default_db_path:preferences.dbPath,saved_credentials:saved,saved_settings:[],firecrawl_enabled:false,service:{wigolo_ready:true,state:'healthy',message:'Research tools ready'}};
      else if(p==='/api/model-profiles') body=[{id:'standard-2026-09',name:'Standard research',description:'MiMo + Luna High',pricing_reviewed:'2026-09-07',models:[{model:'gpt-5.6-luna',roles:'Analysis',input_per_million:'0.50',output_per_million:'1.80',completion_limit:4096}]}];
      else if(p==='/api/credentials') { const keys=req.postDataJSON(); assert.equal(keys.mimo_api_key,'offline-mimo-key'); assert.equal(keys.luna_api_key,'offline-luna-key'); saved=['mimo','openai']; body={saved:true,message:'Saved',saved_settings:[]}; }
      else if(p.endsWith('/check')) { checked++; body={state:'connected',message:'Key accepted and supported models listed. No text was generated.'}; }
      else if(p.endsWith('/remove')) { removed++; saved=saved.filter(s=>s!=='mimo'); body={removed:true}; }
      else if(p==='/api/research/start') { started=req.postDataJSON(); run='running'; body={started:true,run_id:id,classification:'starting',message:'Research started.'}; }
      else if(p.endsWith('/cancel')) { run='cancelled'; body={cancelled:true,message:'Cancellation requested.'}; }
      else if(p==='/api/history') body={items:run ? [{run_id:id,raw_claim:started.raw_claim,status:run,stage:'discovery',updated_at:'2026-09-07T12:00:00Z'}] : []};
      else if(p.endsWith('/v2-result')) {
        if(!detailed) { status=404; body={detail:'Historical brief'}; }
        else body={run_id:id,exact_claim:started.raw_claim,directions:{support_enabled:true,challenge_enabled:true},synthesis:{sections:[{section_type:'supporting',items:[{approved_factual_statement:'Illustrative supporting finding.',admission_method:'analyzer_admitted'}]},{section_type:'opposing',items:[{approved_factual_statement:'Illustrative challenging finding.',admission_method:'analyzer_admitted'}]}]},recommended_source_ids:[],recommended_sources:[],all_surviving_sources:[],unresolved_material_gaps:[{gap_id:'internal-gap-example',direction:'challenge',missing_evidence:'Long-term air temperature data is unavailable.'}],stopping:{reason:'budget_limit',explanation:'Research stopped before all sources could be examined.'},release_validation:{valid:true,rendered_output_hash:'a'.repeat(64)}};
      }
      else if(p.endsWith('/v2-evidence')) body={run_id:id,items:detailed ? ['support','challenge'].map(direction=>({source_id:direction,title:direction==='support'?'Illustrative canopy study':'Illustrative climate review',source_url:'https://example.org/study',source_family:'Research paper',direction,recommendation_status:'Analyzed',selection_rationale:'Relevant to the question',gap_ids:[],evidence_summary:'Source context is limited to the measured conditions.',supporting_proposition:direction==='support'?'Canopy cover was associated with cooling.':'Cooling varied with local conditions.',quote_passage:'This is an exact illustrative quotation for the offline test.',limitations:['Surface temperatures only; not a general estimate of air temperature.'],validation_status:'analyzer_admitted'})) : []};
      else if(p.endsWith('/trail')) body={run_id:id,items:[]};
      else if(p===`/api/research/${id}`) body=snapshot();
      else { status=404; body={detail:'Unknown mocked API'}; }
      await route.fulfill({status,json:body});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    const preview = page.locator('.preview-wrap');
    await page.getByText('Example complete',{exact:true}).waitFor();
    await page.waitForTimeout(4000);
    assert.equal(await preview.getAttribute('data-preview-step'),'3','Reduced motion keeps the complete example still');
    assert.equal(await preview.getByRole('button').count(),0,'Example has no playback or direction buttons');
    assert.equal(await preview.locator('.evidence-tile').count(),4,'Completed example has four sourced cards');
    assert.equal(await preview.locator('.evidence-tile.support').count(),2);
    assert.equal(await preview.locator('.evidence-tile.challenge').count(),2);
    assert.equal(await preview.locator('.preview-conclusion').count(),0,'No takeaway panel');
    assert.equal(await preview.getByText(/Illustrative study|Illustrative review/).count(),0);
    assert.match(await preview.locator('h2').innerText(),/Green technology solves climate change/);
    const sourceLinks = await preview.locator('.evidence-source-row a').evaluateAll(links => links.map(link => link.href));
    assert.equal(new Set(sourceLinks).size,4,'Four distinct source documents');
    for (const link of sourceLinks) assert.ok(['www.iea.org','www.ipcc.ch','wedocs.unep.org'].includes(new URL(link).hostname));
    const loopStarted = Date.now();
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.getByText('Ready to begin',{exact:true}).waitFor();
    await page.mouse.move(0,0);
    await page.screenshot({path:path.join(shots,'home-ready.png'),fullPage:true,animations:'disabled'});
    for (const [step,state] of [[1,'active'],[2,'review'],[3,'complete'],[4,'error'],[1,'retry'],[2,'review-recovered'],[3,'complete-recovered'],[0,'loop-reset']]) {
      await page.waitForFunction(expected => document.querySelector('.preview-wrap')?.getAttribute('data-preview-step') === String(expected), step);
      assert.equal(await preview.getAttribute('data-preview-step'),String(step),`Automatic ${state} state`);
      await page.screenshot({path:path.join(shots,`preview-${state}.png`),fullPage:true,animations:'disabled'});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight),`Home fits at ${state}`);
    }
    const loopElapsed = Date.now() - loopStarted;
    assert.ok(loopElapsed > 10000 && loopElapsed < 14000, `Loop must stay over 10 seconds and finish promptly: ${loopElapsed}ms`);
    console.log(`Preview loop: ${loopElapsed}ms`);
    await page.waitForFunction(() => document.querySelector('.preview-wrap')?.getAttribute('data-preview-step') === '1');
    await preview.hover(); await page.waitForTimeout(4000);
    assert.equal(await preview.getAttribute('data-preview-step'),'1','Hover pauses the example');
    await page.mouse.move(0,0); await page.waitForFunction(() => document.querySelector('.preview-wrap')?.getAttribute('data-preview-step') === '2');
    assert.equal(await preview.getAttribute('data-preview-step'),'2','Example resumes after hover');
    await preview.locator('summary').first().focus(); await page.waitForTimeout(4000);
    assert.equal(await preview.getAttribute('data-preview-step'),'2','Keyboard source inspection pauses the example');
    assert.equal(started,null,'Preview must not create a real run');
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.getByRole('button',{name:'Connect providers',exact:true}).click();
    const dialog=page.getByRole('dialog'); await dialog.waitFor();
    assert.equal(await dialog.locator('input[type=password]').count(),7);
    await dialog.getByLabel('Xiaomi MiMo API key',{exact:true}).fill('offline-mimo-key');
    await dialog.getByLabel('OpenAI API key',{exact:true}).fill('offline-luna-key');
    await dialog.getByRole('button',{name:'Save keys securely'}).click();
    await dialog.getByText('Saved securely. You can now check access or begin research.').waitFor();
    for(const input of await dialog.locator('input[type=password]').all()) assert.equal(await input.inputValue(),'');
    assert.equal(await page.evaluate(()=>localStorage.length),0);
    await dialog.getByRole('button',{name:'Check connection',exact:true}).first().click();
    await dialog.getByText(/Key accepted and supported models/).waitFor(); assert.equal(checked,1);
    await page.screenshot({path:path.join(shots,'provider-settings.png'),fullPage:true,animations:'disabled'});
    console.log('Verified preview and provider setup');
    // Native dialog keyboard containment and Escape restoration.
    for(let i=0;i<30;i++) { await page.keyboard.press('Tab'); assert.equal(await page.evaluate(()=>document.querySelector('dialog').contains(document.activeElement)),true, `Tab ${i}: ${await page.evaluate(()=>document.activeElement.outerHTML.slice(0,200))}`); }
    await page.keyboard.press('Escape'); await page.getByRole('dialog').waitFor({state:'hidden'}); assert.equal(await page.getByRole('dialog').count(),0);
    console.log('Verified keyboard dialog');
    await page.getByRole('button',{name:'Research',exact:true}).click();
    await page.getByLabel('Your research question',{exact:true}).fill('Can greener streets make cities cooler?');
    await page.getByRole('button',{name:'Both sides',exact:true}).click();
    await page.getByLabel('Model budget limit').selectOption('0.50');
    await page.getByRole('checkbox').check();
    await page.screenshot({path:path.join(shots,'composer.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Begin research',exact:true}).click();
    await page.getByRole('button',{name:'Cancel run',exact:true}).waitFor();
    assert.equal(started.model_profile,'standard-2026-09'); assert.equal(started.max_cost_usd,'0.50'); assert.equal(started.challenge_enabled,true);
    await page.screenshot({path:path.join(shots,'research-active.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Cancel run',exact:true}).click();
    await page.getByText('No brief was released.',{exact:true}).waitFor();
    await page.screenshot({path:path.join(shots,'research-cancelled.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await page.getByText('No brief was released.',{exact:true}).waitFor();
    run='released';
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await page.getByRole('button',{name:'Copy brief',exact:false}).click();
    assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/validated example finding/);
    const downloadEvent=page.waitForEvent('download'); await page.getByRole('button',{name:'Download brief'}).click();
    const download=await downloadEvent; assert.match(fs.readFileSync(await download.path(),'utf8'),/validated example finding/);
    await page.screenshot({path:path.join(shots,'research-result.png'),fullPage:true,animations:'disabled'});
    detailed=true;
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await page.getByText('Illustrative supporting finding.',{exact:true}).waitFor();
    await page.locator('.evidence-card').first().locator('summary').click();
    await page.getByText('This is an exact illustrative quotation for the offline test.',{exact:true}).first().waitFor();
    assert.equal(await page.locator('.evidence-card.support').count(),1);
    assert.equal(await page.locator('.evidence-card.challenge').count(),1);
    assert.equal(await page.getByText('internal-gap-example',{exact:true}).count(),0);
    await page.screenshot({path:path.join(shots,'research-evidence.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Settings',exact:true}).click();
    await page.getByRole('dialog').getByRole('switch',{name:'arXiv',exact:true}).click();
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:/Provider setup/}).click();
    await page.getByRole('dialog').getByRole('button',{name:'Remove key',exact:true}).first().click();
    await page.getByText('Key removed.',{exact:true}).waitFor(); assert.equal(removed,1);
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Home',exact:true}).click();
    await page.locator('.welcome-view').waitFor();
    for (const width of [1440,1280,1024,800,480]) {
      await page.setViewportSize({width,height:width>=1024?768:800});
      await page.screenshot({path:path.join(shots,`home-${width}.png`),fullPage:true,animations:'disabled'});
      if(width>=1024) assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight),`Desktop home vertical overflow at ${width}: ${await page.evaluate(()=>document.documentElement.scrollHeight)}`);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Horizontal overflow at ${width}`);
      await page.getByRole('button',{name:/Provider setup/}).click();
      await page.getByRole('dialog').getByRole('button',{name:'Save keys securely'}).scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(shots,`settings-${width}.png`),animations:'disabled'});
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: automatic offline preview/recovery, hover/focus pause, static reduced motion, desktop viewport fit, 7 transient password fields, save/check/remove, profile/direction/budget, startup/progress/cancellation, history, copy/export, keyboard dialogs, reduced motion and resizing.');
  } finally { if(browser) await browser.close(); await new Promise(resolve=>server.close(resolve)); }
}
main().catch(e=>{console.error(e);process.exitCode=1});
