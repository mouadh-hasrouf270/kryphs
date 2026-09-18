import {test,expect,type Page} from '@playwright/test'
async function call(page:Page,path:string,method='GET',data?:unknown){return page.evaluate(async({path,method,data})=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||'');const r=await fetch('/api/v1/'+path,{method,headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:data===undefined?undefined:JSON.stringify(data)});return {status:r.status,data:r.status===204?null:await r.json()}},{path,method,data})}
test('cross-workspace and restricted-brand reads are rejected in browser sessions',async({page})=>{
 await page.goto('/');await page.locator('select.locale').selectOption('en');expect((await call(page,'auth/session/','POST',{email:'admin@demo.local',password:'CreativeDemo!2026'})).status).toBe(200)
 const me=await call(page,'me/');const ws=me.data.workspaces[0].id;const original=await call(page,'brands/?workspace='+ws);const allowed=original.data.results.find((b:{slug:string})=>b.slug==='noura')
 const stamp=Date.now();const second=await call(page,'workspaces/','POST',{name:'Browser isolation '+stamp,slug:'browser-isolation-'+stamp});expect(second.status).toBe(201)
 const hidden=await call(page,'brands/?workspace='+ws,'POST',{name:'Restricted browser brand '+stamp,slug:'restricted-'+stamp});expect(hidden.status).toBe(201)
 expect((await call(page,`workspaces/${ws}/members/`,'POST',{email:'viewer@demo.local',role:'viewer',brand_restricted:true,brands:[allowed.id]})).status).toBe(201)
 await call(page,'auth/session/','DELETE');await call(page,'auth/session/','POST',{email:'viewer@demo.local',password:'CreativeDemo!2026'})
 expect((await call(page,'creatives/?workspace='+second.data.id)).status).toBe(403)
 expect((await call(page,`brands/${hidden.data.id}/?workspace=${ws}`)).status).toBe(404)
 expect((await call(page,'brands/?workspace='+ws,'POST',{name:'Forbidden',slug:'forbidden'})).status).toBe(403)
 const visible=await call(page,'brands/?workspace='+ws);expect(visible.data.results.every((b:{id:string})=>b.id===allowed.id)).toBeTruthy()
})
