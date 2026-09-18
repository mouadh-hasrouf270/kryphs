import {useEffect,useRef,useState,type ReactNode} from 'react'
import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {useForm} from 'react-hook-form'
import {X,Plus,ArrowUpRight,AlertCircle,Search,LoaderCircle,Inbox} from 'lucide-react'
import {api,post,label,displayValue,csrf,ApiError,type Item,type Page,type Field,type Schema} from './api'
import {useI18n} from './i18n'

export function ErrorBox({error}:{error:unknown}) {const {t}=useI18n();return <div className="error" role="alert"><AlertCircle size={18}/><div><strong>{t('error')}</strong><p>{error instanceof ApiError&&error.status>=500?t('unexpectedError'):error instanceof ApiError&&error.status===403?t('permissionError'):error instanceof Error?error.message:String(error)}</p>{error instanceof ApiError&&error.requestId&&<small>{t('requestId')}: {error.requestId}</small>}</div></div>}
export function Loading(){const {t}=useI18n();return <div className="loading" role="status"><LoaderCircle className="spin" size={22}/>{t('loading')}</div>}
export function Badge({value}:{value:unknown}){const {t}=useI18n();const v=String(value||'draft');return <span className={'badge badge-'+v}><span/>{t(v)}</span>}
export function Empty({action}:{action?:ReactNode}){const {t}=useI18n();return <div className="empty"><div className="empty-icon"><Inbox size={28}/></div><h3>{t('empty')}</h3><p>{t('emptyCaption')}</p>{action}</div>}
export function Modal({title,close,children}:{title:string;close:()=>void;children:ReactNode}){
 const {t}=useI18n();const ref=useRef<HTMLDialogElement>(null)
 useEffect(()=>{const dialog=ref.current;dialog?.showModal();return()=>dialog?.close()},[])
 return <dialog ref={ref} className="modal" onCancel={close}><header><h2>{title}</h2><button className="icon-button" onClick={close} aria-label={t('close')}><X size={20}/></button></header>{children}</dialog>
}
export function RelationField({field,workspace,value,onChange}:{field:Field;workspace:string;value:unknown;onChange:(v:unknown)=>void}){
 const {t}=useI18n();const query=useQuery({queryKey:['options',field.related,workspace,field.filters],queryFn:()=>api<Page>(field.related+'/?'+new URLSearchParams(field.filters||{}),workspace)})
 if(query.error)return <ErrorBox error={query.error}/>
 return <select aria-label={t(field.name)} required={field.required} multiple={field.kind==='multi'} value={field.kind==='multi'?(Array.isArray(value)?value.map(String):[]):String(value||'')} onChange={e=>onChange(field.kind==='multi'?Array.from(e.target.selectedOptions).map(x=>x.value):e.target.value||null)}><option value="">{t('select')}</option>{query.data?.results.map(row=><option key={row.id} value={row.id}>{label(row)}</option>)}</select>
}
type RecordFormProps={resource:string;workspace:string;schema:Schema;initial?:Item;defaults?:Record<string,unknown>;onDone:()=>void}
export function RecordForm(props:RecordFormProps){
 return props.schema[props.resource]?.fields.length?<LoadedRecordForm {...props}/>:<Loading/>
}
function LoadedRecordForm({resource,workspace,schema,initial,defaults={},onDone}:RecordFormProps){
 const {t}=useI18n();const client=useQueryClient();const formDefaults=Object.fromEntries((schema[resource]?.fields||[]).filter(f=>f.default!==null&&f.default!==undefined).map(f=>[f.name,f.kind==='json'?JSON.stringify(f.default):f.default]));const {register,handleSubmit,setValue,watch}=useForm<Record<string,unknown>>({defaultValues:initial?Object.fromEntries(Object.entries(initial).map(([key,value])=>{const kind=schema[resource]?.fields.find(f=>f.name===key)?.kind;if(kind==='json')return [key,JSON.stringify(value)];if(kind==='datetime'&&value){const date=new Date(String(value));return [key,new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)]}return [key,value]})):{...formDefaults,...defaults}})
 const fields=schema[resource]?.fields||[]
 const mutation=useMutation({mutationFn:(values:Record<string,unknown>)=>{
   const body:Record<string,unknown>={...defaults}
   fields.forEach(f=>{let value=values[f.name]; if(f.kind==='json'){if(typeof value==='string')value=JSON.parse(value||'{}');else value=value||{}} if(f.kind==='number'&&value!==undefined&&value!=='')value=Number(value);if(f.kind==='datetime'&&value)value=new Date(String(value)).toISOString();if(value===''&&!f.required){if(f.kind==='datetime'||f.kind==='relation')value=null;else if(f.kind==='number')return} if(value!==undefined)body[f.name]=value})
   return api(resource+'/'+(initial?initial.id+'/':''),workspace,{method:initial?'PATCH':'POST',body:JSON.stringify(body)})
 },onSuccess:()=>{void client.invalidateQueries();onDone()}})
 return <form onSubmit={handleSubmit(values=>mutation.mutate(values))} className="form-grid">
 {fields.map(f=><label className={['textarea','json'].includes(f.kind)?'full':''} key={f.name}><span>{t(f.name)} {f.required&&<b className="required">*</b>}</span>
 {f.kind==='relation'||f.kind==='multi'?<RelationField field={{...f,...(f.related==='versions'&&watch('creative')?{filters:{creative:String(watch('creative'))}}:{})}} workspace={workspace} value={watch(f.name)} onChange={v=>setValue(f.name,v)}/>:
 f.kind==='select'?<select aria-label={t(f.name)} {...register(f.name)} required={f.required}><option value="">{t('select')}</option>{f.choices.map(c=><option key={c.value} value={c.value}>{t(c.value)}</option>)}</select>:
 f.kind==='boolean'?<input type="checkbox" {...register(f.name)}/>:
 f.kind==='textarea'?<textarea aria-label={t(f.name)} rows={4} {...register(f.name)} required={f.required}/>:
 f.kind==='json'?<textarea rows={3} {...register(f.name)} defaultValue={typeof (initial||defaults)[f.name]==='object'?JSON.stringify((initial||defaults)[f.name]):'{}'} dir="ltr"/>:
 <input aria-label={t(f.name)} type={f.kind==='number'?'number':f.kind==='datetime'?'datetime-local':'text'} step={f.kind==='number'?'any':undefined} {...register(f.name)} required={f.required}/>}
 </label>)}
 {mutation.error&&<div className="full"><ErrorBox error={mutation.error}/></div>}
 <footer className="form-footer full"><button type="button" className="button secondary" onClick={onDone}>{t('cancel')}</button><button className="button primary" disabled={mutation.isPending}>{mutation.isPending?t('loading'):t('save')}</button></footer></form>
}
export function ActionForm({title,fields=[],run,onDone,workspace}:{title:string;fields?:{name:string;kind?:string;options?:string[];required?:boolean;related?:string}[];run:(data:Record<string,unknown>)=>Promise<unknown>;onDone:()=>void;workspace:string}){
 const {t}=useI18n();const [values,setValues]=useState<Record<string,unknown>>({});const client=useQueryClient()
 const mutation=useMutation({mutationFn:()=>run(values),onSuccess:()=>{void client.invalidateQueries();onDone()}})
 return <Modal title={title} close={onDone}><form className="form-grid" onSubmit={e=>{e.preventDefault();mutation.mutate()}}>{fields.length===0&&<p className="full">{t('confirmCaption')}</p>}{fields.map(f=><label key={f.name} className={f.kind==='textarea'?'full':''}><span>{t(f.name)}</span>{f.related?<RelationField field={{name:f.name,kind:'relation',required:f.required||false,related:f.related,choices:[]}} workspace={workspace} value={values[f.name]} onChange={v=>setValues({...values,[f.name]:v})}/>:f.options?<select aria-label={t(f.name)} required={f.required} value={String(values[f.name]||'')} onChange={e=>setValues({...values,[f.name]:e.target.value})}><option value="">{t('select')}</option>{f.options.map(o=><option key={o} value={o}>{t(o)}</option>)}</select>:f.kind==='textarea'?<textarea aria-label={t(f.name)} rows={4} required={f.required} value={String(values[f.name]||'')} onChange={e=>setValues({...values,[f.name]:e.target.value})}/>:<input aria-label={t(f.name)} type={f.kind||'text'} required={f.required} value={String(values[f.name]||'')} onChange={e=>setValues({...values,[f.name]:e.target.value})}/>}</label>)}{mutation.error&&<div className="full"><ErrorBox error={mutation.error}/></div>}<footer className="form-footer full"><button type="button" className="button secondary" onClick={onDone}>{t('cancel')}</button><button className="button primary" disabled={mutation.isPending}>{t('confirm')}</button></footer></form></Modal>
}
export function ResourceList({resource,workspace,schema,title,filters={},onOpen,compact=false}:{resource:string;workspace:string;schema:Schema;title?:string;filters?:Record<string,string>;onOpen?:(item:Item)=>void;compact?:boolean}){
 const {t,lang}=useI18n();const [search,setSearch]=useState('');const [page,setPage]=useState(1);const [create,setCreate]=useState(false);const [editing,setEditing]=useState<Item|undefined>();const [selected,setSelected]=useState<Item|undefined>();const [operation,setOperation]=useState<string|null>(null)
 const params=new URLSearchParams({...filters,q:search,page:String(page)})
 const query=useQuery({queryKey:[resource,workspace,params.toString()],queryFn:()=>api<Page>(resource+'/?'+params,workspace)})
 const fields=schema[resource]?.fields||[];const canCreate=schema[resource]?.can_create;const rows=query.data?.results||[]
 const columns=['title','name','filename','action','operation','type','label','text','kind','outcome'].filter(k=>rows.some(r=>r[k]));const main=columns[0]||'id'
 const extras=['status','state','priority','provider','version_number','spend','impressions','clicks','revenue','currency','read_at','created_at'].filter(k=>rows.some(r=>k in r)).slice(0,5)
 const close=()=>{setOperation(null);setSelected(undefined)}
 const run=(op:string,data:Record<string,unknown>)=>post(`${resource}/${selected?.id}/actions/${op}/`,workspace,data)
 return <section className={'resource-section '+(compact?'compact':'')}>
 <div className="section-heading"><div><h2>{title||t(resource)}</h2><span className="muted small">{query.data?.count??rows.length} {t('count')}</span></div>{canCreate&&<button className="button primary" onClick={()=>setCreate(true)}><Plus size={17}/>{t('create')}</button>}</div>
 <div className="list-toolbar"><div className="search-input"><Search size={17}/><input aria-label={t('search')} placeholder={t('searchPlaceholder')} value={search} onChange={e=>{setSearch(e.target.value);setPage(1)}}/></div></div>
 {query.isPending?<Loading/>:query.error?<ErrorBox error={query.error}/>:rows.length===0?<Empty/>:<div className="table-scroll"><table><thead><tr><th>{t(main)}</th>{extras.map(k=><th key={k}>{t(k)}</th>)}<th><span className="sr-only">{t('actions')}</span></th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td><button className="record-link" onClick={()=>onOpen?onOpen(row):setSelected(row)}>{label(row)}</button>{row.code?<span className="record-code">{String(row.code)}</span>:null}</td>{extras.map(k=><td key={k}>{['status','state','priority','outcome'].includes(k)?<Badge value={row[k]}/>:k==='created_at'?new Intl.DateTimeFormat(lang,{dateStyle:'medium'}).format(new Date(String(row[k]))):k==='read_at'?t(row[k]?'read':'unread'):String(row[k]??'—')}</td>)}<td><button className="icon-button" aria-label={t('detail')} onClick={()=>onOpen?onOpen(row):setSelected(row)}><ArrowUpRight size={17}/></button></td></tr>)}</tbody></table></div>}
 {(page>1||query.data?.next)&&<footer className="pagination"><button className="button secondary" disabled={page===1} onClick={()=>setPage(page-1)}>{t('previous')}</button><span>{page}</span><button className="button secondary" disabled={!query.data?.next} onClick={()=>setPage(page+1)}>{t('next')}</button></footer>}
 {(create||editing)&&<Modal title={t(editing?'edit':'create')+' · '+(title||t(resource))} close={()=>{setCreate(false);setEditing(undefined)}}><RecordForm resource={resource} workspace={workspace} schema={schema} initial={editing} defaults={filters} onDone={()=>{setCreate(false);setEditing(undefined)}}/></Modal>}
 {selected&&!operation&&<Modal title={label(selected)} close={close}><div className="detail-content"><div className="detail-grid">{Object.entries(selected).filter(([k,v])=>v!==null&&v!==''&&!['id','workspace','display_label','relation_labels','asset'].includes(k)).map(([k])=><div key={k}><dt>{t(k)}</dt><dd>{displayValue(selected,k)}</dd></div>)}</div><div className="action-row">{schema[resource]?.can_edit&&<button className="button primary" onClick={()=>{setEditing(selected);setSelected(undefined)}}>{t('edit')}</button>}
 {resource==='storage/connections'&&['connect','sync','test','organize','transfer','disconnect'].map(op=><button className="button secondary" key={op} onClick={()=>setOperation(op)}>{t(op)}</button>)}
 {resource==='ad-connections'&&schema[resource]?.can_edit&&<button className="button secondary" onClick={()=>setOperation('credentials')}>{t('credentials')}</button>}
 {resource==='ad-connections'&&schema[resource]?.can_edit&&<button className="button secondary" disabled={selected.provider!=='meta'||selected.status!=='connected'} onClick={()=>setOperation('sync')}>{t('sync')}</button>}
 {resource==='proposals'&&selected.status==='proposed'&&['accept','reject'].map(op=><button className="button secondary" key={op} onClick={()=>setOperation(op)}>{t(op==='accept'?'accepted':'rejected')}</button>)}
 {resource==='experiments'&&['start','complete','cancel'].map(op=><button className="button secondary" key={op} onClick={()=>setOperation(op)}>{t(op)}</button>)}
 {resource==='context'&&<button className="button primary" onClick={()=>setOperation('new-version')}>{t('newContextVersion')}</button>}
 {resource==='context-versions'&&selected.status==='draft'&&<button className="button primary" onClick={()=>setOperation('approve')}>{t('approve')}</button>}
 {resource==='notifications'&&!selected.read_at&&<button className="button primary" onClick={()=>setOperation('read')}>{t('markRead')}</button>}
 {resource==='jobs'&&selected.status==='failed'&&['drive_sync','drive_test','drive_organize','performance_sync','automation','google_upload'].includes(String(selected.type))&&<button className="button secondary" onClick={()=>setOperation('retry')}>{t('retry')}</button>}
 {resource==='storage/objects'&&selected.provider==='local'&&<button className="button primary" onClick={async()=>{try{const response=await fetch(`/api/v1/storage/objects/${selected.id}/actions/download/?workspace=${workspace}`,{method:'POST',headers:{'X-CSRFToken':csrf()}});if(!response.ok)throw new Error(String(response.status));const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=String(selected.filename);a.click();URL.revokeObjectURL(url)}catch(e){setOperation('download-error');console.error(e)}}}>{t('download')}</button>}
 </div></div></Modal>}
 {selected&&operation&&<ActionForm title={t(operation)} workspace={workspace} onDone={close} fields={operation==='credentials'?[{name:'access_token',kind:'password',required:true},{name:'api_version',required:true}]:operation==='complete'?[{name:'learning',kind:'textarea',required:true},{name:'conclusion',kind:'textarea'},{name:'limitations',kind:'textarea'},{name:'next_action'}]:operation==='new-version'?[{name:'content',kind:'textarea',required:true}]:operation==='transfer'?[{name:'version',related:'versions',required:true},{name:'provider',options:['google_drive','youtube'],required:true},{name:'privacy',options:['private','unlisted','public']}]:operation==='connect'?[{name:'scope',options:['file','full'],required:true}]:[]} run={async data=>{if(operation==='credentials')return run(operation,{credentials:data});if(operation==='connect'){const res=await run(operation,data) as {url:string};window.location.assign(res.url);return}return run(operation,{...data,idempotency_key:crypto.randomUUID()})}}/>}
 {fields.length===0&&null}
 </section>
}


