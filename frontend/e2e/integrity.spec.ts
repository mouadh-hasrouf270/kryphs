import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'

const python=process.platform==='win32'?'../backend/.venv/Scripts/python.exe':'../backend/.venv/bin/python'
const fixture=(...args:string[])=>JSON.parse(execFileSync(python,['../backend/tests/drive_browser_fixture.py',...args],{encoding:'utf8'}))
async function call(page:Page,path:string,method='GET',data?:unknown){return page.evaluate(async({path,method,data})=>{
 const token=decodeURIComponent(document.cookie.split('; ').find(v=>v.startsWith('csrftoken='))?.split('=')[1]||'')
 const response=await fetch('/api/v1/'+path,{method,headers:{'Content-Type':'application/json','X-CSRFToken':token},body:data===undefined?undefined:JSON.stringify(data)})
 return {status:response.status,data:response.status===204?null:await response.json()}
},{path,method,data})}
async function login(page:Page,role:string){await page.goto('/');await call(page,'auth/session/');await call(page,'auth/session/','DELETE');const response=await call(page,'auth/session/','POST',{email:role+'@demo.local',password:'CreativeDemo!2026'});expect(response.status).toBe(200);await page.reload();await page.locator('select.locale').selectOption('en');return response.data}

test('assignment integrity, one creative, deduplicated tasks and automatic Drive worker',async({page})=>{
 test.setTimeout(240000)
 const destination=fixture('--seed');const me=await login(page,'manager');const ws=me.workspaces.find((w:{name:string})=>w.name==='Olive Studio').id;const suffix='?workspace='+ws
 const people=(await call(page,'users/'+suffix)).data.results;const editor=people.find((p:{email:string})=>p.email==='editor@demo.local')
 const made=await call(page,'requests/'+suffix,'POST',{title:'Integrity '+Date.now(),brand:destination.brand,deliverables:[{title:'Execution A'},{title:'Execution B'}]});expect(made.status).toBe(201)
 const request=made.data;const children=(await call(page,'deliverables/'+suffix+'&request='+request.id)).data.results.sort((a:{sequence:number},b:{sequence:number})=>a.sequence-b.sequence)
 const assign=async(d:{id:string})=>expect((await call(page,`deliverables/${d.id}/actions/assign/`+suffix,'POST',{editor:editor.id})).status).toBe(200)
 await assign(children[0]);expect((await call(page,`requests/${request.id}/`+suffix)).data.status).toBe('new')
 await assign(children[1]);expect((await call(page,`requests/${request.id}/`+suffix)).data.status).toBe('assigned')
 await page.goto('/requests/'+request.id)
 const second=page.locator('.deliverable-card').filter({has:page.getByRole('heading',{name:'Execution B',exact:true})})
 await second.getByRole('button',{name:'Remove assignment',exact:true}).click()
 await expect(second.getByText('New',{exact:true})).toBeVisible();await expect(second.getByRole('button',{name:'Start production',exact:true})).toBeDisabled()
 expect((await call(page,`deliverables/${children[1].id}/actions/start-production/`+suffix,'POST',{})).status).toBe(400)
 expect((await call(page,`requests/${request.id}/`+suffix)).data.status).toBe('new')
 await assign(children[1]);expect((await call(page,`deliverables/${children[1].id}/actions/start-production/`+suffix,'POST',{})).status).toBe(200)
 expect((await call(page,'deliverable-assignments/'+suffix,'POST',{deliverable:children[1].id,user:editor.id,role:'filming_responsible',notes:'Film and edit'})).status).toBe(201)
 await login(page,'editor');const tasks=(await call(page,'tasks/'+suffix)).data.results
 expect(tasks.filter((t:{kind:string;id:string})=>t.kind==='deliverable'&&t.id===children[1].id)).toHaveLength(1)
 await page.goto('/requests/'+request.id);await second.getByRole('button',{name:'Create creative',exact:true}).click();await expect(page).toHaveURL(/creatives\//)
 const creative=page.url().split('/').pop()!
 expect((await call(page,`deliverables/${children[1].id}/actions/create-creative/`+suffix,'POST',{})).status).toBe(400)
 await page.goto('/requests/'+request.id);await expect(second.getByRole('link',{name:'Open creative',exact:true})).toBeVisible();await expect(second.getByRole('button',{name:'Create creative',exact:true})).toHaveCount(0)
 const remoteFiles:{id:string;name:string;parents:string[]}[]=[]
 for(const version of [1,2]){
  expect((await call(page,`creatives/${creative}/actions/new-version/`+suffix,'POST',{})).status).toBe(201)
  await page.goto('/creatives/'+creative);await page.getByRole('button',{name:'Files',exact:true}).click();await page.getByRole('button',{name:'Upload asset',exact:true}).click()
  await page.getByLabel('Choose a file').setInputFiles({name:`master-v${version}.mp4`,mimeType:'video/mp4',buffer:Buffer.concat([Buffer.from([0,0,0,24]),Buffer.from('ftypmp42'),Buffer.alloc(30)])})
  await page.getByRole('dialog').getByRole('button',{name:'Upload asset',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('Google Drive upload queued')
  const uploads=(await call(page,'storage/uploads/'+suffix+'&connection='+destination.connection)).data.results
  expect(uploads).toHaveLength(version)
  const worked=fixture('--run-upload',uploads[0].id);expect(worked.status).toBe('complete')
  const file=worked.remote.find((f:{name:string})=>f.name.includes(`master-master-v${version}-`));expect(file).toBeTruthy();remoteFiles.push(file)
  expect(worked.remote.some((f:{name:string})=>/^WS-|^BR-|^CR-/.test(f.name))).toBeFalsy()
  await page.reload();await page.getByRole('button',{name:'Files',exact:true}).click();await expect(page.locator('.file-history')).toContainText('Complete')
  if(version===1){expect((await call(page,`creatives/${creative}/actions/submit/`+suffix,'POST',{})).status).toBe(200);await login(page,'reviewer');expect((await call(page,`creatives/${creative}/actions/request-changes/`+suffix,'POST',{feedback:'Second cut'})).status).toBe(200);await login(page,'editor')}
 }
 expect(remoteFiles[0].id).not.toBe(remoteFiles[1].id);expect(remoteFiles[0].parents).not.toEqual(remoteFiles[1].parents)
 await expect(page.locator('.file-history')).toContainText('master-v1.mp4');await expect(page.locator('.file-history')).toContainText('master-v2.mp4')
 await page.setViewportSize({width:390,height:844});await page.locator('select.locale').selectOption('ar');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
 await page.screenshot({path:'test-results/automatic-drive-mobile-ar.png',fullPage:true})
})
