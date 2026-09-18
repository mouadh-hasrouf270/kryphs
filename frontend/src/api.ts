export type Item = {id:string; [key:string]:unknown}
export type Page = {results:Item[];count?:number;next?:string|null}
export type Field = {name:string;kind:string;required:boolean;choices:{value:string;label:string}[];related:string|null;default?:unknown;filters?:Record<string,string>}
export type Schema = Record<string,{fields:Field[];can_create:boolean;can_edit:boolean;permission:string}>
export type User = {id:string;email:string;display_name:string;is_superuser:boolean;must_change_password:boolean;capabilities:{meta_publish:boolean;youtube_publish:boolean;google_oauth:boolean};profile:{preferred_language:'ar'|'en'|'fr'};workspaces:{id:string;name:string;role:string;permissions:string[]}[]}
export const label = (row:Item) => String(row.display_label || row.title || row.name || row.filename || row.label || row.email || row.action || row.type || '\u2014')
export function csrf():string { return decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '') }
export async function api<T>(path:string,workspace='',init:RequestInit={}):Promise<T> {
  const separator=path.includes('?')?'&':'?'
  const url='/api/v1/'+path+(workspace?separator+'workspace='+encodeURIComponent(workspace):'')
  const response=await fetch(url,{...init,credentials:'same-origin',headers:{...(init.body instanceof FormData?{}:{'Content-Type':'application/json'}),'X-CSRFToken':csrf(),...(init.headers||{})}})
  if (!response.ok) {
    let body:Record<string,unknown>
    try {body=await response.json()}catch{body={detail:response.status===403?'You do not have permission to perform this action.':'The request could not be completed.'}}
    throw new ApiError(response.status,body,response.headers.get('X-Request-ID')||String(body.request_id||''))
  }
  return response.status===204?undefined as T:response.json() as Promise<T>
}
export const post = <T>(path:string,workspace:string,data:unknown) => api<T>(path,workspace,{method:'POST',body:JSON.stringify(data)})

export class ApiError extends Error {
 constructor(public status:number,public fields:Record<string,unknown>,public requestId:string){
  const flatten=(value:unknown):string=>Array.isArray(value)?value.map(flatten).join('; '):value&&typeof value==='object'?Object.entries(value).map(([key,v])=>`${key}: ${flatten(v)}`).join('; '):String(value)
  super(status>=500?'The server could not complete this action.':flatten(fields));this.name='ApiError'
 }
}

export function relationLabel(row:Item,key:string):string{
 const labels=row.relation_labels as Record<string,string|string[]>|undefined
 const value=labels?.[key]
 return Array.isArray(value)?value.join(', '):value||'\u2014'
}
export function displayValue(row:Item,key:string):string{
 if((row.relation_labels as Record<string,unknown>|undefined)?.[key]!==undefined)return relationLabel(row,key)
 const value=row[key]
 if(typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(value))return '\u2014'
 return value===null||value===undefined?'\u2014':typeof value==='object'?JSON.stringify(value,null,2):String(value)
}
