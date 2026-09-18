import {test,expect,type Page} from '@playwright/test'

async function call(page:Page,path:string,method='GET',data?:unknown){return page.evaluate(async({path,method,data})=>{
 const token=decodeURIComponent(document.cookie.split('; ').find(v=>v.startsWith('csrftoken='))?.split('=')[1]||'')
 const response=await fetch('/api/v1/'+path,{method,headers:{'Content-Type':'application/json','X-CSRFToken':token},body:data===undefined?undefined:JSON.stringify(data)})
 return {status:response.status,data:response.status===204?null:await response.json()}
},{path,method,data})}
async function login(page:Page,role:string){await page.goto('/');await call(page,'auth/session/');await call(page,'auth/session/','DELETE');const response=await call(page,'auth/session/','POST',{email:role+'@demo.local',password:'CreativeDemo!2026'});expect(response.status).toBe(200);await page.reload();await page.locator('select.locale').selectOption('en');return response.data}

test('existing request adds production brief, multi-role team, scoped access and historical masters',async({page})=>{
 test.setTimeout(180000)
 const user=await login(page,'manager');const ws=user.workspaces[0].id;const suffix='?workspace='+ws
 const brand=(await call(page,'brands/'+suffix)).data.results.find((b:{slug:string})=>b.slug==='noura').id
 const people=(await call(page,'users/'+suffix)).data.results
 const editor=people.find((u:{email:string})=>u.email==='editor@demo.local');const filming=people.find((u:{email:string})=>u.email==='viewer@demo.local')
 const title='Focused workflow '+Date.now()
 await page.goto('/requests');await page.getByRole('button',{name:'Create',exact:true}).click()
 let dialog=page.getByRole('dialog');await dialog.getByLabel('Title',{exact:true}).fill(title);await dialog.getByLabel('Brand',{exact:true}).selectOption(brand)
 await dialog.getByRole('button',{name:'Add deliverable',exact:true}).click();await dialog.locator('.deliverable-input').getByLabel('Title',{exact:true}).fill('Inline brief')
 await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('heading',{name:title})).toBeVisible()
 const requestId=page.url().split('/').pop()!
 await page.getByRole('button',{name:'Add deliverable',exact:true}).click();dialog=page.getByRole('dialog')
 await expect(dialog.getByLabel('Sequence',{exact:true})).toHaveCount(0)
 await dialog.getByLabel('Title',{exact:false}).fill('Production brief')
 for(const [key,value] of [['Hook','Opening hook'],['Script','A complete script'],['Requirements','Vertical output'],['Notes','Brand tone']])await dialog.getByLabel(key,{exact:false}).fill(value)
 await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toHaveCount(0)
 const card=page.locator('.deliverable-card').filter({has:page.getByRole('heading',{name:'Production brief',exact:true})})
 await expect(card).toContainText('Opening hook');await expect(card).toContainText('A complete script')
 for(const [person,role,notes] of [[editor.id,'editor','Edit the vertical cut'],[filming.id,'filming_responsible','Film outdoors Saturday']]){
  await card.getByRole('button',{name:'Add assignment',exact:true}).click();dialog=page.getByRole('dialog')
  await dialog.getByLabel('Person',{exact:true}).selectOption(person);await dialog.getByLabel('Responsibility',{exact:true}).selectOption(role);await dialog.getByLabel('Notes',{exact:true}).fill(notes);await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(dialog).toHaveCount(0)
 }
 await expect(card.locator('.team-assignment')).toHaveCount(2);await expect(card).toContainText('Editor — Editor');await expect(card).toContainText('Viewer — Filming responsible');await expect(card).toContainText('Film outdoors Saturday')
 await login(page,'viewer');await page.goto('/requests');await expect(page.getByRole('button',{name:title,exact:true})).toBeVisible();await page.goto('/tasks');await expect(page.locator('a[href="/requests/'+requestId+'"]').filter({hasText:'Production brief'})).toBeVisible()
 await login(page,'media_buyer');await page.goto('/requests');await expect(page.getByRole('button',{name:title,exact:true})).toHaveCount(0);expect((await call(page,`requests/${requestId}/`+suffix)).status).toBe(404)
 await login(page,'reviewer');expect((await call(page,`requests/${requestId}/`+suffix)).status).toBe(200)
 await login(page,'editor');await page.goto('/requests');await expect(page.getByRole('button',{name:title,exact:true})).toBeVisible();await page.goto('/requests/'+requestId)
 await page.locator('.deliverable-card').filter({has:page.getByRole('heading',{name:'Production brief',exact:true})}).getByRole('button',{name:'Create creative',exact:true}).click();await expect(page).toHaveURL(/creatives\//)
 const creative=page.url().split('/').pop()!
 const upload=async(filename:string)=>{
  await page.getByRole('button',{name:'Files',exact:true}).click();await expect(page.getByRole('button',{name:'Create',exact:true})).toHaveCount(0)
  await page.getByRole('button',{name:'Upload asset',exact:true}).click()
  // Signature fixture: upload/history acceptance does not claim video decoding.
  await page.getByLabel('Choose a file').setInputFiles({name:filename,mimeType:'video/mp4',buffer:Buffer.concat([Buffer.from([0,0,0,24]),Buffer.from('ftypmp42'),Buffer.alloc(30)])})
  await page.getByRole('dialog').getByRole('button',{name:'Upload asset',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0)
 }
 expect((await call(page,`creatives/${creative}/actions/new-version/`+suffix,'POST',{})).status).toBe(201);await page.reload();await upload('master-v1.mp4')
 expect((await call(page,`creatives/${creative}/actions/submit/`+suffix,'POST',{})).status).toBe(200)
 await login(page,'reviewer');expect((await call(page,`creatives/${creative}/actions/request-changes/`+suffix,'POST',{feedback:'New opening'})).status).toBe(200)
 await login(page,'editor');expect((await call(page,`creatives/${creative}/actions/new-version/`+suffix,'POST',{})).status).toBe(201);await page.goto('/creatives/'+creative);await upload('master-v2.mp4')
 await expect(page.locator('.file-history')).toContainText('master-v1.mp4');await expect(page.locator('.file-history')).toContainText('master-v2.mp4');await expect(page.locator('.version-file-group')).toHaveCount(2)
 expect((await call(page,`creatives/${creative}/actions/submit/`+suffix,'POST',{})).status).toBe(200);await login(page,'reviewer');expect((await call(page,`creatives/${creative}/actions/approve/`+suffix,'POST',{})).status).toBe(200)
 await page.goto('/creatives/'+creative);await page.getByRole('button',{name:'Files',exact:true}).click();await expect(page.locator('.file-history')).toContainText('master-v1.mp4');await expect(page.locator('.file-history')).toContainText('master-v2.mp4')
 await page.screenshot({path:'test-results/file-history-desktop.png',fullPage:true})
 await page.setViewportSize({width:390,height:844});await page.locator('select.locale').selectOption('ar')
 await expect(page.locator('.file-history')).toContainText('master-v1.mp4');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
 await page.screenshot({path:'test-results/file-history-mobile-ar.png',fullPage:true})
})

test('Arabic mobile adds a deliverable and filming assignment to an existing request',async({page})=>{
 await login(page,'manager');const me=await call(page,'me/');const ws=me.data.workspaces[0].id;const suffix='?workspace='+ws
 const brand=(await call(page,'brands/'+suffix)).data.results.find((b:{slug:string})=>b.slug==='noura').id
 const made=await call(page,'requests/'+suffix,'POST',{title:'طلب فريق عربي '+Date.now(),brand})
 expect(made.status).toBe(201)
 await page.setViewportSize({width:390,height:844});await page.locator('select.locale').selectOption('ar');await page.goto('/requests/'+made.data.id)
 await page.getByRole('button',{name:'إضافة مخرج',exact:true}).click();let dialog=page.getByRole('dialog')
 await dialog.getByLabel('العنوان',{exact:false}).fill('إنتاج عربي');await dialog.getByLabel('السيناريو',{exact:false}).fill('نص التصوير');await dialog.getByRole('button',{name:'حفظ',exact:true}).click();await expect(dialog).toHaveCount(0)
 await page.getByRole('button',{name:'إضافة تكليف',exact:true}).click();dialog=page.getByRole('dialog');await dialog.getByLabel('الشخص',{exact:true}).selectOption({index:1});await dialog.getByLabel('المسؤولية',{exact:true}).selectOption('filming_responsible');await dialog.getByLabel('ملاحظات',{exact:true}).fill('التصوير يوم السبت');await dialog.getByRole('button',{name:'حفظ',exact:true}).click();await expect(dialog).toHaveCount(0)
 await expect(page.locator('.deliverable-team')).toContainText('مسؤول التصوير');await expect(page.locator('.deliverable-team')).toContainText('التصوير يوم السبت')
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:'test-results/production-team-mobile-ar.png',fullPage:true})
})
