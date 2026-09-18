import {afterEach,expect,it,vi} from 'vitest'
import {cleanup,render,screen,waitFor} from '@testing-library/react'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {RecordForm} from './components'
import {displayValue,label,type Schema} from './api'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})

it('waits for the schema before initializing server defaults',()=>{
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
 const show=(schema:Schema)=><QueryClientProvider client={client}><RecordForm resource="deliverables" workspace="studio" schema={schema} onDone={()=>{}}/></QueryClientProvider>
 const view=render(show({deliverables:{fields:[],can_create:true,can_edit:true,permission:'create_requests'}}))
 expect(screen.getByRole('status')).toBeVisible()
 view.rerender(show({deliverables:{fields:[{name:'creative_type',kind:'select',default:'video',required:false,choices:[{value:'video',label:'Video'}],related:null}],can_create:true,can_edit:true,permission:'create_requests'}}))
 expect(screen.getByRole('combobox')).toHaveValue('video')
})

it('filters version choices by the current creative and renders readable labels',async()=>{
 const fetcher=vi.fn().mockResolvedValue(new Response(JSON.stringify({results:[{id:'version-a',display_label:'Creative A / v002'}]})))
 vi.stubGlobal('fetch',fetcher)
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
 render(<QueryClientProvider client={client}><RecordForm resource="comments" workspace="studio" defaults={{creative:'creative-a'}} schema={{comments:{fields:[{name:'version',kind:'relation',required:false,choices:[],related:'versions'}],can_create:true,can_edit:true,permission:'comment_creatives'}}} onDone={()=>{}}/></QueryClientProvider>)
 await waitFor(()=>expect(screen.getByRole('option',{name:'Creative A / v002'})).toBeVisible())
 expect(fetcher.mock.calls[0][0]).toBe('/api/v1/versions/?creative=creative-a&workspace=studio')
 const row={id:'identity',owner:'45d254c3-f888-4e52-a417-473a2550e208',relation_labels:{owner:'Ahmed'},display_label:'Brief'}
 expect(displayValue(row,'owner')).toBe('Ahmed')
 expect(label(row)).toBe('Brief')
 expect(row.owner).toBe('45d254c3-f888-4e52-a417-473a2550e208')
})
