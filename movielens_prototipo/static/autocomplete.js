/* Catálogo local; os pôsteres são um enriquecimento independente. Sem dependências. */
(function(root){
'use strict';
class MovieAutocomplete {
  constructor({input,list,selected,status,fetchSuggestions,poster,existing=()=>[],references=()=>[],delay=300,setTimer=(fn,ms)=>root.setTimeout(fn,ms),clearTimer=id=>root.clearTimeout(id),clearOptions=()=>list.replaceChildren()}) {
    Object.assign(this,{input,list,selected,status,fetchSuggestions,poster,existing,references,delay,setTimer,clearTimer,clearOptions});
    this.items=[];this.results=[];this.active=-1;this.sequence=0;this.timer=null;this.controller=null;
    input.addEventListener('input',()=>this.search());
    input.addEventListener('keydown',e=>this.key(e));
    input.addEventListener('blur',()=>this.dismiss());
    this.renderSelection();
  }
  invalidate(){this.sequence++;if(this.timer!==null)this.clearTimer(this.timer);this.timer=null;if(this.controller)this.controller.abort();this.input.setAttribute('aria-busy','false');}
  hide(){this.list.hidden=true;this.input.setAttribute('aria-expanded','false');this.input.removeAttribute('aria-activedescendant');this.active=-1;}
  dismiss(){this.invalidate();this.hide();}
  search(){
    this.invalidate();this.hide();this.results=[];
    const query=this.input.value.trim(),version=this.sequence;
    if(query.length<2){this.status.textContent='Digite pelo menos 2 caracteres para buscar.';return;}
    this.status.textContent='Aguardando digitação…';
    this.timer=this.setTimer(async()=>{
      this.controller=new AbortController();this.input.setAttribute('aria-busy','true');this.status.textContent='Buscando no catálogo…';
      try{
        const values=await this.fetchSuggestions(query,this.controller.signal);
        if(version!==this.sequence)return;
        this.results=values.slice(0,8);this.show();
        this.status.textContent=this.results.length?this.results.length+' sugestões. Confira o título e o ano; use as setas e Enter para escolher.':'Nenhum filme encontrado. Corrija a busca ou tente o título em inglês; sua seleção foi mantida.';
      }catch(error){if(version===this.sequence&&error.name!=='AbortError'){this.results=[];this.hide();this.status.textContent=error.userMessage||'Não foi possível buscar. Continue digitando para tentar novamente; sua seleção foi mantida.';}}
      finally{if(version===this.sequence)this.input.setAttribute('aria-busy','false');}
    },this.delay);
  }
  show(){
    this.clearOptions();this.active=-1;this.input.removeAttribute('aria-activedescendant');
    this.results.forEach((film,index)=>{
      const option=this.list.ownerDocument.createElement('li');option.id=this.list.id+'-'+index;option.setAttribute('role','option');option.setAttribute('aria-selected','false');
      option.append(this.poster(film,true));
      const text=this.list.ownerDocument.createElement('span');
      const title=film.titulo_br||film.titulo;
      const year=film.ano&&!title.includes('('+film.ano+')')?' ('+film.ano+')':'';
      text.textContent=title+year+(film.correspondencia==='aproximada'?' · título aproximado':'');
      if(film.titulo_br&&film.titulo_original){
        const original=this.list.ownerDocument.createElement('small');
        original.className='original-title';
        original.textContent=film.titulo_original;
        text.append(original);
      }
      option.append(text);
      option.addEventListener('pointerdown',e=>e.preventDefault());
      option.addEventListener('click',()=>this.choose(index));this.list.append(option);
    });
    this.list.hidden=!this.results.length;this.input.setAttribute('aria-expanded',String(!!this.results.length));
  }
  highlight(index){
    this.active=index;Array.from(this.list.children).forEach((option,i)=>option.setAttribute('aria-selected',String(i===index)));
    const option=this.list.children[index];if(option){this.input.setAttribute('aria-activedescendant',option.id);option.scrollIntoView({block:'nearest'});}
  }
  key(event){
    if(event.isComposing)return;
    if(event.key==='Escape'){event.preventDefault();this.dismiss();return;}
    if(event.key==='Enter'){event.preventDefault();if(!this.list.hidden&&this.active>=0)this.choose(this.active);return;}
    if((event.key==='ArrowDown'||event.key==='ArrowUp')&&this.results.length){
      event.preventDefault();this.list.hidden=false;this.input.setAttribute('aria-expanded','true');
      const step=event.key==='ArrowDown'?1:-1;
      const next=this.active<0?(step===1?0:this.results.length-1):(this.active+step+this.results.length)%this.results.length;this.highlight(next);
    }
  }
  choose(index){
    const film=this.results[index];if(!film)return;
    if(this.items.some(f=>f.movieId===film.movieId)||this.existing().some(f=>f.movieId===film.movieId)){
      this.status.textContent='Esse filme já está selecionado ou registrado como assistido.';this.input.focus();return;
    }
    if(this.items.length>=5){this.status.textContent='Você já selecionou cinco filmes. Remova um antes de escolher outro.';this.input.focus();return;}
    this.items.push(film);this.dismiss();this.results=[];this.input.value='';this.renderSelection();this.status.textContent=film.titulo+' adicionado. Você pode inserir outro filme ou confirmar a seleção.';this.input.focus();
  }
  renderSelection(){
    this.selected.replaceChildren();
    this.items.forEach((film,index)=>{
      const li=this.selected.ownerDocument.createElement('li');
      const text=this.selected.ownerDocument.createElement('span');text.textContent=(film.titulo_br||film.titulo)+' · '+'Referência ao confirmar';
      const remove=this.selected.ownerDocument.createElement('button');remove.type='button';remove.textContent='Remover';remove.setAttribute('aria-label','Remover '+film.titulo+' da seleção');
      remove.onclick=()=>{this.items=this.items.filter(f=>f.movieId!==film.movieId);this.renderSelection();this.status.textContent=film.titulo+' removido da seleção a confirmar.';this.input.focus();};li.append(text,remove);this.selected.append(li);
    });
  }
  confirmed(ids=null){if(ids){this.items=this.items.filter(f=>!ids.includes(f.movieId));this.renderSelection();return;}this.items=[];this.renderSelection();this.dismiss();this.results=[];this.input.value='';}
  reset(){this.confirmed();this.status.textContent='Digite pelo menos 2 caracteres para buscar filmes.';}
}
if(typeof module!=='undefined'&&module.exports)module.exports=MovieAutocomplete;
else root.MovieAutocomplete=MovieAutocomplete;
})(typeof window!=='undefined'?window:globalThis);
