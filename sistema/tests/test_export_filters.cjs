const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const events = {}, timers = new Map(), pending = [];
let next = 0;
const form = {dataset:{countUrl:'/exportacoes/contagem'},addEventListener:(name,fn)=>events[name]=fn};
const count = {}, status = {}, summary = {setAttribute(){},removeAttribute(){}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/export-filters.js'),'utf8'), {
  document:{querySelector:selector=>({'[data-export-filters]':form,'[data-export-count]':count,'[data-export-status]':status,'[data-export-summary]':summary}[selector])},
  FormData:class {},URLSearchParams:class {toString(){return '';}},AbortController,
  setTimeout:fn=>{timers.set(++next,fn);return next;},clearTimeout:id=>timers.delete(id),
  fetch:()=>new Promise(resolve=>pending.push(resolve))
});
function tick(){const [id,fn]=timers.entries().next().value;timers.delete(id);return fn();}
const response=total=>({ok:true,redirected:false,json:async()=>({total,filtrado:true})});
(async()=>{
  const first=tick();
  events.change();
  const second=tick();
  pending[1](response(12));await second;
  assert.equal(count.textContent,'12');
  pending[0](response(99));await first;
  assert.equal(count.textContent,'12','Resposta antiga não substitui os filtros novos');
  events.reset();const reset=tick();pending[2](response(0));await reset;
  assert.equal(count.textContent,'0');assert.equal(status.textContent,'Nenhum cliente encontrado');
  events.change();const failure=tick();pending[3]({ok:false});await failure;
  assert.equal(count.textContent,'—');
  events.change();const retry=tick();pending[4](response(4));await retry;
  assert.equal(count.textContent,'4');
  console.log('Contagem: atualização, respostas fora de ordem, limpeza, vazio e recuperação OK.');
})().catch(error=>{console.error(error);process.exitCode=1;});
