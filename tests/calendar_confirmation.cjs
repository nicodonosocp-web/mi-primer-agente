const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '..', 'realtime.html'), 'utf8');
const start = html.indexOf('function confirmarCreacionEvento(');
const end = html.indexOf('async function procesarEvento(', start);
const code = html.slice(start, end);
async function scenario(approved, modelFlag) {
 const sent=[],posts=[];let confirmations=0;
 const ctx={confirm:()=>{confirmations++;return approved;},dc:{readyState:'open',send:x=>sent.push(JSON.parse(x))},
  estadoAvatar:()=>{},registrarActividad:()=>{},activarTab:()=>{},mostrarError:()=>{},cargarAgenda:async()=>{},
  fetch:async(url,options)=>{
   const body=JSON.parse(options.body);posts.push({url,body});
   return {json:async()=>url==='/calendar/proposals'?{ok:true,propuesta_id:'proposal-id',evento:body}:{ok:approved,cancelado_por_usuario:!approved}};
  }};
 vm.createContext(ctx);vm.runInContext(code,ctx);
 await ctx.ejecutarTool({name:'crear_evento_calendar',call_id:'test',arguments:JSON.stringify({titulo:'Sintético',inicio_iso:'2026-10-05T10:00:00-03:00',fin_iso:'2026-10-05T11:00:00-03:00',usuario_autorizo_creacion:modelFlag})});
 assert.equal(confirmations,1);assert.equal(posts.length,2);
 assert.equal(posts[0].url,'/calendar/proposals');assert.equal(posts[1].url,'/calendar/confirm');
 assert.deepEqual(posts[1].body,{propuesta_id:'proposal-id',confirmar:approved});
 if(!approved)assert.equal(JSON.parse(sent[0].item.output).cancelado_por_usuario,true);
}
(async()=>{await scenario(false,true);await scenario(false,false);await scenario(true,false);console.log('3 escenarios Calendar: OK');})().catch(e=>{console.error(e);process.exitCode=1});
