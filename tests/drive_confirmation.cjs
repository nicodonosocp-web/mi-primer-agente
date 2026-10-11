const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '..', 'realtime.html'), 'utf8');
const code = html.slice(html.indexOf('function confirmarCreacionEvento('), html.indexOf('async function procesarEvento('));
async function scenario(approved, modelFlag) {
    const posts=[],sent=[]; let confirmations=0,refreshes=0;
    const ctx = {
        confirm: text => {assert.match(text,/Nombre verificado.pdf/);assert.match(text,/OpenAI/);confirmations++;return approved;},
        dc: {readyState:'open',send: x=>sent.push(JSON.parse(x))},
        registrarActividad:()=>{},mostrarError:()=>{},
        cargarBiblioteca:async()=>{refreshes++;},
        fetch: async(url,opts)=>{
            const body=JSON.parse(opts.body);posts.push({url,body});
            return {json:async()=>url==='/drive/proposals' ?
                {propuesta_id:'proposal',archivo:{nombre:'Nombre verificado.pdf'}} :
                {ok:approved,cancelado_por_usuario:!approved}};
        }
    };
    vm.createContext(ctx);vm.runInContext(code,ctx);
    await ctx.ejecutarTool({name:'indexar_drive',call_id:'call',arguments:JSON.stringify({file_id:'real-id',usuario_autorizo_indexacion:modelFlag})});
    assert.equal(confirmations,1);
    assert.deepEqual(posts,[{url:'/drive/proposals',body:{file_id:'real-id'}},
        {url:'/drive/confirm',body:{propuesta_id:'proposal',confirmar:approved}}]);
    assert.equal(refreshes,approved?1:0);
    assert.equal(JSON.parse(sent[0].item.output).ok,approved);
    assert.equal(sent[1].type,'response.create');
}
(async()=>{await scenario(false,true);await scenario(true,false);console.log('2 escenarios confirmación Drive: OK');})().catch(e=>{console.error(e);process.exitCode=1;});
