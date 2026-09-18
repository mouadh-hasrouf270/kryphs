export type Item = {id:string; [key:string]:unknown}
export type Page = {results:Item[];count?:number;next?:string|null}
export type Field = {name:string;kind:string;required:boolean;choices:{value:string;label:string}[];related:string|null;default?:unknown}
export type Schema = Record<string,{fields:Field[];can_create:boolean;can_edit:boolean;permission:string}>
export type User = {id:string;email:string;display_name:string;is_superuser:boolean;must_change_password:boolean;profile:{preferred_language:'ar'|'en'|'fr'};workspaces:{id:string;name:string;role:string;permissions:string[]}[]}
export const label = (row:Item) => String(row.title || row.name || row.filename || row.label || row.email || row.action || row.type || row.id.slice(0,8))
export function csrf():string { return decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '') }
export async function api<T>(path:string,workspace='',init:RequestInit={}):Promise<T> {
  const separator=path.includes('?')?'&':'?'
  const url='/api/v1/'+path+(workspace?separator+'workspace='+encodeURIComponent(workspace):'')
  const response=await fetch(url,{...init,credentials:'same-origin',headers:{...(init.body instanceof FormData?{}:{'Content-Type':'application/json'}),'X-CSRFToken':csrf(),...(init.headers||{})}})
  if (!response.ok) {
    let message:string
    try { const body=await response.json(); message=typeof body.detail==='string'?body.detail:JSON.stringify(body) } catch { message=`HTTP ${response.status}` }
    throw new Error(message)
  }
  return response.status===204?undefined as T:response.json() as Promise<T>
}
export const post = <T>(path:string,workspace:string,data:unknown) => api<T>(path,workspace,{method:'POST',body:JSON.stringify(data)})
