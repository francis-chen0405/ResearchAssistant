"use strict";
// Offline UI acceptance. All application API requests are intercepted; no providers run.
const { chromium } = require('./acquisition/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

async function main() {
  const root = path.resolve(__dirname, '../frontend/out');
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
  const productionFixture = process.env.REPORT_REVIEW_FIXTURE ? JSON.parse(fs.readFileSync(process.env.REPORT_REVIEW_FIXTURE, "utf8")) : null;
  let productionReport = false;
  let browser;
  try {
    browser = await chromium.launch({headless:true});
    const context = await browser.newContext({viewport:{width:1280,height:860}, reducedMotion:'reduce', acceptDownloads:true, permissions:['clipboard-read','clipboard-write']});
    const page = await context.newPage();
    const errors = []; page.on('pageerror', e=>errors.push(e.message));
    async function openReportDetails() {
      await page.getByRole('heading', { name: 'Recommended Sources', exact: true }).waitFor();
      const sections = page.locator('.brief-disclosure, .brief-paper > .all-live-sources');
      for (const section of await sections.all()) {
        if (!await section.evaluate(node => node.open)) await section.locator(':scope > summary').click();
      }
    }

    let preferences = {modelProfile:'configurable-2026-09',stageModels:{planner:'gpt-6-luna-xhigh',scout:'gpt-6-luna-high',gap_analysis:'gpt-6-luna-xhigh',search_agent:'gpt-6-luna-xhigh',source_selection:'gpt-6-luna-xhigh',extractor:'gpt-6-luna-high',analyst:'gpt-6-luna-xhigh'},dbPath:'/example/history.sqlite3',maxTokens:500000,maxCost:'0.20',maxCalls:160,supportEnabled:true,challengeEnabled:false,sourceTarget:10,useSerpSearch:true,useExa:true,useOpenAlex:true,useArxiv:false,usePubmed:false,useCrossref:true};
    let serviceReady = false; let serviceProbes = 0; let serviceStarts = 0;
    let studyReviewed = false; let assessmentPersisted = false; let assessmentFresh = false;
    let saved = []; let run = null; let started = null; let checked = 0; let removed = 0; let detailed = false; let invalidPlan = false; let sufficientSourcePool = false; let invalidRelease = false; let evidenceFailure = false; let v2ResultRequests = 0; let v2EvidenceRequests = 0;
    const id='11111111-1111-4111-8111-111111111111';
    const progress = {status:'running',model_attempts:1,retrieval_attempts:2,usable_snapshots:1,candidates:1};
    const sourceLeadRequests=[];
    const sourceLeadPage=(offset,limit)=>{
      const all=Array.from({length:51},(_,index)=>({
        lead_id:`lead-${String(index+1).padStart(2,'0')}`,
        source_id:index===0?'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa':null,
        title:`Lead ${String(index+1).padStart(2,'0')} · Discovery example`,
        url:`https://example.org/lead-${index+1}`,
        work_id:null,
        readable_alternate_url:null,
        providers:['openalex'],
        search_directions:['support_search'],
        rounds:[1],
        capture_status:index===0?'failed':'unknown',
        disposition:index===0?'excluded':'pending',
        reason:index===0?'The source could not be captured; it remains a discovery lead.':'Recorded discovery candidate; capture not yet attempted.',
        confidence:'recorded',
        unknowns:[],
        history:index===0?[{stage:'source_capture',status:'failed',reason:'The capture worker reported a timeout.'}]:[],
        snippet:'SOURCE_LEAD_SNIPPET_MUST_NOT_RENDER',
        quote:'SOURCE_LEAD_QUOTE_MUST_NOT_RENDER',
      }));
      Object.assign(all[1],{
        url:'https://example.org/landing',
        capture_status:'unusable',
        readable_alternate_url:'https://mirror.example.org/fulltext',
        reason:'The linked landing page was unusable; a readable alternate was captured.',
        history:[
          {stage:'capture',status:'unusable',reason:'wigolo: https://example.org/landing'},
          {stage:'capture',status:'readable',reason:'wigolo: https://mirror.example.org/fulltext'},
        ],
      });
      all[50].url='https://example.org/lead-1#later';
      all[50].history=[{stage:'capture',status:'failed',reason:'A later discovery record.'}];
      all[2].readable_alternate_url='https://user:secret@example.org/fulltext';
      all[3].readable_alternate_url='javascript:alert(1)';
      const items=all.slice(offset,offset+limit);
      return {run_id:id,items,total:all.length,offset,limit,has_more:offset+items.length<all.length,notice:'Discovery leads are records of candidate sources.'};
    };
    const snapshot = () => ({run_id:id,db_path:preferences.dbPath,raw_claim:productionReport ? productionFixture.result.exact_claim : started.raw_claim,classification:run,stage:'discovery',current_research_round:1,progress_percent:25,message:run === 'cancelled' ? 'Cancelled; incomplete work is preserved.' : 'Finding sources for your question.',model_calls_used:1,retrieval_attempts_used:2,known_cost_subtotal_usd:'0.01',cost_usage_complete:false,conservative_reserved_cost_usd:'0.02',model_usage_details:{input_tokens:{total:null,known_subtotal:123,complete:false},output_tokens:{total:44,known_subtotal:44,complete:true},cached_input_tokens:{total:null,known_subtotal:0,complete:false},cache_write_tokens:{total:null,known_subtotal:4,complete:false},cost_basis_counts:[{basis:'published_cache_prices_reported_writes',physical_calls:1},{basis:'published_cache_prices_assumed_all_uncached_writes',physical_calls:1},{basis:null,physical_calls:1}]},supporting:{...progress,stance:'supporting'},opposing:{...progress,stance:'opposing'},validation_errors:[],research_controls:{research_mode:'balanced',sources_per_stance_per_round:10,discovery_providers:['arxiv']},final_brief:run === 'released' ? '# Research Brief\n\nA validated example finding.\n' : null,rendered_brief_hash:run === 'released' ? 'a'.repeat(64) : null,v2_diagnostics:detailed && run === 'released' ? {
      configured_providers:['arxiv'], logical_discovery_operations:6,
      physical_search_requests:10, seed_derived_candidates:0,
      diagnostic_messages:['Recorded diagnostic'], provider_outcomes:[],
    } : null});
    await page.route('**/api/**', async route => {
      const req=route.request(); const url=new URL(req.url()); const p=url.pathname; let body={}; let status=200;
      assert.equal(url.origin, `http://127.0.0.1:${server.address().port}`, 'Desktop API requests must use the exported app origin');
      if(p==='/api/preferences') { if(req.method()==='POST') preferences=req.postDataJSON(); body=preferences; }
      else if(p==='/api/model-options') body={choices:[['gpt-6-luna-high','GPT-6 Luna · High','openai','0.10','0.50'],['gpt-6-luna-xhigh','GPT-6 Luna · XHigh','openai','0.10','0.50'],['mimo-v2.6-pro','MiMo v2.6 Pro','mimo','0.435','0.87'],['mimo-v2.6-flash','MiMo v2.6 Flash','mimo','0.14','0.28'],['gpt-6-sol-high','GPT-6 Sol · High','openai','2.00','10.00'],['gpt-5.6-terra-high','GPT-5.6 Terra · High','openai','2.00','12.00']].map(([id,label,provider,input_per_million,output_per_million])=>({id,label,provider,input_per_million,output_per_million})),defaults:preferences.stageModels};
      else if(p==='/api/configuration/check') { assert.equal(req.method(),'POST'); const payload=req.postDataJSON(); assert.equal(payload.model_profile,'configurable-2026-09'); assert.equal(Object.keys(payload.stage_models).length,7); preferences.stageModels=payload.stage_models; const required=new Set(Object.values(payload.stage_models).map(choice=>choice.startsWith('mimo-')?'mimo':'openai')); body={configured:[...required].every(provider=>saved.includes(provider)),message:'Offline test configuration',default_db_path:preferences.dbPath,saved_credentials:saved,saved_settings:[],firecrawl_enabled:false,service:{wigolo_ready:serviceReady,state:serviceReady?'healthy':'unhealthy',message:'Offline local tools'}}; }
      else if(p==='/api/model-profiles') body=[{id:'configurable-2026-09',name:'Choose each research model',description:'Six supported choices for each active model step',pricing_reviewed:'2026-09-25',models:[{model:'gpt-6-luna-high',roles:'Any active model step',input_per_million:'0.25',output_per_million:'0.75',completion_limit:16384},{model:'mimo-v2.6-flash',roles:'Any active model step',input_per_million:'0.15',output_per_million:'0.30',completion_limit:16384}]}];
      else if(p==='/api/credentials') { const keys=req.postDataJSON(); assert.equal(keys.model_profile,'configurable-2026-09'); assert.deepEqual(Object.values(keys.stage_models),Array(7).fill('mimo-v2.6-flash')); assert.equal(keys.mimo_api_key,'offline-mimo-key'); assert.equal(keys.luna_api_key,undefined); saved=['mimo']; body={saved:true,message:'Saved',saved_settings:[]}; }
      else if(p.endsWith('/check')) { assert.equal(req.method(),'POST'); const payload=req.postDataJSON(); assert.equal(payload.model_profile,'configurable-2026-09'); assert.deepEqual(Object.values(payload.stage_models),Array(7).fill('mimo-v2.6-flash')); checked++; body={state:'connected',message:'Key accepted and selected model IDs listed. No text was generated.'}; }
      else if(p.endsWith('/remove')) { removed++; saved=saved.filter(s=>s!=='mimo'); body={removed:true}; }
      else if(p==='/api/service/start') { serviceStarts++; body={wigolo_ready:false,state:'starting',message:'Offline tools starting'}; }
      else if(p==='/api/service') { serviceReady=++serviceProbes>=2; body={wigolo_ready:serviceReady,state:serviceReady?'healthy':'starting',message:'Offline tools readiness'}; }
      else if(p==='/api/research/start') { assert.equal(serviceReady,true,'Research must wait for local tools health'); assert.equal(serviceStarts,1); assert.equal(serviceProbes,2); started=req.postDataJSON(); run='running'; body={started:true,run_id:id,classification:'starting',message:'Research started.'}; }
      else if(p.endsWith('/cancel')) { run='cancelled'; body={cancelled:true,message:'Cancellation requested.'}; }
      else if(p==='/api/history') body={items:run ? [{run_id:id,raw_claim:started.raw_claim,status:run,stage:'discovery',updated_at:'2026-09-07T12:00:00Z'}] : []};
      else if(p===`/api/research/${id}/source-leads`) {
        const offset=Number(url.searchParams.get('offset')||'0'); const limit=Number(url.searchParams.get('limit')||'0');
        assert.equal(req.method(),'GET','Source leads are a read-only request');
        assert.ok(limit>0 && limit<=50,`Source-lead page size must be at most 50: ${limit}`);
        sourceLeadRequests.push({method:req.method(),run,offset,limit});
        body=sourceLeadPage(offset,limit);
      }
      else if(p.endsWith('/v2-result')) {
        v2ResultRequests++;
        if(!detailed) { status=404; body={detail:'Historical brief'}; }
        else body={run_id:id,exact_claim:started.raw_claim,directions:{support_enabled:true,challenge_enabled:true},synthesis:{sections:[{section_type:'supporting',items:[{ledger_claim_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',approved_factual_statement:'Illustrative supporting finding.',admission_method:'analyzer_admitted'}]},{section_type:'opposing',items:[{ledger_claim_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',approved_factual_statement:'Illustrative challenging finding.',admission_method:'analyzer_admitted'}]}]},recommended_source_ids:['11111111-1111-4111-8111-111111111111'],recommended_sources:[{source_id:'11111111-1111-4111-8111-111111111111',source_url:'https://example.org/study',title:'Illustrative canopy study',source_type:'Research paper',publication_date:null,discovery_providers:['exa'],discovery_round:1,recommended:true,recommendation_rank:1,queue_rank:1,status:'recommended_analyzer_admitted',ledger_claim_ids:['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'],budget_prevented_reason:null}],all_surviving_sources:[{source_id:'11111111-1111-4111-8111-111111111111',source_url:'https://example.org/study',title:'Illustrative canopy study',source_type:'Research paper',publication_date:null,discovery_providers:['exa'],discovery_round:1,recommended:true,recommendation_rank:1,queue_rank:1,status:'recommended_analyzer_admitted',ledger_claim_ids:['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'],budget_prevented_reason:null},{source_id:'22222222-2222-4222-8222-222222222222',source_url:'https://example.org/review',title:'Illustrative climate review',source_type:'Review',publication_date:null,discovery_providers:['crossref'],discovery_round:2,recommended:false,recommendation_rank:null,queue_rank:null,status:'surviving_analyzer_admitted',ledger_claim_ids:['bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'],budget_prevented_reason:null}],unresolved_material_gaps:[{gap_id:'internal-gap-example',direction:'challenge',missing_evidence:'Long-term air temperature data is unavailable.'}],claim_coverage_map:[{dimension:'effect_or_association',claim_component:started.raw_claim,coverage_state:'partial',evidence_summary:'Direct evidence remains incomplete.'}],stopping:{reason:invalidPlan?'invalid_search_agent_plan':'budget_limit',explanation:invalidPlan?'Follow-up search stopped after two invalid plans. Results use sources already collected.':'Research stopped before all sources could be examined.'},release_validation:{valid:!invalidRelease,rendered_output_hash:'a'.repeat(64)}};
      }
      else if(p.endsWith('/v2-evidence')) { v2EvidenceRequests++; if(evidenceFailure) { status=503; body={detail:'Offline evidence failure'}; } else body={run_id:id,source_titles:[{source_id:'11111111-1111-4111-8111-111111111111',display_title:'Illustrative canopy study',captured_title:'Illustrative canopy study'},{source_id:'22222222-2222-4222-8222-222222222222',display_title:'Illustrative climate review',captured_title:'Illustrative climate review'},{source_id:'33333333-3333-4333-8333-333333333333',display_title:'Illustrative failed analysis',captured_title:'Illustrative failed analysis'},{source_id:'44444444-4444-4444-8444-444444444444',display_title:'Illustrative rejected analysis',captured_title:'Illustrative rejected analysis'},{source_id:'55555555-5555-4555-8555-555555555555',display_title:'PDF file: paper.pdf (example.org)',captured_title:'S2056608520000082jra 1..28'}],research_status:{reason_code:invalidPlan?'no_productive_search':'no_actionable_material_gap',explanation:invalidPlan?'Follow-up search stopped after two invalid plans; coverage may remain partial or unavailable.':'No actionable gap remained for another search round.',actionable_gap_count:0,partial_coverage_count:1,unavailable_coverage_count:1,source:'persisted_governor'},study_lineage:[{source_ids:['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'],basis:'matching_title',explanation:'These sources may report the same study; identity is unverified.'}],items:detailed ? ['support','challenge'].map((direction,index)=>({source_id:index===0?'11111111-1111-4111-8111-111111111111':'22222222-2222-4222-8222-222222222222',ledger_claim_id:index===0?'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',approved_factual_statement:index===0?'Illustrative supporting finding.':'Illustrative challenging finding.',title:direction==='support'?'Illustrative canopy study':'Illustrative climate review',source_url:'https://example.org/study',source_family:'family-raw-id-should-not-render',direction,recommendation_status:'Analyzed',relationship_to_claim:direction==='support'?'qualifies':'challenges',selection_rationale:'Relevant to the question',gap_ids:[],evidence_summary:'Source context is limited to the measured conditions.',supporting_proposition:direction==='support'?'Canopy cover was associated with cooling.':'Cooling varied with local conditions.',quote_passage:'This is an exact illustrative quotation for the offline test.',limitations:['Surface temperatures only; not a general estimate of air temperature.'],validation_status:'reviewer_approved',claim_fit:2})) : []}; }
      else if(p.endsWith('/trail')) body={run_id:id,items:[]};
      else if(p===`/api/research/${id}`) body=snapshot();
      else { status=404; body={detail:'Unknown mocked API'}; }
      if(p.endsWith('/v2-result') && detailed && body.release_validation) {
        body.all_surviving_sources[1].status='surviving_analyzer_admitted';
        body.all_surviving_sources.push({...body.all_surviving_sources[1],source_id:'33333333-3333-4333-8333-333333333333',source_url:'https://example.org/failed',title:'Illustrative failed analysis',recommended:false,status:'surviving_analyzer_failed',ledger_claim_ids:[]});
        body.all_surviving_sources.push({...body.all_surviving_sources[1],source_id:'44444444-4444-4444-8444-444444444444',source_url:'https://example.org/rejected',title:'Illustrative rejected analysis',recommended:false,status:'surviving_analyzer_rejected',ledger_claim_ids:[]});
        body.all_surviving_sources.push({...body.all_surviving_sources[1],source_id:'55555555-5555-4555-8555-555555555555',source_url:'https://example.org/paper.pdf',title:'S2056608520000082jra 1..28',recommended:false,status:'surviving_not_deeply_analyzed',ledger_claim_ids:[]});
        if(assessmentPersisted) body.post_analysis_assessment={run_id:id,policy_identity:'researchassistant-v2-post-analysis-evidence-v1',assessed_after_analysis:true,claim_established:false,admitted_source_ids:['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'],supporting_count:0,challenging_count:0,qualifying_count:2,unrelated_count:0,unadmitted_source_count:3,partial_coverage_count:1,unavailable_coverage_count:1,unresolved_gap_count:1,claim_support_observed:false,limitations:['No admitted finding was classified as supporting the claim. This does not establish that the claim is false.','3 selected source(s) produced no admitted evidence; selection is not evidence sufficiency.','Research coverage remains limited.']};
        if(assessmentFresh) body.post_analysis_assessment={run_id:id,policy_identity:'researchassistant-v2-post-analysis-evidence-v2',search_outcome:'incomplete_coverage',coverage_incomplete:true,assessed_after_analysis:true,claim_established:false,admitted_source_ids:['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'],supporting_count:0,challenging_count:0,qualifying_count:2,unrelated_count:0,unadmitted_source_count:3,partial_coverage_count:1,unavailable_coverage_count:1,unresolved_gap_count:1,claim_support_observed:false,limitations:['No admitted finding was classified as supporting the claim. This does not establish that the claim is false.','3 of 5 surviving sources produced no admitted evidence; surviving selection is not evidence sufficiency.','Research coverage remains limited.']};
      }
      if(p.endsWith('/v2-evidence') && sufficientSourcePool && !evidenceFailure) {
        body.research_status={reason_code:'sufficient_source_pool',explanation:'Further searches overlap with the existing source families and are unlikely to add useful evidence.',actionable_gap_count:1,partial_coverage_count:1,unavailable_coverage_count:0,source:'final_output'};
      }
      if(p.endsWith('/v2-evidence') && detailed && body.run_id) body.source_budget_outcomes=[{source_id:'33333333-3333-4333-8333-333333333333',outcome:'token_cap_blocked'}]; if(p.endsWith('/v2-evidence') && detailed && body.run_id) { body.post_analysis_assessment={run_id:id,policy_identity:assessmentFresh?'researchassistant-v2-post-analysis-evidence-v2':'researchassistant-v2-post-analysis-evidence-v1',...(assessmentFresh?{search_outcome:'incomplete_coverage',coverage_incomplete:true}:{}),assessed_after_analysis:true,claim_established:false,admitted_source_ids:body.items.map(item=>item.source_id),supporting_count:0,challenging_count:0,qualifying_count:2,unrelated_count:0,unadmitted_source_count:3,partial_coverage_count:1,unavailable_coverage_count:1,unresolved_gap_count:1,claim_support_observed:false,limitations:assessmentFresh?['No admitted finding was classified as supporting the claim. This does not establish that the claim is false.','3 of 5 surviving sources produced no admitted evidence; surviving selection is not evidence sufficiency.','Research coverage remains limited.']:['No admitted finding was classified as supporting the claim. This does not establish that the claim is false.','3 selected source(s) produced no admitted evidence; selection is not evidence sufficiency.','Research coverage remains limited.']}; body.shared_website_groups=[{host:'imy.se',source_ids:body.items.map(item=>item.source_id),explanation:'These 2 admitted pages share the imy.se website. A shared website alone does not establish independent corroboration. This does not show they are duplicates.'}]; body.items[0].source_type='randomized_trial'; body.items[0].verified_publication={doi:'10.1000/example',canonical_url:'https://doi.org/10.1000/example',title:'Illustrative canopy study',authors:['A. Researcher'],publication_date:'2024',venue:'Illustrative Journal',verification:'crossref_doi'}; body.items[1].source_type='observational_study'; body.items[1].quote_passage='The outcome was lower. However, only among'; body.items[0].source_context_notice='Legal scope has not been independently verified; check jurisdiction, dates and exceptions against primary sources. The all-50-states statement has not been independently verified; check whether its scope and conditions apply in each jurisdiction.'; body.items.forEach(item=>{item.relationship_to_claim='qualifies';}); }
      if (p.endsWith('/v2-evidence') && studyReviewed && body.items?.length) {
        body.study_opening=[{ledger_claim_id:body.items[0].ledger_claim_id,study_identifier:'REG-2024',role:'main',text:body.items[0].approved_factual_statement,design:'randomized',intervention:'canopy',outcome:'temperature'}, {ledger_claim_id:body.items[1].ledger_claim_id,study_identifier:'REG-2025',role:'limitation',text:body.items[1].limitations[0],design:'observational',intervention:'canopy',outcome:'temperature'}];
      }
      if (productionReport && p.endsWith('/v2-result')) body = productionFixture.result;
      if (productionReport && p.endsWith('/v2-evidence')) body = productionFixture.evidence;
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
    await page.getByRole('button',{name:'Explore the workspace',exact:true}).click();
    await page.getByText('Research models',{exact:true}).click();
    for (const stage of ['planner','scout','gap_analysis','search_agent','source_selection','extractor','analyst']) await page.locator(`#stage-model-${stage}`).selectOption('mimo-v2.6-flash');
    await page.getByRole('button',{name:'Connect providers',exact:true}).click();
    const dialog=page.getByRole('dialog'); await dialog.waitFor();
    assert.deepEqual(
      await dialog.locator('input[type=password]').evaluateAll(inputs =>
        inputs.map(input => input.labels[0].textContent.trim())),
      ['Xiaomi MiMo', 'OpenAI', 'SERP Search', 'Brave Search', 'Serper', 'Exa', 'OpenAlex', 'PubMed', 'Firecrawl']
        .map(provider => `${provider} API key`),
    );
    assert.match(await dialog.innerText(),/OpenAI[\s\S]*Optional until a research role uses a GPT model/);
    await dialog.getByLabel('Xiaomi MiMo API key',{exact:true}).fill('offline-mimo-key');
    await dialog.getByRole('button',{name:'Save keys securely'}).click();
    await dialog.getByText('Saved securely. You can now check access or begin research.').waitFor();
    for(const input of await dialog.locator('input[type=password]').all()) assert.equal(await input.inputValue(),'');
    assert.equal(await page.evaluate(()=>localStorage.length),0);
    await dialog.getByRole('button',{name:'Check connection',exact:true}).first().click();
    await dialog.getByText(/Key accepted and selected model IDs/).waitFor(); assert.equal(checked,1);
    await page.screenshot({path:path.join(shots,'provider-settings.png'),fullPage:true,animations:'disabled'});
    console.log('Verified preview and provider setup');
    // Native dialog keyboard containment and Escape restoration.
    for(let i=0;i<30;i++) { await page.keyboard.press('Tab'); assert.equal(await page.evaluate(()=>document.querySelector('dialog').contains(document.activeElement)),true, `Tab ${i}: ${await page.evaluate(()=>document.activeElement.outerHTML.slice(0,200))}`); }
    await page.keyboard.press('Escape'); await page.getByRole('dialog').waitFor({state:'hidden'}); assert.equal(await page.getByRole('dialog').count(),0);
    console.log('Verified keyboard dialog');
    await page.getByRole('button',{name:'Research',exact:true}).click();
    assert.equal(await page.getByText('A fresh line of inquiry',{exact:true}).count(),0);
    assert.equal(await page.getByText(/^Default: Luna/).count(),0);
    assert.equal(await page.getByText('Model profile',{exact:true}).count(),0);
    await page.getByLabel('Your research question',{exact:true}).fill('Can greener streets make cities cooler?');
    await page.getByRole('button',{name:'Both sides',exact:true}).click();
    await page.getByLabel('Model budget limit').selectOption('0.50');
    await page.screenshot({path:path.join(shots,'composer.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Begin research',exact:true}).click();
    await page.getByRole('button',{name:'Cancel run',exact:true}).waitFor();
    await page.getByText('Recorded token usage and cost basis',{exact:true}).click();
    await page.getByText('at least 123 known; total incomplete',{exact:true}).waitFor();
    await page.getByText('44',{exact:true}).waitFor();
    await page.getByText('unavailable; total incomplete',{exact:true}).waitFor();
    await page.getByText(/pricing basis not recorded/).waitFor();
    await page.getByText(/all uncached input assumed to incur cache-write charges/).waitFor();
    await page.getByText(/not an invoice/).waitFor();
    assert.equal(started.model_profile,'configurable-2026-09'); assert.deepEqual(Object.values(started.stage_models),Array(7).fill('mimo-v2.6-flash')); assert.equal(started.max_cost_usd,'0.50'); assert.equal(started.challenge_enabled,true);
    await page.screenshot({path:path.join(shots,'research-active.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Cancel run',exact:true}).click();
    await page.getByText('No brief was released.',{exact:true}).waitFor();
    await page.getByRole('button',{name:/Research trail/}).click();
    await page.locator('.trail-source-leads > summary').click();
    await page.locator('.source-lead').first().waitFor();
    assert.equal(await page.locator('.source-lead').count(),50,'An unreleased run shows the first bounded source-lead page');
    const firstLead=page.locator('.source-lead').first();
    await firstLead.getByRole('link',{name:'Lead 01 · Discovery example',exact:true}).waitFor();
    await firstLead.locator('.source-lead-reason').getByText(/recorded reason could not be translated/).waitFor();
    assert.equal(await firstLead.locator('details[open]').count(),0,'Lead history and metadata start collapsed');
    assert.equal(await page.getByText('SOURCE_LEAD_SNIPPET_MUST_NOT_RENDER',{exact:true}).count(),0);
    assert.equal(await page.getByText('SOURCE_LEAD_QUOTE_MUST_NOT_RENDER',{exact:true}).count(),0);
    await firstLead.locator('.source-lead-details > summary').click();
    await firstLead.getByText(/recorded reason could not be translated/).first().waitFor();
    const landingLead=page.locator('.source-lead').nth(1);
    assert.equal((await landingLead.locator('.source-lead-status').innerText()).toLowerCase(),'linked page: unusable','The badge describes the linked page, not a readable alternate');
    assert.equal(await landingLead.getByRole('link',{name:'Lead 02 · Discovery example',exact:true}).getAttribute('href'),'https://example.org/landing');
    const readableAlternate=landingLead.getByRole('link',{name:'Readable alternate',exact:true});
    assert.equal(await readableAlternate.getAttribute('href'),'https://mirror.example.org/fulltext','The readable capture has its own visible alternate link');
    assert.equal(await readableAlternate.getAttribute('rel'),'noopener noreferrer');
    assert.equal(await landingLead.locator('details[open]').count(),0,'The alternate link is visible before expanding history');
    await landingLead.locator('.source-lead-details > summary').click();
    await landingLead.getByText('Technical details',{exact:true}).click();
    await landingLead.getByText(/wigolo: https:\/\/example.org\/landing/).waitFor();
    for(const index of [2,3]) assert.equal(await page.locator('.source-lead').nth(index).getByRole('link',{name:'Readable alternate',exact:true}).count(),0,'Unsafe alternate protocols and embedded credentials must not become links');
    await page.getByRole('button',{name:'Load more source leads'}).click();
    await page.getByText('51 of 51 discovery records loaded · 50 unique pages or unlinked records',{exact:true}).waitFor();
    assert.equal(await page.locator('.source-lead').count(),50,'A duplicate on the next page is grouped with its earlier record');
    await firstLead.getByText(/1 additional discovery record/).waitFor();
    assert.deepEqual(sourceLeadRequests.filter(request=>request.run==='cancelled').map(({method,offset,limit})=>({method,offset,limit})),[
      {method:'GET',offset:0,limit:50},
      {method:'GET',offset:50,limit:50},
    ]);
    await page.screenshot({path:path.join(shots,'research-cancelled.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('dialog').getByRole('button',{name:'Close'}).click();
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    run='failed'; v2ResultRequests=0; v2EvidenceRequests=0;
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await page.getByText('No brief was released.',{exact:true}).waitFor();
    await page.waitForTimeout(100);
    assert.equal(v2ResultRequests,0,'Failed runs do not request v2 result details');
    assert.equal(v2EvidenceRequests,0,'Failed runs do not request v2 evidence details');
    assert.equal(await page.getByText(/validated brief remains available/i).count(),0,'Failed runs do not claim a brief is available');
    run='released';
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await page.getByRole('button',{name:/Research trail/}).click();
    await page.locator('.trail-source-leads > summary').click();
    await page.locator('.source-lead').first().waitFor();
    assert.equal(await page.locator('.source-lead').count(),50,'Released run loads source leads independently of the brief');
    assert.ok(sourceLeadRequests.some(request=>request.run==='released' && request.method==='GET' && request.offset===0 && request.limit===50),'The released run requests its first lead page');
    assert.ok(sourceLeadRequests.every(request=>request.method==='GET' && request.limit<=50),'Every source-lead request is a bounded GET');
    await page.getByRole('dialog').getByRole('button',{name:'Close'}).click();
    await page.getByRole('button',{name:'Copy brief',exact:false}).click();
    assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/validated example finding/);
    const downloadEvent=page.waitForEvent('download'); await page.getByRole('button',{name:'Download brief'}).click();
    const download=await downloadEvent; assert.match(fs.readFileSync(await download.path(),'utf8'),/validated example finding/);
    await page.screenshot({path:path.join(shots,'research-result.png'),fullPage:true,animations:'disabled'});
    detailed=true;
    evidenceFailure=true;
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await page.locator('.overview-item').getByText('Illustrative supporting finding.',{exact:true}).waitFor();
    await page.getByText(/Detailed evidence could not be loaded/i).waitFor();
    await page.locator('.overview-item').getByText('Illustrative supporting finding.',{exact:true}).waitFor();
    assert.equal(await page.getByText('No brief was released.',{exact:true}).count(),0,'Evidence failure keeps the validated brief visible');
    evidenceFailure=false;
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await page.getByRole('heading', { name: 'Overview', exact: true }).waitFor();
    for (const section of await page.locator('.brief-disclosure').all()) {
      assert.equal(await section.evaluate(node => node.open), false, 'Secondary sections start collapsed');
    }
    const sourceBrowser = page.locator('.brief-paper > .all-live-sources');
    assert.equal(await sourceBrowser.evaluate(node => node.open), false, 'All sources starts collapsed after recommendations');
    await page.screenshot({path:path.join(shots,'research-compact.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'View admitted quote and source'}).first().click();
    assert.equal(await page.locator('.brief-evidence').evaluate(node => node.open), true, 'Evidence link opens its collapsed parent');
    await openReportDetails();
    assert.equal(await page.locator('.evidence-card').first().evaluate(node=>node.open),true,'Brief findings open the exact admitted Ledger record');
    await page.locator('.evidence-card').first().getByText('Assessment relationship Adds a qualification',{exact:false}).waitFor();
    await page.getByText('Claim status · Claim not established by the admitted evidence',{exact:true}).waitFor();
    await page.getByText('This is an additional assessment of saved evidence. The saved brief is unchanged; new copies and exports may include a reading aid.',{exact:true}).waitFor();
    await page.getByText(/2 qualifying/).waitFor();
    await page.locator('summary').getByText('Shared publisher/website',{exact:true}).waitFor();
    assert.ok(await page.getByText(/does not establish independent corroboration/i).count() >= 1,'Shared website pages are not presented as independent corroboration');
    await page.getByText(/all-50-states statement has not been independently verified/i).waitFor();
    await page.getByText(/separate links do not establish independent studies/i).waitFor();
    assert.equal(await page.getByText('Recommended · evidence admitted',{exact:false}).count(),1,'Recommended source is shown only once');
    await page.getByText('Recommended outcomes: 1 evidence admitted',{exact:true}).waitFor();
    await page.getByText('Outcomes among all 5 surviving sources: 2 evidence admitted, 1 source token limit prevented analysis, 1 evidence not admitted, 1 not assessed',{exact:true}).waitFor();
    await page.getByText('Survived selection · source token limit prevented analysis',{exact:false}).waitFor();
    await page.locator('summary').getByText('Source lineage',{exact:true}).waitFor();
    assert.equal(await page.getByText(/0 Reviewer-approved/).count(),0,'Fresh analyzer-admission runs do not imply an active Reviewer with zero approvals');
    assert.equal(await page.getByText('family-raw-id-should-not-render',{exact:true}).count(),0,'Internal family identifiers are not shown in ordinary cards');
    await page.locator('blockquote').getByText('This is an exact illustrative quotation for the offline test.',{exact:false}).first().waitFor();
    await page.getByRole('link',{name:'10.1000/example',exact:true}).waitFor();
    await page.locator('.evidence-card').nth(1).locator('summary').first().focus();
    await page.keyboard.press('Enter');
    await page.locator('.evidence-card').nth(1).getByText(/recorded passage may be incomplete/i).waitFor();
    await page.locator('.evidence-card').nth(1).getByText('Recorded passage and context').click();
    await page.locator('.evidence-card').nth(1).getByText('The outcome was lower. However, only among',{exact:true}).waitFor();
    assert.equal(await page.locator('.evidence-card.support').count(),1);
    assert.equal(await page.locator('.evidence-card.challenge').count(),1);
    assert.equal(await page.getByText('internal-gap-example',{exact:true}).count(),0);
    await page.getByRole('heading',{name:'Unresolved evidence gaps',exact:true}).waitFor();
    await page.getByText('1 gap remains unresolved.',{exact:true}).waitFor();
    await page.getByText(/^Earlier search decision ·/).click();
    await page.getByText(/The search assessment counted 0 unresolved evidence gaps for possible follow-up/).waitFor();
    await page.getByText(/Release checks passed: yes\./).waitFor();
    const sidebar = page.locator('.report-meta');
    await sidebar.getByText('Input tokens',{exact:true}).waitFor();
    await sidebar.getByText('at least 123 known; total incomplete',{exact:true}).waitFor();
    assert.equal(await sidebar.getByText(/Recorded token usage and cost basis|Frozen research settings|Research notes|The saved research result is available/).count(),0);
    const discovery = sidebar.locator('details').filter({hasText:'Discovery counts'});
    assert.equal(await discovery.evaluate(node => node.open),false);
    await discovery.locator('summary').click();
    await discovery.getByText('Physical provider requests/pages',{exact:true}).waitFor();
    await discovery.getByText('0',{exact:true}).waitFor();
    await discovery.locator('summary').click();
    assert.equal(await discovery.evaluate(node => node.open),false);
    assert.doesNotMatch(await page.locator('[aria-labelledby="brief-overview-heading"]').innerText(), /Research coverage was incomplete|Support-directed research only/);
    await page.screenshot({path:path.join(shots,'research-evidence.png'),fullPage:true,animations:'disabled'});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),true,'Result fits narrow viewport without horizontal overflow');
    await page.locator('.result-bottom-line > summary').waitFor();
    await page.screenshot({path:path.join(shots,'research-evidence-narrow.png'),fullPage:true,animations:'disabled'});
    await page.setViewportSize({width:1280,height:860});
    await page.getByRole('heading',{name:'Latest research coverage assessment',exact:true}).waitFor();
    await page.getByText('Direct evidence remains incomplete.',{exact:true}).waitFor();
    invalidPlan=true;
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await openReportDetails();
    await page.getByText(/^Earlier search decision ·/).click();
    await page.getByText('Technical search record',{exact:true}).click();
    await page.locator('.result-limitation').getByText(/Follow-up search stopped after two invalid plans/).waitFor();
    await page.getByText('Long-term air temperature data is unavailable.',{exact:false}).waitFor();
    await page.screenshot({path:path.join(shots,'adaptive-search-limitations.png'),fullPage:true,animations:'disabled'});
    invalidPlan=false; sufficientSourcePool=true;
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await openReportDetails();
    await page.getByText(/Earlier search decision · Search stopped after the source pool was considered sufficient/).waitFor();
    await page.getByText(/^Earlier search decision ·/).click();
    await page.getByText('Technical search record',{exact:true}).click();
    await page.locator('.result-limitation').getByText(/Further searches overlap with the existing source families/).waitFor();
    await page.locator('.result-limitation').getByText(/counted 1 unresolved evidence gap for possible follow-up/).waitFor();
    sufficientSourcePool=false;
    assessmentPersisted=true;
    await page.getByRole('button',{name:'Home',exact:true}).click();
    await page.locator('.welcome-view').waitFor();
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await openReportDetails();
    await page.getByText('Supplemental post-analysis status from saved evidence. The saved brief is unchanged; new copies and exports may include a reading aid.',{exact:true}).waitFor();
    await page.getByText('This assessment is included in the saved brief and export.',{exact:true}).waitFor();
    await page.getByText('Among 5 surviving sources, 3 had no admitted evidence and 2 had admitted evidence.',{exact:true}).waitFor();
    await page.getByRole('heading',{name:'Context and evidence qualifications',exact:true}).waitFor();
    await page.locator('.evidence-card').first().locator('summary').first().click();
    await page.locator('.evidence-card').first().getByText('Limited relevance',{exact:true}).waitFor();
    await page.locator('.evidence-card').first().getByText('Claim Fit 2/5',{exact:false}).waitFor();
    const pdfSource = page.locator('.source-card').filter({has:page.getByRole('link',{name:'Source page at Example',exact:true})});
    await pdfSource.getByRole('link',{name:'Source page at Example',exact:true}).waitFor();
    await pdfSource.getByText('Captured title and provenance',{exact:true}).click();
    await pdfSource.getByText('Original captured title S2056608520000082jra 1..28',{exact:true}).waitFor();
    assessmentPersisted=false; assessmentFresh=true;
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await openReportDetails();
    await page.getByText('Post-analysis research status · Incomplete coverage',{exact:true}).waitFor();
    await page.getByText('This post-analysis status is included in the saved brief and export.',{exact:true}).waitFor();
    assert.equal(await page.getByText('Supplemental post-analysis status from saved evidence. The saved brief is unchanged; new copies and exports may include a reading aid.',{exact:true}).count(),0);
    assessmentFresh=false;
    assessmentPersisted=false;
    studyReviewed=true;
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await openReportDetails();
    await page.locator('.result-bottom-line').getByText('Surface temperatures only; not a general estimate of air temperature.',{exact:false}).waitFor();
    assert.equal(await page.locator('.result-bottom-line').getByText(/not necessarily representative/).count(),0);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth),true);
    await page.screenshot({path:path.join(shots,'reviewed-opening-narrow.png'),fullPage:true,animations:'disabled'});
    await page.setViewportSize({width:1280,height:860});
    await page.screenshot({path:path.join(shots,'reviewed-opening-desktop.png'),fullPage:true,animations:'disabled'});
    studyReviewed=false;
    if (productionFixture) {
      productionReport=true;
      await page.getByRole('button',{name:'Saved research',exact:true}).click();
      await page.getByRole('button',{name:/Can greener streets/}).click();
      await openReportDetails();
      const opening = page.locator('.result-bottom-line');
      await opening.getByText(/randomized study REG-2024/).waitFor();
      await opening.getByText(/observational study REG-2025/).waitFor();
      await opening.getByText(/Recorded limitations/).waitFor();
      assert.equal(await opening.getByText(/not necessarily representative/).count(), 0);
      assert.equal(await page.locator('.evidence-card').count(), 3);
      await opening.getByRole('button',{name:'View evidence and source'}).first().click();
      assert.equal(await page.locator('.evidence-card[open]').count(),1);
      await page.getByRole('link',{name:'Canonical publication',exact:true}).first().waitFor();
      for (const width of [1280,390]) {
        await page.setViewportSize({width,height:844});
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth),true);
        await page.screenshot({path:path.join(shots,`production-report-${width}.png`),fullPage:true,animations:'disabled'});
      }
      const [download] = await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Download brief'}).click()]);
      assert.equal(fs.readFileSync(await download.path(),'utf8'),productionFixture.evidence.reading_aid_markdown);
      await page.setViewportSize({width:1280,height:860});
      productionReport=false;
    }
    invalidRelease=true; v2ResultRequests=0; v2EvidenceRequests=0;
    await page.getByRole('button',{name:'Saved research',exact:true}).click();
    await page.getByRole('button',{name:/Can greener streets/}).click();
    await page.getByText('A validated example finding.',{exact:true}).waitFor();
    await page.waitForTimeout(100);
    assert.equal(v2ResultRequests,1,'Released runs validate the stored v2 result before loading evidence');
    assert.equal(v2EvidenceRequests,0,'Evidence is not requested for an invalid v2 release');
    assert.equal(await page.getByText(/Detailed evidence could not be loaded/i).count(),0,'Invalid releases do not show the evidence retry warning');
    await page.getByRole('button',{name:'Settings',exact:true}).click();
    await page.getByRole('dialog').locator('summary').filter({hasText:'Search providers'}).click();
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
    console.log('PASS: automatic offline preview/recovery, hover/focus pause, static reduced motion, desktop viewport fit, 9 transient password fields, save/check/remove, profile/direction/budget, startup/progress/cancellation, history, copy/export, keyboard dialogs, reduced motion and resizing.');
  } finally { if(browser) await browser.close(); await new Promise(resolve=>server.close(resolve)); }
}
main().catch(e=>{console.error(e);process.exitCode=1});
