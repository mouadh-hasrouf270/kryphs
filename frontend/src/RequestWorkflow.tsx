import {DeliverableTeam} from './DeliverableTeam'
import {useState} from 'react'
import {Link,useNavigate,useParams} from 'react-router-dom'
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query'
import {api,post,label,ApiError,type Item,type Page,type Schema,type User} from './api'
import {useI18n} from './i18n'
import {ActionForm,Badge,Empty,ErrorBox,Loading,Modal,RecordForm,ResourceList} from './components'

type Props={workspace:string;schema:Schema;user:User;can:(key:string)=>boolean}
type Values=Record<string,unknown>
function useOptions(resource:string,workspace:string,brand?:string){return useQuery({queryKey:['choices',resource,workspace,brand],queryFn:async()=>{
 const results:Item[]=[];let page=1
 for(;;){const data=await api<Page>(`${resource}/?page=${page}${brand?'&brand='+brand:''}`,workspace);results.push(...data.results);if(!data.next)break;page++}
 return results
}})}
const localDate=(v:unknown)=>{if(!v)return '';const d=new Date(String(v));return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}

export function RequestForm({workspace,can,initial,onDone}:{workspace:string;can:Props['can'];initial?:Item;onDone:(row?:Item)=>void}){
 const {t}=useI18n();const client=useQueryClient();const [values,setValues]=useState<Values>(initial?{...initial,due_date:localDate(initial.due_date)}:{title:'',brand:'',priority:'normal',platforms:[]})
 const [children,setChildren]=useState<Values[]>([]);const [key]=useState(()=>crypto.randomUUID());const [locked,setLocked]=useState(false)
 const brands=useOptions('brands',workspace),products=useOptions('products',workspace,String(values.brand||'')),campaigns=useOptions('campaigns',workspace,String(values.brand||'')),platforms=useOptions('platforms',workspace),users=useOptions('users',workspace)
 const set=(name:string,value:unknown)=>setValues(v=>({...v,[name]:value,...(name==='brand'?{product:null,campaign:null}:{})}))
 const mutation=useMutation({mutationFn:async()=>{
  const date=(v:unknown)=>v?new Date(String(v)).toISOString():null
  const body={...values,due_date:date(values.due_date),...(!initial?{deliverables:children.map(child=>({...child,due_date:date(child.due_date)}))}:{})}
  return api<Item>(`requests/${initial?initial.id+'/':''}`,workspace,{method:initial?'PATCH':'POST',headers:{'Idempotency-Key':key},body:JSON.stringify(body)})
 },onSuccess:row=>{void client.invalidateQueries();onDone(row)},onSettled:()=>setLocked(false)})
 const errors=mutation.error instanceof ApiError?mutation.error.fields:{}
 const field=(name:string,kind='text',options?:Item[],target=values,change=set)=> <label key={name}><span>{t(name)}</span>{options?<select aria-label={t(name)} required={name==='brand'} value={String(target[name]||'')} onChange={e=>change(name,e.target.value||null)} disabled={!!initial&&name==='brand'}><option value="">{t('select')}</option>{options.map(row=><option key={row.id} value={row.id}>{label(row)}</option>)}</select>:kind==='textarea'?<textarea aria-label={t(name)} value={String(target[name]||'')} onChange={e=>change(name,e.target.value)}/>:<input aria-label={t(name)} type={kind} required={name==='title'} min={name==='quantity'?1:0} value={String(target[name]??'')} onChange={e=>change(name,kind==='number'?Number(e.target.value):e.target.value)}/>} {!!errors[name]&&<small role="alert">{String(errors[name])}</small>}</label>
 return <form className="request-form" onSubmit={e=>{e.preventDefault();if(locked)return;setLocked(true);mutation.mutate()}}>
 <h3>{t('requestBasics')}</h3><div className="form-grid">
 {field('brand','text',brands.data||[])}{field('title')}{field('product','text',(products.data||[]).filter(r=>r.brand===values.brand))}{field('campaign','text',(campaigns.data||[]).filter(r=>r.brand===values.brand))}
 {field('objective','textarea')}{field('details','textarea')}
 <label><span>{t('priority')}</span><select aria-label={t('priority')} value={String(values.priority)} onChange={e=>set('priority',e.target.value)}>{['normal','high','urgent','low'].map(v=><option key={v} value={v}>{t(v)}</option>)}</select></label>
 {field('due_date','datetime-local')}{can('assign_editors')&&field('owner','text',users.data||[])}
 <fieldset className="full platform-choices"><legend>{t('platforms')}</legend>{platforms.data?.map(p=><label key={p.id}><input type="checkbox" checked={(values.platforms as string[]||[]).includes(p.id)} onChange={e=>set('platforms',e.target.checked?[...(values.platforms as string[]||[]),p.id]:(values.platforms as string[]).filter(id=>id!==p.id))}/>{label(p)}</label>)}</fieldset></div>
 {!initial&&<><div className="section-heading"><h3>{t('deliverables')}</h3><button type="button" className="button secondary" onClick={()=>setChildren([...children,{title:'',creative_type:'video',quantity:1,aspect_ratio:'9:16',duration_target:0}])}>{t('addDeliverable')}</button></div>{children.map((child,index)=>{
 const change=(name:string,value:unknown)=>setChildren(rows=>rows.map((row,i)=>i===index?{...row,[name]:value}:row))
 return <fieldset className="deliverable-input" key={index}><legend>{t('deliverable')} {index+1}</legend><div className="form-grid">{field('title','text',undefined,child,change)}<label><span>{t('creative_type')}</span><select aria-label={t('creative_type')} value={String(child.creative_type)} onChange={e=>change('creative_type',e.target.value)}>{['video','image','audio','document'].map(v=><option key={v} value={v}>{t(v)}</option>)}</select></label>{field('platform','text',platforms.data||[],child,change)}{field('aspect_ratio','text',undefined,child,change)}{field('quantity','number',undefined,child,change)}{field('duration_target','number',undefined,child,change)}{field('hook','textarea',undefined,child,change)}{field('script','textarea',undefined,child,change)}{field('requirements','textarea',undefined,child,change)}{field('notes','textarea',undefined,child,change)}{field('due_date','datetime-local',undefined,child,change)}{can('assign_editors')&&field('assigned_editor','text',users.data||[],child,change)}</div><button type="button" className="text-button" onClick={()=>setChildren(rows=>rows.filter((_,i)=>i!==index))}>{t('removeDeliverable')}</button></fieldset>
 })}</>}
 {[brands,products,campaigns,platforms,users].find(q=>q.error)?.error&&<ErrorBox error={[brands,products,campaigns,platforms,users].find(q=>q.error)?.error}/>}
 {mutation.error&&<ErrorBox error={mutation.error}/>}<footer className="form-footer"><button type="button" className="button secondary" onClick={()=>onDone()}>{t('cancel')}</button><button className="button primary" disabled={locked||mutation.isPending}>{t('save')}</button></footer></form>
}

export function RequestsPage({workspace,schema,can}:Props){
 const {t}=useI18n();const navigate=useNavigate();const [create,setCreate]=useState(false)
 return <><div className="page-header"><div><h1>{t('requests')}</h1><p>{t('requestCaption')}</p></div>{can('create_requests')&&<button className="button primary" onClick={()=>setCreate(true)}>{t('create')}</button>}</div><ResourceList resource="requests" workspace={workspace} schema={{...schema,requests:{...schema.requests,can_create:false}}} onOpen={row=>navigate('/requests/'+row.id)}/>{create&&<Modal title={t('create')+' · '+t('request')} close={()=>setCreate(false)}><RequestForm workspace={workspace} can={can} onDone={row=>{setCreate(false);if(row)navigate('/requests/'+row.id)}}/></Modal>}</>
}

export function RequestPage({workspace,schema,can,user}:Props){
 const {id}=useParams();const {t,lang}=useI18n();const navigate=useNavigate();const client=useQueryClient();const [edit,setEdit]=useState(false);const [childEdit,setChildEdit]=useState<Item|null|undefined>();const [operation,setOperation]=useState<{resource:string;id:string;op:string}|null>(null)
 const query=useQuery({queryKey:['request',workspace,id],queryFn:()=>api<Item>(`requests/${id}/`,workspace)})
 const deliverables=useOptions('deliverables',workspace);const creatives=useOptions('creatives',workspace);const users=useOptions('users',workspace);const brands=useOptions('brands',workspace);const products=useOptions('products',workspace);const campaigns=useOptions('campaigns',workspace);const platforms=useOptions('platforms',workspace)
 const create=useMutation({mutationFn:(child:Item)=>post<Item>(`deliverables/${child.id}/actions/create-creative/`,workspace,{}),onSuccess:row=>{void client.invalidateQueries();navigate('/creatives/'+row.id)}})
 if(query.isPending)return <Loading/>;if(query.error)return <ErrorBox error={query.error}/>
 const row=query.data;const children=(deliverables.data||[]).filter(d=>d.request===id);const linked=(creatives.data||[]).filter(c=>c.request===id)
 const lookup=(rows:Item[]|undefined,value:unknown)=>rows?.find(r=>r.id===value)?label(rows.find(r=>r.id===value)!):'—'
 const date=(value:unknown)=>value?new Intl.DateTimeFormat(lang,{dateStyle:'medium',timeStyle:'short'}).format(new Date(String(value))):'—'
 return <><Link className="breadcrumb" to="/requests">{t('requests')} / {String(row.code)}</Link><div className="page-header"><div><h1>{String(row.title)}</h1><p>{String(row.objective||'')}</p></div><Badge value={row.status}/></div><section className="panel"><div className="detail-grid">{[['requester',lookup(users.data,row.requester)],['brand',lookup(brands.data,row.brand)],['product',lookup(products.data,row.product)],['campaign',lookup(campaigns.data,row.campaign)],['platforms',(row.platforms as string[]).map(p=>lookup(platforms.data,p)).join(', ')||'—'],['priority',t(String(row.priority))],['due_date',date(row.due_date)]].map(([key,value])=><div key={key}><dt>{t(key)}</dt><dd>{value}</dd></div>)}</div><p className="prose">{String(row.details||'')}</p><div className="action-row">{can('assign_editors')&&<button className="button secondary" onClick={()=>setOperation({resource:'requests',id:id!,op:'assign'})}>{t('assign')}</button>}{can('create_requests')&&<button className="button secondary" onClick={()=>setEdit(true)}>{t('edit')}</button>}</div></section>
 <div className="section-heading"><h2>{t('deliverables')}</h2>{can('create_requests')&&<button className="button secondary" onClick={()=>setChildEdit(null)}>{t('addDeliverable')}</button>}<span>{children.filter(d=>['approved','published'].includes(String(d.status))).length} / {children.length} {t('approved')}</span></div>{deliverables.error&&<ErrorBox error={deliverables.error}/>} {create.error&&<ErrorBox error={create.error}/>}
 {children.map(child=>{const items=linked.filter(c=>c.deliverable===child.id&&!c.archived_at);const approved=items.filter(c=>['approved','published'].includes(String(c.status))).length;return <section className="panel deliverable-card" key={child.id}><div className="section-heading"><h3>{String(child.title)}</h3><Badge value={child.status}/></div><p>{t(String(child.creative_type))} · {String(child.aspect_ratio)} · {lookup(users.data,child.assigned_editor)} · {date(child.due_date)}</p><p>{items.length} / {String(child.quantity)} {t('creativesCreated')} · {approved} / {String(child.quantity)} {t('approved')}</p><progress max={Number(child.quantity)} value={Math.min(approved,Number(child.quantity))}/><div className="deliverable-brief">{['hook','script','requirements','notes'].map(key=><div key={key}><h4>{t(key)}</h4><p className="prose">{String(child[key]||'\u2014')}</p></div>)}</div><p>{t('platform')}: {lookup(platforms.data,child.platform)} / {t('duration_target')}: {String(child.duration_target||0)}</p><DeliverableTeam workspace={workspace} deliverable={child} canManage={can('create_requests')&&row.requester===user.id} canAssignEditor={can('assign_editors')}/><div className="action-row">{can('create_requests')&&<button className="button secondary" onClick={()=>setChildEdit(child)}>{t('edit')}</button>}{can('edit_creatives')&&<button className="button primary" disabled={create.isPending} onClick={()=>create.mutate(child)}>{t('createCreative')}</button>}{can('submit_version')&&['assigned','changes_requested'].includes(String(child.status))&&<button className="button secondary" onClick={()=>setOperation({resource:'deliverables',id:child.id,op:'start-production'})}>{t('startProduction')}</button>}{can('assign_editors')&&<button className="button secondary" onClick={()=>setOperation({resource:'deliverables',id:child.id,op:'assign'})}>{t('assign')}</button>}</div>{items.map(c=><Link className="search-result" key={c.id} to={'/creatives/'+c.id}><span>{label(c)}</span><Badge value={c.status}/></Link>)}</section>})}
 {!children.length&&<ResourceList resource="creatives" workspace={workspace} schema={schema} filters={{request:id!,brand:String(row.brand)}} onOpen={c=>navigate('/creatives/'+c.id)}/>}
 <ResourceList resource="sources" workspace={workspace} schema={schema} filters={{request:id!,brand:String(row.brand)}}/>
 <ResourceList resource="activity" workspace={workspace} schema={schema} filters={{object_id:id!}}/>
 {childEdit!==undefined&&<Modal title={t('deliverable')} close={()=>setChildEdit(undefined)}><RecordForm resource="deliverables" workspace={workspace} schema={{...schema,deliverables:{...schema.deliverables,fields:(schema.deliverables?.fields||[]).filter(f=>!['brand','request','sequence'].includes(f.name)&&(can('assign_editors')||f.name!=='assigned_editor'))}}} initial={childEdit||undefined} defaults={{request:id,brand:row.brand}} onDone={()=>setChildEdit(undefined)}/></Modal>}
 {edit&&<Modal title={t('edit')} close={()=>setEdit(false)}><RequestForm workspace={workspace} can={can} initial={row} onDone={()=>setEdit(false)}/></Modal>}
 {operation&&<ActionForm title={t(operation.op==='assign'?'assign':'startProduction')} workspace={workspace} fields={operation.op==='assign'?[{name:'editor',related:'users',required:true}]:[]} onDone={()=>setOperation(null)} run={data=>post(`${operation.resource}/${operation.id}/actions/${operation.op}/`,workspace,data)}/>}
 </>
}

export function TasksPage({workspace}:{workspace:string}){
 const {t}=useI18n();const query=useQuery({queryKey:['tasks',workspace],queryFn:()=>api<Page>('tasks/',workspace)})
 return <><div className="page-header"><h1>{t('tasks')}</h1></div>{query.isPending?<Loading/>:query.error?<ErrorBox error={query.error}/>:!query.data.results.length?<Empty/>:<section className="panel">{query.data.results.map(row=><Link className="search-result" key={String(row.kind)+row.id} to={String(row.href)}><div><strong>{String(row.title)}</strong><p>{t(String(row.kind))} · {t(String(row.reason))}{row.overdue?' · '+t('overdue'):''}</p></div><Badge value={row.status}/></Link>)}</section>}</>
}
