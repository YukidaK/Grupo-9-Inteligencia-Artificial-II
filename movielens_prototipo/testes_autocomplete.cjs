/* Executa o widget real com DOM, relógio e transporte controlados; sem pacotes npm. */
const test=require('node:test'),assert=require('node:assert/strict');
const MovieAutocomplete=require('./static/autocomplete.js');
class Element {
  constructor(doc){this.ownerDocument=doc;this.children=[];this.attrs={};this.listeners={};this.value='';this.textContent='';this.hidden=false;this.disabled=false;}
  addEventListener(type,fn){this.listeners[type]=fn;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  removeAttribute(k){delete this.attrs[k];}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  scrollIntoView(){this.scrolled=true;}
  focus(){this.ownerDocument.activeElement=this;}
  emit(type,extra={}){const e={prevented:false,preventDefault(){this.prevented=true;},...extra};this.listeners[type]?.(e);return e;}
}
function setup(fetchSuggestions=async()=>[]){
  const doc={createElement(){return new Element(doc);}};
  const input=doc.createElement(),list=doc.createElement(),selected=doc.createElement(),status=doc.createElement();list.id='suggestions';list.hidden=true;
  let pending=null,wait=null;
  const widget=new MovieAutocomplete({input,list,selected,status,fetchSuggestions,poster:()=>doc.createElement(),setTimer:(fn,ms)=>{pending=fn;wait=ms;return fn;},clearTimer:()=>{pending=null;}});
  return {widget,input,list,selected,status,doc,delay:()=>wait,fire:()=>{const fn=pending;pending=null;return fn?.();},hasTimer:()=>!!pending};
}
const film=(movieId,titulo='Filme '+movieId+' (2000)')=>({movieId,titulo,ano:2000});
function results(w,films){w.widget.results=films;w.widget.show();}
test('debounce 300 ms e mínimo de dois caracteres',async()=>{
  const calls=[];const w=setup(async q=>{calls.push(q);return [film(1)];});
  w.input.value='T';w.input.emit('input');assert.equal(w.hasTimer(),false);
  w.input.value='To';w.input.emit('input');assert.equal(w.delay(),300);assert.equal(calls.length,0);
  w.input.value='Toy';w.input.emit('input');await w.fire();assert.deepEqual(calls,['Toy']);assert.equal(w.list.children.length,1);assert.equal(w.widget.active,-1);
});
test('respostas fora de ordem e abort ignorado pelo transporte',async()=>{
  const deferred=[];const w=setup((q,signal)=>new Promise(resolve=>deferred.push({q,signal,resolve})));
  w.input.value='Toy';w.input.emit('input');const old=w.fire();
  w.input.value='Solaris';w.input.emit('input');assert.equal(deferred[0].signal.aborted,true);const next=w.fire();
  deferred[1].resolve([film(2,'Solaris (2002)')]);await next;deferred[0].resolve([film(1,'Toy Story (1995)')]);await old;
  assert.equal(w.widget.results[0].movieId,2);assert.equal(w.input.attrs['aria-busy'],'false');
});
test('resposta antiga não aparece durante o debounce de uma nova consulta',async()=>{
  let resolve;const w=setup(()=>new Promise(r=>resolve=r));w.input.value='Toy';w.input.emit('input');const run=w.fire();
  w.input.value='Sol';w.input.emit('input');resolve([film(1)]);await run;assert.equal(w.list.hidden,true);assert.equal(w.widget.results.length,0);
});
test('teclado exige escolha, Enter nunca envia formulário e Escape fecha',()=>{
  const w=setup();results(w,[film(1),film(2)]);
  assert.equal(w.input.emit('keydown',{key:'Enter'}).prevented,true);assert.equal(w.widget.items.length,0);
  w.input.emit('keydown',{key:'ArrowDown'});assert.equal(w.input.attrs['aria-activedescendant'],'suggestions-0');assert.equal(w.list.children[0].attrs['aria-selected'],'true');
  w.input.emit('keydown',{key:'ArrowDown'});w.input.emit('keydown',{key:'ArrowUp'});
  const e=w.input.emit('keydown',{key:'Enter'});assert.equal(e.prevented,true);assert.equal(w.widget.items[0].movieId,1);assert.equal(w.input.value,'');assert.equal(w.list.hidden,true);
  results(w,[film(2)]);w.input.emit('keydown',{key:'Escape'});assert.equal(w.input.attrs['aria-expanded'],'false');assert.equal(w.input.attrs['aria-activedescendant'],undefined);
});
test('Escape invalida resposta pendente; blur também fecha a lista',async()=>{
  let resolve;const w=setup(()=>new Promise(r=>resolve=r));w.input.value='Toy';w.input.emit('input');const run=w.fire();w.input.emit('keydown',{key:'Escape'});resolve([film(1)]);await run;assert.equal(w.list.hidden,true);
  results(w,[film(1)]);w.input.emit('blur');assert.equal(w.list.hidden,true);
});
test('mouse/toque seleciona, duplicata por ID é impedida e remoção funciona',()=>{
  const w=setup();results(w,[film(1)]);const option=w.list.children[0];assert.equal(option.emit('pointerdown').prevented,true);option.emit('click');assert.equal(w.widget.items.length,1);
  results(w,[film(1,'Outro texto para o mesmo ID')]);w.widget.choose(0);assert.equal(w.widget.items.length,1);assert.match(w.status.textContent,/já está/);
  w.selected.children[0].children[1].onclick();assert.equal(w.widget.items.length,0);
  w.widget.existing=()=>[film(2)];results(w,[film(2)]);w.widget.choose(0);assert.equal(w.widget.items.length,0);
});
test('mais de cinco selecionados, etiquetas de excedentes e nenhuma seleção perdida',()=>{
  const w=setup();for(let i=1;i<=7;i++){results(w,[film(i)]);w.widget.choose(0);}
  assert.equal(w.widget.items.length,7);assert.match(w.selected.children[4].children[0].textContent,/Referência/);assert.match(w.selected.children[5].children[0].textContent,/Excedente/);
  w.widget.confirmed([1,2,3,4,5,6]);assert.deepEqual(w.widget.items.map(f=>f.movieId),[7]);w.widget.reset();assert.equal(w.widget.items.length,0);
});
test('sem resultados ou falha preserva seleção e campo editável',async()=>{
  const w=setup(async()=>[]);results(w,[film(1)]);w.widget.choose(0);w.input.value='Nada';w.input.emit('input');await w.fire();assert.equal(w.widget.items.length,1);assert.match(w.status.textContent,/Nenhum/);
  w.widget.fetchSuggestions=async()=>{throw Error('offline');};w.input.value='Outro';w.input.emit('input');await w.fire();assert.equal(w.input.disabled,false);assert.equal(w.widget.items.length,1);assert.match(w.status.textContent,/Não foi possível/);
});

// Exercita também o bootstrap e o fetch da página, além da classe isolada.
const fs=require('fs'),vm=require('vm'),path=require('path');
function fullPage({missingScript=false,oldServer=false}={}){
  const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
  const timers=[],nodes=new Map();
  const doc={createElement(){const e=new Element(doc);e.dataset={};e.querySelectorAll=()=>[];e.prepend=(...n)=>e.children.unshift(...n);return e;},querySelector:s=>nodes.get(s),querySelectorAll:()=>[]};
  for(const [,id] of html.matchAll(/\bid="([^"]+)"/g)){const e=doc.createElement();e.id=id;nodes.set('#'+id,e);}
  const state={mensagem:'Pronto',assistidos:[],referencias:[],excedentes:[],rejeitados:[],preferencias:{positivas:[],negativas:[]},recomendacoes:[]};
  const context={console,AbortController,queueMicrotask,setTimeout:fn=>{timers.push(fn);return fn;},clearTimeout:fn=>{const i=timers.indexOf(fn);if(i>=0)timers.splice(i,1);},document:doc,IntersectionObserver:class{observe(){}unobserve(){}},fetch:async url=>({ok:!oldServer||!url.startsWith('/api/filmes'),status:oldServer&&url.startsWith('/api/filmes')?404:200,json:async()=>url.startsWith('/api/filmes')?{sugestoes:[film(1,'Toy Story (1995)')]}:state})};
  context.window=context;vm.createContext(context);
  // Timers nativos de Window exigem o receptor correto; Node não impõe essa regra.
  context.__schedule=fn=>{timers.push(fn);return fn;};
  context.__cancel=fn=>{const i=timers.indexOf(fn);if(i>=0)timers.splice(i,1);};
  vm.runInContext(`window.setTimeout=function(fn){if(this!==window)throw new TypeError('Illegal invocation: setTimeout');return window.__schedule(fn);};window.clearTimeout=function(fn){if(this!==window)throw new TypeError('Illegal invocation: clearTimeout');return window.__cancel(fn);};`,context);
  if(!missingScript)vm.runInContext(fs.readFileSync(path.join(__dirname,'static/autocomplete.js'),'utf8'),context);
  const inline=html.match(/<script>([\s\S]*?)<\/script>/)[1];vm.runInContext(inline,context);
  return {context,nodes,timers};
}
test('página completa inicializa autocomplete e exibe lista após digitar',async()=>{
  const p=fullPage();await new Promise(r=>setImmediate(r));
  const input=p.nodes.get('#titles');input.value='To';input.emit('input');input.value='Toy';input.emit('input');assert.equal(p.timers.length,1);await p.timers.shift()();
  assert.equal(p.nodes.get('#suggestions').hidden,false);assert.equal(p.nodes.get('#suggestions').children.length,1);
  assert.match(p.nodes.get('#search-status').textContent,/1 sugestões/);
  input.emit('keydown',{key:'ArrowDown'});input.emit('keydown',{key:'Enter'});
  assert.equal(vm.runInContext('autocomplete.items[0].movieId',p.context),1);
});
test('arquivo do widget ausente não derruba o restante da página',async()=>{
  const p=fullPage({missingScript:true});await new Promise(r=>setImmediate(r));
  assert.equal(vm.runInContext('autocomplete',p.context),null);
  await p.nodes.get('#search').onsubmit({preventDefault(){}});
  assert.match(p.nodes.get('#search-status').textContent,/não carregou/);
  assert.equal(p.nodes.get('#status').textContent,'Pronto');
});
test('página com backend antigo orienta reiniciar o servidor sem perder seleção',async()=>{
  const p=fullPage({oldServer:true});await new Promise(r=>setImmediate(r));
  const input=p.nodes.get('#titles');input.value='Toy';input.emit('input');await p.timers.shift()();
  assert.match(p.nodes.get('#search-status').textContent,/Ctrl\+C/);
  assert.match(p.nodes.get('#search-status').textContent,/Ctrl\+Shift\+R/);
  assert.equal(input.disabled,false);
});
