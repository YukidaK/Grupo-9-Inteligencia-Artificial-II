/* Preferências de sessão. Não consulta TMDB nem filtra recomendações. */
(function(root){
'use strict';
class StreamingPreferencesUI {
  constructor({form,grid,services,modes,restricted,flexible,save,count,status,empty,retry,load,send}){
    Object.assign(this,{form,grid,services,modes,restricted,flexible,save,count,status,empty,retry,load,send});
    this.pendingIds=new Set();this.selected=new Set();this.checks=[];this.revision=0;this.sequence=0;this.busy=false;this.loaded=false;
    this.form.onsubmit=e=>{e.preventDefault();return this.salvar()};
    this.retry.onclick=()=>this.carregar();
    for(const radio of [restricted,flexible])radio.addEventListener('change',()=>this.changed());
    this.updateCount();
  }
  changed(){this.revision++;this.updateCount();this.status.textContent='Alterações não salvas.';}
  updateCount(){const pending=[...this.selected].filter(i=>this.pendingIds.has(i)).length,n=this.selected.size-pending;this.count.textContent=n+' '+(n===1?'serviço selecionado':'serviços selecionados')+(pending?' · '+pending+' ID(s) fora do catálogo para revisão':'');}
  validate(d){
    if(!d||d.integracao_ativa!==false||!d.catalogo||d.catalogo.regiao!=='BR'||!Array.isArray(d.catalogo.provedores))throw Error('Resposta de preferências inválida.');
    const ids=new Set();
    for(const p of d.catalogo.provedores){if(!Number.isSafeInteger(p.id)||p.id<=0||ids.has(p.id)||typeof p.nome!=='string'||!p.nome.trim())throw Error('Catálogo inválido.');ids.add(p.id);}
    const p=d.preferencias;
    if(p&&(!Array.isArray(p.provedores)||p.provedores.some(i=>!Number.isSafeInteger(i)||i<=0)||new Set(p.provedores).size!==p.provedores.length||p.regiao!=='BR'||p.ativo!==false||!['restrito','flexivel'].includes(p.modo)))throw Error('Preferências incompatíveis com o catálogo.');
    const missing=p?p.provedores.filter(i=>!ids.has(i)).sort((a,b)=>a-b):[];
    const reconciliation=d.reconciliacao;
    if(reconciliation){
      const listed=reconciliation.provedores_ausentes;
      if(!Array.isArray(listed)||JSON.stringify(listed)!==JSON.stringify(missing)||reconciliation.revisao_necessaria!==(missing.length>0))throw Error('Reconciliação inválida.');
    }else if(missing.length)throw Error('Preferências incompatíveis com o catálogo.');
    return d;
  }
  render(d){
    const p=d.preferencias;this.selected=new Set(p?p.provedores:[]);this.pendingIds=new Set(d.reconciliacao?.provedores_ausentes||[]);this.checks=[];this.grid.replaceChildren();
    for(const provider of [...d.catalogo.provedores,...[...this.pendingIds].map(id=>({id,nome:`Provedor ID ${id} — fora do catálogo; desmarque e salve para remover.`}))]){
      const label=this.grid.ownerDocument.createElement('label'),input=this.grid.ownerDocument.createElement('input'),name=this.grid.ownerDocument.createElement('span');
      input.type='checkbox';input.value=String(provider.id);input.id='streaming-provider-'+provider.id;
      input.checked=this.selected.has(provider.id);input.setAttribute('aria-describedby','streaming-notice');
      name.textContent=provider.nome;label.htmlFor=input.id;label.className='streaming-choice';label.append(input,name);
      input.addEventListener('change',()=>{if(input.checked)this.selected.add(provider.id);else this.selected.delete(provider.id);this.changed()});
      this.grid.append(label);this.checks.push(input);
    }
    this.restricted.checked=!p||p.modo==='restrito';this.flexible.checked=!!p&&p.modo==='flexivel';
    this.empty.hidden=d.catalogo.provedores.length>0;this.services.hidden=!this.checks.length;this.services.disabled=false;this.modes.disabled=false;this.updateCount();
  }
  async carregar(){
    const focoRetry=this.form.ownerDocument.activeElement===this.retry;
    const seq=++this.sequence;this.busy=true;this.loaded=false;this.save.disabled=true;this.retry.hidden=true;this.services.disabled=true;this.modes.disabled=true;
    this.status.textContent='Carregando preferências…';
    try{const d=this.validate(await this.load());if(seq!==this.sequence)return;this.render(d);this.loaded=true;this.status.textContent=d.mensagem||'Preferências da sessão carregadas.';}
    catch(e){if(seq!==this.sequence)return;this.retry.hidden=false;this.status.textContent='Não foi possível carregar os serviços. Você pode continuar escolhendo filmes.';}
    finally{if(seq===this.sequence){this.busy=false;this.save.disabled=!this.loaded;const doc=this.form.ownerDocument;if(this.loaded&&focoRetry&&(!doc.activeElement||doc.activeElement===doc.body))(this.checks[0]||this.restricted).focus();}}
  }
  async salvar(){
    if(this.busy||!this.loaded)return;
    const seq=++this.sequence,revision=this.revision,doc=this.form.ownerDocument,foco=doc.activeElement;
    this.busy=true;this.save.disabled=true;this.status.textContent='Salvando preferências…';
    const pedido={acao:'salvar',regiao:'BR',provedores:[...this.selected].sort((a,b)=>a-b),modo:this.flexible.checked?'flexivel':'restrito'};
    const removed=[...this.pendingIds].filter(id=>!this.selected.has(id));
    if(removed.length)pedido.remover_incompativeis=removed;
    try{const data=this.validate(await this.send(pedido));if(seq!==this.sequence)return;
      if(revision===this.revision){
        // Remove somente rótulos históricos confirmados; mantém DOM/foco dos demais.
        for(const input of this.checks.filter(c=>removed.includes(Number(c.value))))input.parentElement.remove();
        this.checks=this.checks.filter(c=>!removed.includes(Number(c.value)));
        this.pendingIds=new Set(data.reconciliacao?.provedores_ausentes||[]);
        this.services.hidden=!this.checks.length;this.updateCount();
      }
      this.status.textContent=revision===this.revision?(data.mensagem||'Preferências salvas nesta sessão. A seleção ainda não altera as recomendações.'):'Preferências anteriores salvas; há alterações não salvas.';
    }catch(e){if(seq===this.sequence)this.status.textContent='Não foi possível salvar. Suas seleções foram mantidas; tente novamente.';}
    finally{if(seq===this.sequence){this.busy=false;this.save.disabled=false;if(foco===this.save&&(!doc.activeElement||doc.activeElement===doc.body))this.save.focus();}}
  }
}
if(typeof module!=='undefined'&&module.exports)module.exports=StreamingPreferencesUI;
if(root)root.StreamingPreferencesUI=StreamingPreferencesUI;
})(typeof window!=='undefined'?window:null);
