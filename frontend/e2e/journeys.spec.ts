import {test,expect,type Page} from '@playwright/test'

async function login(page:Page,role='manager'){
 await page.goto('/');await page.locator('select.locale').selectOption('en')
 await page.getByLabel('Email',{exact:true}).fill(role+'@demo.local');await page.getByLabel('Password',{exact:true}).fill('CreativeDemo!2026');await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await expect(page.locator('.sidebar')).toBeVisible();await page.locator('select.locale').selectOption('en');await expect(page.getByRole('heading',{name:'Make room for great work.'})).toBeVisible()
}
async function call(page:Page,path:string,method='GET',data?:unknown){
 return page.evaluate(async({path,method,data})=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||'');const r=await fetch('/api/v1/'+path,{method,headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:data===undefined?undefined:JSON.stringify(data)});return {status:r.status,data:r.status===204?null:await r.json()}},{path,method,data})
}
test('request, two deliverables, revision and approval with persisted activity',async({page})=>{
 await login(page,'requester')
 const session=await call(page,'me/');const ws=session.data.workspaces[0].id;const suffix='?workspace='+ws
 const brands=await call(page,'brands/'+suffix);const brand=brands.data.results[0].id
 await page.getByRole('link',{name:'Requests',exact:true}).click();await page.getByRole('button',{name:'Create',exact:true}).click()
 const title='Browser request '+Date.now();await page.getByLabel('Title',{exact:false}).fill(title);await page.getByLabel('Brand',{exact:true}).selectOption(brand);await page.getByLabel('Priority',{exact:true}).selectOption('normal');await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('button',{name:title,exact:true})).toBeVisible()
 const requests=await call(page,'requests/'+suffix+'&q='+encodeURIComponent(title));const request=requests.data.results[0]
 for(let i=1;i<=2;i++){const r=await call(page,'deliverables/'+suffix,'POST',{request:request.id,brand,title:'Deliverable '+i,sequence:i,creative_type:'video'});expect(r.status).toBe(201)}
 await call(page,'auth/session/','DELETE');await login(page,'manager')
 const users=await call(page,'users/'+suffix);const editor=users.data.results.find((u:{email:string})=>u.email==='editor@demo.local')
 const assigned=await call(page,`requests/${request.id}/actions/assign/`+suffix,'POST',{editor:editor.id});expect(assigned.status).toBe(200)
 await call(page,'auth/session/','DELETE');await login(page,'editor')
 const made=await call(page,'creatives/'+suffix,'POST',{title:'Browser creative '+Date.now(),brand,request:request.id,creative_type:'video'});expect(made.status).toBe(201)
 const id=made.data.id
 await page.goto('/creatives/'+id);await page.getByLabel('Language',{exact:true}).selectOption('en')
 await page.getByRole('button',{name:'New version',exact:true}).click();await page.getByLabel('Notes',{exact:true}).fill('Initial browser version');await page.getByRole('button',{name:'Confirm action',exact:true}).click();await expect(page.getByRole('button',{name:'Submit for review',exact:true})).toBeVisible();await page.getByRole('button',{name:'Submit for review',exact:true}).click();await page.getByRole('button',{name:'Confirm action',exact:true}).click()
 await call(page,'auth/session/','DELETE');await login(page,'reviewer');await page.goto('/creatives/'+id)
 await page.getByRole('button',{name:'Request changes',exact:true}).click();await page.getByLabel('Feedback',{exact:true}).fill('Change the opening hook');await page.getByRole('button',{name:'Confirm action',exact:true}).click()
 await call(page,'auth/session/','DELETE');await login(page,'editor')
 expect((await call(page,`creatives/${id}/actions/new-version/`+suffix,'POST',{notes:'Revised hook'})).status).toBe(201)
 expect((await call(page,`creatives/${id}/actions/submit/`+suffix,'POST',{})).status).toBe(200)
 await call(page,'auth/session/','DELETE');await login(page,'reviewer');await page.goto('/creatives/'+id)
 await page.getByRole('button',{name:'Approve',exact:true}).click();await page.getByRole('button',{name:'Confirm action',exact:true}).click();await expect(page.locator('.page-header').getByText('Approved',{exact:true})).toBeVisible()
 const versions=await call(page,'versions/'+suffix+'&creative='+id);expect(versions.data.results).toHaveLength(2)
 const notifications=await call(page,'notifications/'+suffix);expect(notifications.data.results.length).toBeGreaterThan(0)
})
test('RTL mobile navigation has no horizontal overflow',async({page})=>{
 await login(page);await page.setViewportSize({width:390,height:844});await page.getByLabel('Language',{exact:true}).selectOption('ar')
 await expect(page.locator('html')).toHaveAttribute('dir','rtl')
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
 await page.getByRole('button',{name:'Menu',exact:true}).click();await page.getByRole('link',{name:'مكتبة الإبداعات',exact:true}).click()
 await expect(page.getByRole('heading',{name:'مكتبة الإبداعات',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
 await expect(page.locator('.creative-card').first()).toBeVisible();await page.screenshot({path:'test-results/mobile-rtl.png',fullPage:true})
})
test('viewer cannot mutate; manager dashboard and library persist',async({page})=>{
 await login(page,'viewer');const me=await call(page,'me/');const ws=me.data.workspaces[0].id
 const r=await call(page,'requests/?workspace='+ws,'POST',{title:'Forbidden'});expect(r.status).toBe(403)
 await page.getByRole('link',{name:'Creative library',exact:true}).click();await expect(page.locator('.creative-card').first()).toBeVisible();await expect(page.getByRole('button',{name:'Create Creative',exact:true})).toHaveCount(0)
 await call(page,'auth/session/','DELETE');await login(page,'manager');await page.screenshot({path:'test-results/overview-desktop.png',fullPage:true})
})


