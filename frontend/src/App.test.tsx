import {describe,it,expect} from 'vitest'
import {render,screen,cleanup} from '@testing-library/react'
import {afterEach} from 'vitest'
import {Badge,ErrorBox} from './components'
import {I18n,dictionaries} from './i18n'
import {buildUtm} from './App'
afterEach(cleanup)
describe('localized interface',()=>{
 it('renders Arabic workflow state',()=>{render(<I18n.Provider value={{lang:'ar',t:k=>dictionaries.ar[k]||k}}><Badge value="approved"/></I18n.Provider>);expect(screen.getByText('معتمد')).toBeInTheDocument()})
 it('makes API failures accessible',()=>{render(<ErrorBox error={new Error('Workspace unavailable')}/>);expect(screen.getByRole('alert')).toHaveTextContent('Workspace unavailable')})
 it('includes translated primary navigation in all languages',()=>{for(const locale of Object.values(dictionaries)){for(const key of ['overview','board','requests','creatives','save','login','approve','notifications'])expect(locale[key]).toBeTruthy()}})
})
describe('UTM links',()=>{
 it('encodes campaign text while preserving fragments and existing parameters',()=>{const link=new URL(buildUtm('https://example.com/page?ref=a#offer',{source:'social',campaign:'ربيع & été'}));expect(link.searchParams.get('utm_campaign')).toBe('ربيع & été');expect(link.searchParams.get('ref')).toBe('a');expect(link.hash).toBe('#offer')})
 it('replaces duplicate UTM values',()=>expect(new URL(buildUtm('https://example.com?utm_source=old',{source:'new'})).searchParams.getAll('utm_source')).toEqual(['new']))
 it('rejects executable and credential-bearing URLs',()=>{expect(()=>buildUtm('javascript:alert(1)',{})).toThrow();expect(()=>buildUtm('https://user:pass@example.com',{})).toThrow()})
})
