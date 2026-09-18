import {afterEach,describe,expect,it,vi} from 'vitest'
import {cleanup,render,screen} from '@testing-library/react'
import {api,ApiError} from './api'
import {ErrorBox} from './components'
import {I18n,dictionaries} from './i18n'
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
describe('API failures',()=>{
 it('retains field validation and the correlation ID',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({campaign:['Must match selected brand.']}),{status:400,headers:{'X-Request-ID':'request-123'}})))
  let failure:unknown
  try{await api('requests/')}catch(error){failure=error}
  expect(failure).toBeInstanceOf(ApiError)
  render(<ErrorBox error={failure}/>);expect(screen.getByRole('alert')).toHaveTextContent('Must match selected brand.');expect(screen.getByRole('alert')).toHaveTextContent('request-123')
 })
 it('hides server error details while showing a support identifier',()=>{
  render(<I18n.Provider value={{lang:'en',t:k=>dictionaries.en[k]||k}}><ErrorBox error={new ApiError(500,{detail:'secret traceback'},'safe-id')}/></I18n.Provider>)
  expect(screen.getByRole('alert')).not.toHaveTextContent('secret traceback');expect(screen.getByRole('alert')).toHaveTextContent('safe-id')
 })
 it('contains Arabic for the daily request and Drive workflow',()=>{
  for(const key of ['requestBasics','deliverables','addDeliverable','removeDeliverable','createCreative','driveRootHint','addDriveConnection','scope','youtube_scope','resetTemporaryPassword','permissionError']){
   expect(dictionaries.ar[key]).toMatch(/[\u0600-\u06ff]/);expect(dictionaries.ar[key]).not.toContain('???')
  }
 })
})
