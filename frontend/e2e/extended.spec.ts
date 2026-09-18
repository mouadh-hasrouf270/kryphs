import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'
async function login(page:Page,role='manager'){
 await page.goto('/');await page.locator('select.locale').selectOption('en')
 await page.getByLabel('Email',{exact:true}).fill(role+'@demo.local');await page.getByLabel('Password',{exact:true}).fill('CreativeDemo!2026');await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await expect(page.locator('.sidebar')).toBeVisible();await page.locator('select.locale').selectOption('en')
}
async function call(page:Page,path:string,method='GET',data?:unknown){
 return page.evaluate(async({path,method,data})=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||'');const r=await fetch('/api/v1/'+path,{method,headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:data===undefined?undefined:JSON.stringify(data)});return {status:r.status,data:r.status===204?null:await r.json()}},{path,method,data})
}
test('Drive development fixture retains identity through rename and move',async({page})=>{
 const python='../backend/.venv/Scripts/python.exe';const script='../backend/tests/seed_drive_fixture.py'
 const original=execFileSync(python,[script],{encoding:'utf8'}).trim()
 await login(page);const me=await call(page,'me/');const ws=me.data.workspaces[0].id
 const before=await call(page,`storage/objects/${original}/?workspace=${ws}`);expect(before.data.filename).toBe('Original fixture.png')
 const renamed=execFileSync(python,[script,'--rename'],{encoding:'utf8'}).trim();expect(renamed).toBe(original)
 const after=await call(page,`storage/objects/${original}/?workspace=${ws}`);expect(after.data.external_id).toBe(before.data.external_id);expect(after.data.parents).toEqual(['fixture-folder-b'])
 await page.goto('/integrations');await page.getByRole('button',{name:'Assets',exact:true}).click();await expect(page.getByRole('button',{name:'Renamed fixture.png',exact:true})).toBeVisible()
})
test('media buyer stores historical performance and records an outcome',async({page})=>{
 await login(page,'media_buyer');const me=await call(page,'me/');const ws=me.data.workspaces[0].id;const suffix='?workspace='+ws
 const library=await call(page,'creatives/'+suffix+'&status=approved');const c=library.data.results.find((item:{approved_version:string})=>!!item.approved_version)
 const deployment=await call(page,'deployments/'+suffix,'POST',{title:'Browser manual deployment '+Date.now(),brand:c.brand,creative:c.id,version:c.approved_version,provider:'manual',state:'active'});expect(deployment.status).toBe(201)
 const day=Date.now();for(let i=0;i<2;i++){const r=await call(page,'performance/'+suffix,'POST',{brand:c.brand,deployment:deployment.data.id,interval_start:new Date(day-(3-i)*86400000).toISOString(),interval_end:new Date(day-(2-i)*86400000).toISOString(),spend:100,impressions:1000,clicks:i?20:40,conversions:5,revenue:250});expect(r.status).toBe(201)}
 expect((await call(page,`creatives/${c.id}/actions/outcome/`+suffix,'POST',{outcome:'refresh_requested',reason:'CTR declined in comparable daily windows.'})).status).toBe(200)
 await page.goto('/performance');await expect(page.getByRole('heading',{name:'Evidence',exact:true})).toBeVisible();await expect(page.locator('table').first()).toContainText(c.title)
})
test('experiment binds a variant and records a qualified learning',async({page})=>{
 await login(page);const me=await call(page,'me/');const ws=me.data.workspaces[0].id;const suffix='?workspace='+ws;const library=await call(page,'creatives/'+suffix);const c=library.data.results[0]
 const variant=await call(page,`creatives/${c.id}/actions/related/`+suffix,'POST',{title:'Browser variant '+Date.now(),relationship:'variant',hypothesis:'A new opening hook'});expect(variant.status).toBe(200)
 const experiment=await call(page,'experiments/'+suffix,'POST',{brand:c.brand,title:'Browser experiment '+Date.now(),hypothesis:'Product-first opening increases CTR',primary_kpi:'ctr'});expect(experiment.status).toBe(201)
 for(const [creative,control] of [[c,true],[variant.data,false]] as const){const arm=await call(page,'experiment-arms/'+suffix,'POST',{brand:c.brand,experiment:experiment.data.id,creative:creative.id,name:control?'Control':'Variant',control});expect(arm.status).toBe(201)}
 expect((await call(page,`experiments/${experiment.data.id}/actions/start/`+suffix,'POST',{})).status).toBe(200)
 expect((await call(page,`experiments/${experiment.data.id}/actions/complete/`+suffix,'POST',{learning:'Promising association; limited sample, no causal conclusion.',limitations:'Small non-randomized sample'})).status).toBe(200)
 await page.goto('/experiments');await expect(page.getByRole('button',{name:experiment.data.title,exact:true})).toBeVisible()
})
