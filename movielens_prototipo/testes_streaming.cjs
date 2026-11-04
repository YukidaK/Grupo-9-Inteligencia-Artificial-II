const test=require('node:test'),assert=require('node:assert/strict');
const UI=require('./static/streaming.js');
class Element{
 constructor(doc,tag){this.ownerDocument=doc;this.tagName=tag;this.children=[];this.listeners={};this.attrs={};this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';}
 addEventListener(t,f){this.listeners[t]=f;}
 setAttribute(k,v){this.attrs[k]=String(v);}
 append(...n){for(const x of n)x.parentElement=this;this.children.push(...n);}
 remove(){this.parentElement.children=this.parentElement.children.filter(x=>x!==this);}
 replaceChildren(...n){this.children=n;}
 focus(){this.ownerDocument.activeElement=this;}
 change(){this.listeners.change?.();}
}
const response=(ids=[],modo='restrito',catalogo=[{id:10,nome:'Serviço Alfa fictício'},{id:20,nome:'Serviço Beta fictício'}])=>({catalogo:{regiao:'BR',provedores:catalogo},preferencias:{regiao:'BR',provedores:ids,modo,ativo:false},integracao_ativa:false});
function setup({data=response(),load,send}={}){
 const doc={createElement(tag){return new Element(doc,tag);}};doc.body=doc.createElement('body');doc.activeElement=doc.body;
 const nodes={};for(const n of ['form','grid','services','modes','restricted','flexible','save','count','status','empty','retry'])nodes[n]=doc.createElement(n);
 const calls=[];
 const ui=new UI({...nodes,load:load||(async()=>data),send:send||(async p=>{calls.push(p);return response(p.provedores,p.modo)})});
 return {ui,doc,calls,...nodes};
}
test('renderiza checkboxes nativos com rótulos, região e contagem',async()=>{
 const p=setup();await p.ui.carregar();assert.equal(p.grid.children.length,2);
 const [checkbox,nome]=p.grid.children[0].children;
 assert.equal(checkbox.type,'checkbox');assert.equal(nome.textContent,'Serviço Alfa fictício');assert.equal(p.grid.children[0].htmlFor,checkbox.id);
 assert.equal(checkbox.attrs['aria-describedby'],'streaming-notice');assert.equal(p.count.textContent,'0 serviços selecionados');assert.equal(p.restricted.checked,true);
  assert.equal(p.services.hidden,false);
});
test('seleciona vários, desmarca e atualiza contagem sem recarregar',async()=>{
 const p=setup();await p.ui.carregar();const [a,b]=p.ui.checks;
 a.checked=true;a.change();assert.equal(p.count.textContent,'1 serviço selecionado');
 b.checked=true;b.change();assert.equal(p.count.textContent,'2 serviços selecionados');
 a.checked=false;a.change();assert.equal(p.count.textContent,'1 serviço selecionado');
});
test('salva modo e IDs sem ativação e restaura ao atualizar',async()=>{
 let stored=response();const load=async()=>stored;
 const p=setup({load,send:async d=>{stored=response(d.provedores,d.modo);return stored}});await p.ui.carregar();
 p.ui.checks[1].checked=true;p.ui.checks[1].change();p.restricted.checked=false;p.flexible.checked=true;p.flexible.change();await p.ui.salvar();
 assert.match(p.status.textContent,/salvas nesta sessão/);assert.equal(stored.preferencias.ativo,false);
 const next=setup({load});await next.ui.carregar();assert.equal(next.ui.checks[1].checked,true);assert.equal(next.flexible.checked,true);
});
test('sessões distintas mantêm seleções distintas',async()=>{
 const a=setup({data:response([10])}),b=setup({data:response([20],'flexivel')});await a.ui.carregar();await b.ui.carregar();
 assert.equal(a.ui.checks[0].checked,true);assert.equal(b.ui.checks[0].checked,false);assert.equal(b.flexible.checked,true);
});
test('catálogo vazio é honesto, permite modo e não inventa opções',async()=>{
 const p=setup({data:response([],'restrito',[])});await p.ui.carregar();assert.equal(p.grid.children.length,0);assert.equal(p.empty.hidden,false);assert.equal(p.save.disabled,false);
 assert.equal(p.services.hidden,true);
});
test('falha ao salvar preserva seleções, foco e permite nova tentativa',async()=>{
 const p=setup({send:async()=>{throw Error('falha')}});await p.ui.carregar();const input=p.ui.checks[0];input.checked=true;input.change();input.focus();
 await p.ui.salvar();assert.equal(input.checked,true);assert.equal(p.doc.activeElement,input);assert.equal(p.save.disabled,false);assert.match(p.status.textContent,/seleções foram mantidas/);
});
test('falha inicial não interfere em filmes e permite repetir',async()=>{
 let fail=true;const p=setup({load:async()=>{if(fail)throw Error();return response()}});await p.ui.carregar();assert.equal(p.retry.hidden,false);assert.equal(p.save.disabled,true);
 assert.match(p.status.textContent,/continuar escolhendo filmes/);fail=false;await p.retry.onclick();assert.equal(p.ui.checks.length,2);
});
test('mudança durante salvamento não é sobrescrita pela resposta antiga',async()=>{
 let resolve;const p=setup({send:()=>new Promise(r=>resolve=r)});await p.ui.carregar();p.ui.checks[0].checked=true;p.ui.checks[0].change();
 const pending=p.ui.salvar();p.ui.checks[1].checked=true;p.ui.checks[1].change();resolve(response([10]));await pending;
 assert.equal(p.ui.checks[1].checked,true);assert.match(p.status.textContent,/alterações não salvas/);
});
test('resposta que anuncia ativação é recusada e IDs não são inferidos',async()=>{
 const data=response();data.integracao_ativa=true;const p=setup({data});await p.ui.carregar();assert.equal(p.save.disabled,true);assert.equal(p.ui.checks.length,0);
 const q=setup({data:response([999])});await q.ui.carregar();assert.equal(q.save.disabled,true);
});
test('submit nativo não recarrega, não altera o DOM e restaura foco do botão',async()=>{
 const p=setup();await p.ui.carregar();const input=p.ui.checks[0];input.checked=true;input.change();p.save.focus();
 let prevented=false;const pending=p.form.onsubmit({preventDefault(){prevented=true}});p.doc.activeElement=p.doc.body;await pending;
 assert.equal(prevented,true);assert.equal(p.ui.checks[0],input);assert.equal(p.doc.activeElement,p.save);
 assert.deepEqual(p.calls[0],{acao:'salvar',regiao:'BR',provedores:[10],modo:'restrito'});
});

test('bootstrap real carrega streaming só após estabelecer a sessão de recomendações',async()=>{
 const fs=require('fs'),vm=require('vm'),path=require('path');
 const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8'),nodes=new Map(),calls=[];
 const doc={createElement(tag){const e=new Element(doc,tag);e.dataset={};e.querySelectorAll=()=>[];e.prepend=(...n)=>e.children.unshift(...n);return e;},querySelector:s=>nodes.get(s),querySelectorAll:()=>[]};
 doc.body=doc.createElement('body');doc.activeElement=doc.body;
 for(const [,id] of html.matchAll(/\bid="([^"]+)"/g)){const e=doc.createElement();e.id=id;nodes.set('#'+id,e);}
 const state={mensagem:'Pronto',assistidos:[],referencias:[],excedentes:[],rejeitados:[],preferencias:{positivas:[],negativas:[]},recomendacoes:[]};
 let estabelecida=false;
 const context={console,document:doc,AbortController,queueMicrotask,IntersectionObserver:class{observe(){}unobserve(){}},fetch:async url=>{
   calls.push(url);if(url==='/api/streaming')assert.equal(estabelecida,true);
   return {ok:true,json:async()=>{if(url==='/api/recomendar'){estabelecida=true;return state;}return response([20]);}};
 }};context.window=context;vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'static/streaming.js'),'utf8'),context);
 vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
 await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));
 assert.deepEqual(calls,['/api/recomendar','/api/streaming']);assert.equal(nodes.get('#streaming-grid').children.length,2);
 assert.equal(nodes.get('#streaming-count').textContent,'1 serviço selecionado');
});

function reconciled(ids=[10,20],catalogo=[{id:10,nome:'Alfa fictício'},{id:30,nome:'Gama fictício'}]){
 const r=response(ids,'flexivel',catalogo);const missing=ids.filter(i=>!catalogo.some(p=>p.id===i)).sort((a,b)=>a-b);
 r.reconciliacao={provedores_ausentes:missing,revisao_necessaria:missing.length>0};r.mensagem=missing.length?'Há provedores salvos fora do catálogo atual. Revise suas escolhas.':'';return r;
}
test('UX02 catálogo inalterado preserva seleções sem pendências',async()=>{
 const p=setup({data:reconciled([10])});await p.ui.carregar();assert.equal(p.ui.pendingIds.size,0);assert.equal(p.ui.checks[0].checked,true);
});
test('UX02 ausente é revisão, não bloqueia válidos nem vira homologado',async()=>{
 const p=setup({data:reconciled()});await p.ui.carregar();assert.equal(p.save.disabled,false);assert.match(p.status.textContent,/fora do catálogo/);
 assert.equal(p.ui.checks.length,3);assert.equal(p.ui.checks[0].checked,true);assert.match(p.grid.children[2].children[1].textContent,/ID 20.*fora do catálogo/);assert.match(p.count.textContent,/1 serviço selecionado.*1 ID/);
 p.ui.checks[1].checked=true;p.ui.checks[1].change();assert.equal(p.count.textContent,'2 serviços selecionados · 1 ID(s) fora do catálogo para revisão');
});
test('UX02 remoção explícita envia confirmação e preserva DOM/foco válido',async()=>{
 const p=setup({data:reconciled(),send:async d=>{p.calls.push(d);return reconciled(d.provedores)}});await p.ui.carregar();
 const valid=p.ui.checks[0],missing=p.ui.checks[2];missing.checked=false;missing.change();valid.focus();await p.ui.salvar();
 assert.deepEqual(p.calls[0].remover_incompativeis,[20]);assert.deepEqual(p.calls[0].provedores,[10]);assert.equal(p.ui.checks[0],valid);assert.equal(p.doc.activeElement,valid);assert.equal(p.ui.pendingIds.size,0);assert.equal(p.grid.children.length,2);
});
test('UX02 refresh restaura ausentes; metadados inventados são recusados',async()=>{
 const p=setup({data:reconciled()});await p.ui.carregar();await p.ui.carregar();assert.equal(p.ui.checks[2].checked,true);
 const data=reconciled();data.reconciliacao.provedores_ausentes=[99];const q=setup({data});await q.ui.carregar();assert.equal(q.save.disabled,true);
});
