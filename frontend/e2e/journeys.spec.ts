import {test,expect,type Page} from '@playwright/test'

async function login(page:Page,role='manager'){
 await page.goto('/');await page.locator('select.locale').selectOption('en')
 await page.getByLabel('Email',{exact:true}).fill(role+'@demo.local');await page.getByLabel('Password',{exact:true}).fill('CreativeDemo!2026');await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await expect(page.locator('.sidebar')).toBeVisible();await page.locator('select.locale').selectOption('en');await expect(page.getByRole('heading',{name:'Make room for great work.'})).toBeVisible()
}
async function call(page:Page,path:string,method='GET',data?:unknown){
 return page.evaluate(async({path,method,data})=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||'');const r=await fetch('/api/v1/'+path,{method,headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:data===undefined?undefined:JSON.stringify(data)});return {status:r.status,data:r.status===204?null:await r.json()}},{path,method,data})
}
test('complete request, deliverable tasks, revision, one creative per deliverable and parent approval',async({page})=>{
 test.setTimeout(180000)
 await login(page,'requester')
 const session=await call(page,'me/');const ws=session.data.workspaces[0].id;const suffix='?workspace='+ws
 const brands=await call(page,'brands/'+suffix);const brand=brands.data.results.find((b:{slug:string})=>b.slug==='noura').id
 const products=await call(page,'products/'+suffix+'&brand='+brand);const campaigns=await call(page,'campaigns/'+suffix+'&brand='+brand)
 await page.getByRole('link',{name:'Requests',exact:true}).click();await page.getByRole('button',{name:'Create',exact:true}).click()
 const title='Browser aggregate '+Date.now();const dialog=page.getByRole('dialog')
 await dialog.getByLabel('Title',{exact:true}).fill(title);await dialog.getByLabel('Brand',{exact:true}).selectOption(brand)
 if(products.data.results.length)await dialog.getByLabel('Product',{exact:true}).selectOption(products.data.results[0].id)
 if(campaigns.data.results.length)await dialog.getByLabel('Campaign',{exact:true}).selectOption(campaigns.data.results[0].id)
 await dialog.getByLabel('Priority',{exact:true}).selectOption('high');await dialog.getByLabel('Due date',{exact:true}).fill('2027-01-01T12:00')
 await dialog.getByLabel('Meta',{exact:true}).check();await dialog.getByLabel('TikTok',{exact:true}).check()
 for(let i=1;i<=2;i++){await dialog.getByRole('button',{name:'Add deliverable',exact:true}).click();const child=dialog.locator('.deliverable-input').nth(i-1);await child.getByLabel('Title',{exact:true}).fill('Deliverable '+i)}
 await dialog.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible()
 const requests=await call(page,'requests/'+suffix+'&q='+encodeURIComponent(title));const request=requests.data.results[0];expect(request.platforms).toHaveLength(2)
 const children=(await call(page,'deliverables/'+suffix+'&request='+request.id)).data.results.sort((a:{sequence:number},b:{sequence:number})=>a.sequence-b.sequence);expect(children).toHaveLength(2)
 await call(page,'auth/session/','DELETE');await login(page,'manager')
 const users=await call(page,'users/'+suffix);const editor=users.data.results.find((u:{email:string})=>u.email==='editor@demo.local')
 expect((await call(page,`requests/${request.id}/actions/assign/`+suffix,'POST',{editor:editor.id})).status).toBe(200)
 await call(page,'auth/session/','DELETE');await login(page,'editor');await page.goto('/tasks');await expect(page.getByRole('link').filter({hasText:'Deliverable 1'}).first()).toBeVisible()
 expect((await call(page,'creatives/'+suffix,'POST',{title:'Bypass forbidden',brand,request:request.id})).status).toBe(400)
 await page.goto('/requests/'+request.id);const card=page.locator('.deliverable-card').filter({has:page.getByRole('heading',{name:'Deliverable 1',exact:true})})
 await card.getByRole('button',{name:'Start production',exact:true}).click();await page.getByRole('button',{name:'Confirm action',exact:true}).click()
 await card.getByRole('button',{name:'Create creative',exact:true}).click();await expect(page).toHaveURL(/creatives\//)
 const id=page.url().split('/').pop()!
 expect((await call(page,`creatives/${id}/`+suffix)).data.deliverable).toBe(children[0].id)
 await page.getByRole('button',{name:'New version',exact:true}).click();await page.getByLabel('Notes',{exact:true}).fill('Initial browser version');await page.getByRole('button',{name:'Confirm action',exact:true}).click()
 await page.getByRole('button',{name:'Files',exact:true}).click();await page.getByRole('button',{name:'Upload asset',exact:true}).click()
 await page.getByLabel('Choose a file').setInputFiles({name:'master.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAC0lEQVR4nGNgQAYAAA4AAamRc7EAAAAASUVORK5CYII=','base64')})
 await page.getByRole('dialog').getByRole('button',{name:'Upload asset',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0)
 await page.getByRole('button',{name:'Submit for review',exact:true}).click();await page.getByRole('button',{name:'Confirm action',exact:true}).click()
 await call(page,'auth/session/','DELETE');await login(page,'reviewer');await page.goto('/tasks');await expect(page.getByRole('link').filter({hasText:'Deliverable 1'}).first()).toBeVisible();await page.goto('/creatives/'+id)
 await page.getByRole('button',{name:'Request changes',exact:true}).click();await page.getByLabel('Feedback',{exact:true}).fill('Change the opening hook');await page.getByRole('button',{name:'Confirm action',exact:true}).click()
 await call(page,'auth/session/','DELETE');await login(page,'editor');await page.goto('/tasks');await expect(page.getByText('Changes requested',{exact:true}).first()).toBeVisible()
 expect((await call(page,`creatives/${id}/actions/new-version/`+suffix,'POST',{notes:'Revised hook'})).status).toBe(201)
 expect((await call(page,`creatives/${id}/actions/submit/`+suffix,'POST',{})).status).toBe(200)
 const others:string[]=[]
 for(let i=0;i<1;i++){const made=await call(page,`deliverables/${children[1].id}/actions/create-creative/`+suffix,'POST',{title:'Second deliverable creative '+i});expect(made.status).toBe(201);others.push(made.data.id);await call(page,`creatives/${made.data.id}/actions/new-version/`+suffix,'POST',{});await call(page,`creatives/${made.data.id}/actions/submit/`+suffix,'POST',{})}
 await call(page,'auth/session/','DELETE');await login(page,'reviewer');await page.goto('/creatives/'+id)
 await page.getByRole('button',{name:'Approve',exact:true}).click();await page.getByRole('button',{name:'Confirm action',exact:true}).click();await expect(page.locator('.page-header').getByText('Approved',{exact:true})).toBeVisible()
 expect((await call(page,`requests/${request.id}/`+suffix)).data.status).not.toBe('approved')
 for(const other of others){expect((await call(page,`creatives/${other}/actions/approve/`+suffix,'POST',{})).status).toBe(200)}
 expect((await call(page,`requests/${request.id}/`+suffix)).data.status).toBe('approved')
 expect((await call(page,'versions/'+suffix+'&creative='+id)).data.results).toHaveLength(2)
 expect((await call(page,'notifications/'+suffix)).data.results.length).toBeGreaterThan(0)
})

test('RTL mobile navigation has no horizontal overflow',async({page})=>{
 await login(page);await page.setViewportSize({width:390,height:844});await page.getByLabel('Language',{exact:true}).selectOption('ar')
 await expect(page.locator('html')).toHaveAttribute('dir','rtl')
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
 await page.getByRole('button',{name:'\u0627\u0644\u0642\u0627\u0626\u0645\u0629',exact:true}).click();await page.getByRole('link',{name:'مكتبة الإبداعات',exact:true}).click()
 await expect(page.getByRole('heading',{name:'مكتبة الإبداعات',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
 await expect(page.locator('.creative-card').first()).toBeVisible();await page.screenshot({path:'test-results/mobile-rtl.png',fullPage:true})
})
test('viewer cannot mutate; manager dashboard and library persist',async({page})=>{
 await login(page,'viewer');const me=await call(page,'me/');const ws=me.data.workspaces[0].id
 const r=await call(page,'requests/?workspace='+ws,'POST',{title:'Forbidden'});expect(r.status).toBe(403)
 await page.getByRole('link',{name:'Creative library',exact:true}).click();await expect(page.locator('.creative-card').first()).toBeVisible();await expect(page.getByRole('button',{name:'Create Creative',exact:true})).toHaveCount(0)
 await call(page,'auth/session/','DELETE');await login(page,'manager');await page.screenshot({path:'test-results/overview-desktop.png',fullPage:true})
})

test('Arabic mobile creates a request with platforms and deliverables',async({page})=>{
 await login(page,'requester');await page.setViewportSize({width:390,height:844});await page.locator('select.locale').selectOption('ar');await page.goto('/requests')
 await page.getByRole('button',{name:'إنشاء',exact:true}).click();const dialog=page.getByRole('dialog');const title='طلب عربي '+Date.now()
 await dialog.getByLabel('العنوان',{exact:true}).fill(title);await dialog.getByLabel('العلامة التجارية',{exact:true}).selectOption({index:1})
 await dialog.getByLabel('Meta',{exact:true}).check();await dialog.getByLabel('TikTok',{exact:true}).check();await dialog.getByRole('button',{name:'إضافة مخرج',exact:true}).click()
 await dialog.locator('.deliverable-input').getByLabel('العنوان',{exact:true}).fill('فيديو عربي')
 await dialog.getByRole('button',{name:'حفظ',exact:true}).click();await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible()
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
 await page.screenshot({path:'test-results/request-mobile-ar.png',fullPage:true})
})
