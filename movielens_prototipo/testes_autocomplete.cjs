/* Executa o widget real com DOM, relógio e transporte controlados; sem pacotes npm. */
const test=require('node:test'),assert=require('node:assert/strict');
const MovieAutocomplete=require('./static/autocomplete.js');
class Element {
  constructor(doc){this.ownerDocument=doc;this.children=[];this.attrs={};this.listeners={};this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.isConnected=true;}
  addEventListener(type,fn){this.listeners[type]=fn;}
  setAttribute(k,v){this.attrs[k]=String(v);}
  removeAttribute(k){delete this.attrs[k];}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  scrollIntoView(){this.scrolled=true;}
  focus(){this.ownerDocument.activeElement=this;for(const f of this.ownerDocument.focusListeners||[])f({target:this});}
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
test('seleção limita cinco, permite remover e escolher novamente',()=>{
  const w=setup();for(let i=1;i<=7;i++){results(w,[film(i)]);w.widget.choose(0);}
  assert.equal(w.widget.items.length,5);assert.match(w.status.textContent,/cinco filmes/);
  w.selected.children[0].children[1].onclick();
  results(w,[film(6)]);w.widget.choose(0);
  assert.deepEqual(w.widget.items.map(f=>f.movieId),[2,3,4,5,6]);
  w.widget.confirmed([2,3,4,5,6]);assert.equal(w.widget.items.length,0);
});
test('sem resultados ou falha preserva seleção e campo editável',async()=>{
  const w=setup(async()=>[]);results(w,[film(1)]);w.widget.choose(0);w.input.value='Nada';w.input.emit('input');await w.fire();assert.equal(w.widget.items.length,1);assert.match(w.status.textContent,/Nenhum/);
  w.widget.fetchSuggestions=async()=>{throw Error('offline');};w.input.value='Outro';w.input.emit('input');await w.fire();assert.equal(w.input.disabled,false);assert.equal(w.widget.items.length,1);assert.match(w.status.textContent,/Não foi possível/);
});

// Exercita também o bootstrap e o fetch da página, além da classe isolada.
const fs=require('fs'),vm=require('vm'),path=require('path');
function fullPage({missingScript=false,oldServer=false,protocol='http:',response=null,requestHandler=null}={}){
  const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
  const timers=[],nodes=new Map();
  const doc={createElement(tag){const e=new Element(doc);e.tagName=tag;e.dataset={};e.querySelectorAll=()=>[];e.prepend=(...n)=>e.children.unshift(...n);return e;},querySelector:s=>nodes.get(s),querySelectorAll:()=>[]};
  doc.focusListeners=new Set();doc.addEventListener=(t,f)=>{if(t==='focusin')doc.focusListeners.add(f)};doc.removeEventListener=(t,f)=>doc.focusListeners.delete(f);doc.body=doc.createElement('body');doc.activeElement=doc.body;
  for(const [,id] of html.matchAll(/\bid="([^"]+)"/g)){const e=doc.createElement();e.id=id;nodes.set('#'+id,e);}
  const state=response||{mensagem:'Pronto',assistidos:[],referencias:[],recomendacoes:[]};
  const calls=[];
  const context={console,location:{protocol},AbortController,queueMicrotask,Option:function(text,value){const o=doc.createElement('option');o.textContent=text;o.value=value;return o;},setTimeout:fn=>{timers.push(fn);return fn;},clearTimeout:fn=>{const i=timers.indexOf(fn);if(i>=0)timers.splice(i,1);},document:doc,IntersectionObserver:class{observe(){}unobserve(){}},fetch:async(url,options={})=>{const data=options.body?JSON.parse(options.body):null;if(data)calls.push(data);return {ok:!oldServer||!url.startsWith('/api/filmes'),status:oldServer&&url.startsWith('/api/filmes')?404:200,json:async()=>url.startsWith('/api/filmes')?{sugestoes:[film(1,'Toy Story (1995)')]}:requestHandler?requestHandler(data):state}}};
  context.window=context;vm.createContext(context);
  // Timers nativos de Window exigem o receptor correto; Node não impõe essa regra.
  context.__schedule=fn=>{timers.push(fn);return fn;};
  context.__cancel=fn=>{const i=timers.indexOf(fn);if(i>=0)timers.splice(i,1);};
  vm.runInContext(`window.setTimeout=function(fn){if(this!==window)throw new TypeError('Illegal invocation: setTimeout');return window.__schedule(fn);};window.clearTimeout=function(fn){if(this!==window)throw new TypeError('Illegal invocation: clearTimeout');return window.__cancel(fn);};`,context);
  if(!missingScript)vm.runInContext(fs.readFileSync(path.join(__dirname,'static/autocomplete.js'),'utf8'),context);
  const inline=html.match(/<script>([\s\S]*?)<\/script>/)[1];vm.runInContext(inline,context);
  return {context,nodes,timers,calls};
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
test('HTML aberto como arquivo orienta usar o servidor e não chama a API',()=>{
  const p=fullPage({missingScript:true,protocol:'file:'});
  assert.equal(p.nodes.get('#titles').disabled,true);
  assert.equal(p.nodes.get('#confirm-selection').disabled,true);
  assert.match(p.nodes.get('#search-status').textContent,/http:\/\/127\.0\.0\.1:8000/);
  assert.deepEqual(p.calls,[]);
});
test('página com backend antigo orienta reiniciar o servidor sem perder seleção',async()=>{
  const p=fullPage({oldServer:true});await new Promise(r=>setImmediate(r));
  const input=p.nodes.get('#titles');input.value='Toy';input.emit('input');await p.timers.shift()();
  assert.match(p.nodes.get('#search-status').textContent,/Ctrl\+C/);
  assert.match(p.nodes.get('#search-status').textContent,/Ctrl\+Shift\+R/);
  assert.equal(input.disabled,false);
});

function profile(){const f=film(1,'Filme de referência (2000)');return {mensagem:'Pronto',assistidos:[f],referencias:[f],recomendacoes:[]};}



const tick=()=>new Promise(r=>setImmediate(r));
async function confirmation({fail=false}={}){
 let resolve;const p=fullPage({requestHandler:d=>d.acao==='confirmar_selecao'?new Promise(r=>resolve=r):profile()});await tick();
 vm.runInContext('autocomplete.items=[{movieId:2,titulo:"Filme sintético"}]',p.context);
 const button=p.nodes.get('#confirm-selection');button.focus();
 const pending=p.nodes.get('#search').onsubmit({preventDefault(){}});await tick();
 p.context.document.activeElement=p.context.document.body;
 return {p,button,pending,finish:()=>resolve(fail?Promise.reject(Error('falha sintética')):profile())};
}
test('UX02 confirmação bem-sucedida foca título estável do perfil',async()=>{
 const c=await confirmation();c.finish();await c.pending;
 assert.equal(c.p.context.document.activeElement,c.p.nodes.get('#profile-title'));
 assert.equal(c.p.context.document.focusListeners.size,0);
});
test('UX02 falha restaura confirmação e mantém mensagem de erro',async()=>{
 const c=await confirmation({fail:true});c.finish();await c.pending;
 assert.equal(c.p.context.document.activeElement,c.button);assert.match(c.p.nodes.get('#status').textContent,/falha sintética/);
});
test('UX02 não rouba foco se usuário navega durante confirmação',async()=>{
 const c=await confirmation();const other=c.p.nodes.get('#titles');other.focus();c.finish();await c.pending;
 assert.equal(c.p.context.document.activeElement,other);
});
test('UX02 registra navegação mesmo se foco depois volta ao body',async()=>{
 const c=await confirmation();c.p.nodes.get('#titles').focus();c.p.context.document.activeElement=c.p.context.document.body;c.finish();await c.pending;
 assert.equal(c.p.context.document.activeElement,c.p.context.document.body);
});


test('título brasileiro é exibido com original e mantém ID ao selecionar',()=>{
 const w=setup();const f={...film(42,'Original (2000)'),titulo_br:'Nome Brasileiro (2000)',titulo_original:'Original (2000)'};
 results(w,[f]);
 const text=w.list.children[0].children[1];
 assert.equal(text.textContent,'Nome Brasileiro (2000)');
 assert.equal(text.children[0].textContent,'Original (2000)');
 w.input.emit('keydown',{key:'ArrowDown'});w.input.emit('keydown',{key:'Enter'});
 assert.equal(w.widget.items[0].movieId,42);
 assert.equal(w.widget.items[0].titulo,'Original (2000)');
 assert.match(w.selected.children[0].children[0].textContent,/Nome Brasileiro/);
});

test('fluxo essencial confirma, mostra sugestões e permite nova seleção',async()=>{
 const empty={mensagem:'Selecione filmes',assistidos:[],referencias:[],recomendacoes:[]};
 const ref=film(1,'Referência (2000)');
 const rec={...film(2,'Sugestão (2001)'),generos:'Drama',nota_media_treino:4,avaliacoes_treino:5,motivo:'Gênero em comum'};
 const p=fullPage({requestHandler:d=>d.acao==='confirmar_selecao'?{mensagem:'Confirmada',assistidos:[ref],referencias:[ref],recomendacoes:[rec]}:empty});
 await tick();vm.runInContext('autocomplete.items=[{movieId:1,titulo:"Referência (2000)"}]',p.context);
 await p.nodes.get('#search').onsubmit({preventDefault(){}});
 assert.equal(p.calls.at(-1).acao,'confirmar_selecao');assert.equal(p.nodes.get('#cards').children.length,1);
 assert.equal(p.nodes.get('#refs').children.length,1);
 assert.equal(vm.runInContext('autocomplete.items.length',p.context),0);
 await p.nodes.get('#reset').onclick();
 assert.equal(p.calls.at(-1).acao,'reiniciar');assert.equal(p.nodes.get('#cards').children.length,0);
});
test('pôster aceita URL TMDB válida e falha de imagem retorna ao placeholder',async()=>{
 const p=fullPage();await tick();
 const img=vm.runInContext('poster({movieId:1,titulo:"Referência"})',p.context);
 assert.equal(img.src,'/static/poster-placeholder.svg');
 img.src='https://image.tmdb.org/t/p/w342/imagem.jpg';img.onerror();
 assert.equal(img.src,'/static/poster-placeholder.svg');assert.match(img.alt,/indisponível/);
});
