// Minimal DOM contract fixture; never browser QA.
export class Node {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.parentNode=null;this.attributes={};this.dataset={};this.listeners={};this.value='';this.hidden=false;this.textContent='';this.style={setProperty(){}};const names=new Set();this.classList={add:x=>names.add(x),remove:x=>names.delete(x),contains:x=>names.has(x),toggle:(x,on)=>on?names.add(x):names.delete(x)};}
  setAttribute(k,v){this.attributes[k]=String(v);if(k==='id')this.id=v;if(k==='class'){this.className=v;for(const x of v.split(' '))this.classList.add(x);}if(k==='value')this.value=v;if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;}
  removeAttribute(k){delete this.attributes[k];}getAttribute(k){return this.attributes[k]??null;}
  remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(v=>v!==this);this.parentNode=null;}
  append(...nodes){for(const n of nodes){n.remove();n.parentNode=this;this.children.push(n);}}
  prepend(n){n.remove();n.parentNode=this;this.children.unshift(n);}
  before(n){const p=this.parentNode;n.remove();n.parentNode=p;p.children.splice(p.children.indexOf(this),0,n);}
  replaceChildren(...nodes){for(const n of this.children)n.parentNode=null;this.children=[];this.append(...nodes);}
  addEventListener(name,fn){this.listeners[name]=fn;}focus(){this.focused=true;}scrollIntoView(){}
  pause(){this.paused=true;}play(){this.paused=false;return Promise.resolve();}
  descendants(){return this.children.flatMap(n=>[n,...n.descendants()]);}
  matches(s){if(s.startsWith('#'))return this.id===s.slice(1);if(s.startsWith('.'))return this.classList.contains(s.slice(1));const a=/^\[([^=\]]+)(?:="?([^"\]]+)"?)?\]$/.exec(s);if(a)return a[2]===undefined?this.getAttribute(a[1])!==null:this.getAttribute(a[1])===a[2];return this.tagName===s;}
  querySelectorAll(s){return this.descendants().filter(n=>s.split(',').some(x=>n.matches(x.trim())));}querySelector(s){return this.querySelectorAll(s)[0]??null;}
  closest(s){return this.matches(s)?this:this.parentNode?.closest(s)??null;}
}
export class Doc extends Node {constructor(){super('document');this.body=new Node('body');this.append(this.body);}createElement(tag){return new Node(tag);}getElementById(id){return this.descendants().find(n=>n.id===id)??null;}}
