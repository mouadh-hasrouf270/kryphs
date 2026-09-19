import {useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {api,csrf,type Item,type Page} from './api'
import {Badge,Empty,ErrorBox,Loading} from './components'
import {useI18n} from './i18n'

function versionTitle(version:Item){const number='v'+String(version.version_number).padStart(3,'0');return number+(version.label&&version.label!==number?' / '+String(version.label):'')}

export function CreativeFiles({workspace,creative,currentVersion}:{workspace:string;creative:string;currentVersion?:string}){
 const {t}=useI18n();const [error,setError]=useState<unknown>()
 const query=useQuery({queryKey:['creative-file-history',workspace,creative],queryFn:async()=>{
  async function all(resource:string){const rows:Item[]=[];for(let page=1;;page++){const response=await api<Page>(`${resource}/?creative=${creative}&page=${page}`,workspace);rows.push(...response.results);if(!response.next)return rows}}
  const [files,versions]=await Promise.all([all('files'),all('versions')]);return {files,versions}
 }})
 const download=async(file:Item)=>{try{const response=await fetch(`/api/v1/storage/objects/${file.storage_object}/actions/download/?workspace=${workspace}`,{method:'POST',credentials:'same-origin',headers:{'X-CSRFToken':csrf()}});if(!response.ok)throw new Error(t('downloadFailed'));const blob=await response.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=String((file.asset as Item).filename);anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){setError(e)}}
 if(query.isPending)return <Loading/>;if(query.error)return <ErrorBox error={query.error}/>
 const {files,versions}=query.data
 const groups:[Item|null,Item[]][]=[...versions.sort((a,b)=>Number(b.version_number)-Number(a.version_number)).map(v=>[v,files.filter(f=>f.version===v.id)] as [Item,Item[]]),[null,files.filter(f=>!f.version)]]
 return <div className="file-history">{!!error&&<ErrorBox error={error}/>} {!files.length&&<Empty/>}{groups.filter(([version,rows])=>version||rows.length).map(([version,rows])=><section className="panel version-file-group" key={version?.id||'attachments'}><div className="section-heading"><h3>{version?versionTitle(version):t('attachment')}{version?.id===currentVersion?' · '+t('current'):''}</h3>{version&&<Badge value={version.status}/>}</div>{rows.length?rows.map(file=>{const asset=file.asset as Item;const drive=asset.drive_upload as {reason?:string;status?:string;queued?:boolean}|undefined;return <article className="file-history-row" key={file.id}><div><strong>{String(asset.filename)}</strong><p>{t(String(file.role))} · {t(String(asset.provider))} · {String(asset.mime_type)} · {new Intl.NumberFormat().format(Number(asset.size))} {t('bytes')}</p>{Number(asset.width)>0&&<small>{String(asset.width)} × {String(asset.height)}</small>}{drive&&<p className="muted">{t('driveMirror')}: {t(drive.reason||drive.status||(drive.queued?'queued':'drive_not_connected'))}</p>}{!asset.active&&<p>{t('unavailable')}</p>}</div>{asset.provider==='local'?<button className="button secondary" disabled={!asset.active} onClick={()=>void download(file)}>{t('download')}</button>:asset.active?<a className="button secondary" href={'https://drive.google.com/file/d/'+encodeURIComponent(String(asset.external_id))+'/view'} target="_blank" rel="noreferrer">{t('openDrive')}</a>:null}</article>}):<p className="muted">{t('noVersionFiles')}</p>}</section>)}</div>
}
