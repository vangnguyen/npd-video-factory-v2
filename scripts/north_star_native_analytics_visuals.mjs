// Render actual saved HTTP observations through the same Studio chart functions.
// DOM serialization is a component test; it is not browser/non-developer UAT.
import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';import {fileURLToPath} from 'node:url';
import {nativeAnalyticsChart,renderNativeAnalyticsChart} from '../apps/studio-web/native-analytics.mjs';
const [input,destination]=process.argv.slice(2),repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
if(!input||!destination)throw new Error('Exact input and fresh external output required');
const out=path.resolve(destination),source=path.resolve(input),parent=path.dirname(out);
if(out.startsWith(repo+path.sep)||path.basename(source)!=='analytics-page.json'||path.dirname(source)!==parent||!/^visuals(?:-r[2-9][0-9]*)?$/.test(path.basename(out))||fs.existsSync(out))throw new Error('Fresh component artifact folder beside retained HTTP page required');
const raw=fs.readFileSync(source),page=JSON.parse(raw);
if(page.schema_version!=='native-analytics-page-v1'||page.workspace_id!=='wsp_native_storyboard_full_qc_fixture'||page.external_call!==false||page.next_cursor!==null)throw new Error('Exact retained complete fixture page required');
for(const row of page.items){if(row.workspace_id!==page.workspace_id||row.project_id!==page.project_id||row.external_call!==false)throw new Error('Foreign observation');
  if(row.snapshot&&(row.snapshot.mock!==true||row.snapshot.evidence.real_audience_observation!==false))throw new Error('Explicit synthetic observations required');}
class Node{constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.textContent='';}
  setAttribute(k,v){this.attributes[k]=String(v);}append(...values){this.children.push(...values);}replaceChildren(...values){this.children=values;}}
const root={createElement:tag=>new Node(tag),createElementNS:(_,tag)=>new Node(tag)};
const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const serialize=node=>`<${node.tag}${Object.entries(node.attributes).map(([k,v])=>` ${k}="${escape(v)}"`).join('')}${node.className?` class="${escape(node.className)}"`:''}>${escape(node.textContent)}${node.children.map(serialize).join('')}</${node.tag}>`;
const nodes=node=>[node,...node.children.flatMap(nodes)],sha=value=>crypto.createHash('sha256').update(value).digest('hex');
fs.mkdirSync(out);const models={},sections=[];
for(const metric of ['views','completion_rate','watch_time','revenue']){const model=nativeAnalyticsChart(page.items,metric),container=new Node('section');
  renderNativeAnalyticsChart(root,container,model);models[metric]=model;
  const svg=nodes(container).find(n=>n.tag==='svg');if(svg){svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('font-family','Segoe UI,Arial,sans-serif');
    fs.writeFileSync(path.join(out,metric+'.svg'),serialize(svg),{flag:'wx'});}
  fs.writeFileSync(path.join(out,metric+'-model.json'),JSON.stringify(model,null,2)+'\n',{flag:'wx'});sections.push(serialize(container));
}
if(models.views.shown_count!==4||models.views.series.length!==1||models.revenue.points.filter(p=>p.value===null).length!==3||models.completion_rate.series[0].segments.length!==2)throw new Error('Actual persisted fixture values/gaps changed');
const subset=page.items.filter(row=>row.request.fixture_profile==='insufficient_data'),unknown=nativeAnalyticsChart(subset,'revenue'),missing=new Node('section');
renderNativeAnalyticsChart(root,missing,unknown);if(unknown.shown_count!==1||unknown.plotted_known_count!==0||nodes(missing).some(n=>n.tag==='svg'))throw new Error('Missing metric became a graph');
fs.writeFileSync(path.join(out,'all-null-revenue-model.json'),JSON.stringify({scope:'explicit_insufficient_data_fixture_subset',model:unknown},null,2)+'\n',{flag:'wx'});
sections.push(serialize(missing));
const css=fs.readFileSync(path.join(repo,'apps/studio-web/native.css'),'utf8').split('\n').filter(line=>line.startsWith('.native-analytics-')).join('\n');
const html=`<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Analytics component evidence · fixture</title><style>body{font:15px 'Segoe UI',Arial,sans-serif;margin:24px auto;padding:0 20px;max-width:1100px;color:#244a36}section{border:1px solid #dce5dd;padding:18px;margin:22px 0;border-radius:12px}p,li{overflow-wrap:anywhere}pre{white-space:pre-wrap} ${css}</style><h1>Analytics · bằng chứng component từ HTTP đã lưu</h1><p>Dữ liệu mẫu có xác nhận. Các mẫu winner/thiếu dữ liệu/kém là các tình huống kiểm tra riêng, không phải diễn biến khán giả thật. Chưa xác nhận browser hoặc Owner UAT.</p>${sections.join('\n')}</html>`;
fs.writeFileSync(path.join(out,'component-evidence.html'),html,{flag:'wx'});
const files=Object.fromEntries(fs.readdirSync(out).map(name=>{const data=fs.readFileSync(path.join(out,name));return [name,{sha256:sha(data),bytes:data.length}];}));
const receipt={schema:'native-analytics-component-render-v1',input_sha256:sha(raw),frontend_source_sha256:sha(fs.readFileSync(path.join(repo,'apps/studio-web/native-analytics.mjs'))),
  script_source_sha256:sha(fs.readFileSync(fileURLToPath(import.meta.url))),saved_observations:4,metrics:['views','completion_rate','watch_time','revenue'],
  all_null_revenue_subset_graph_absent:true,revenue_missing_values_preserved:true,completion_gaps_preserved:true,component_dom_rendered:true,browser_uat:false,owner_uat:false,provider_calls:0,files};
fs.writeFileSync(path.join(out,'render-receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});process.stdout.write(JSON.stringify({status:'COMPONENT_RENDER_PASS',observations:4,svg:4,files:Object.keys(files).length}));
