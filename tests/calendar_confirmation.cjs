// Ejecuta las funciones reales del frontend con navegador y HTTP simulados.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '..', 'realtime.html'), 'utf8');
const start = html.indexOf('function confirmarCreacionEvento(');
const end = html.indexOf('async function procesarEvento(', start);
assert.ok(start >= 0 && end > start);
const code = html.slice(start, end);

async function scenario(approved, modelFlag) {
    const sent = [], posts = [];
    let confirmations = 0;
    const ctx = {
        confirm: () => { confirmations++; return approved; },
        dc: {send: value => sent.push(JSON.parse(value))},
        estadoAvatar: () => {}, registrarActividad: () => {}, activarTab: () => {},
        cargarAgenda: async () => {},
        fetch: async (url, options) => {
            posts.push({url, body: JSON.parse(options.body)});
            return {json: async () => ({ok: true, result: {id: 'synthetic'}})};
        }
    };
    vm.createContext(ctx);
    vm.runInContext(code, ctx);
    await ctx.ejecutarTool({name: 'crear_evento_calendar', call_id: 'test',
        arguments: JSON.stringify({titulo: 'Sintético', inicio_iso: '2026-10-05T10:00:00-03:00',
            fin_iso: '2026-10-05T11:00:00-03:00', usuario_autorizo_creacion: modelFlag})});
    assert.equal(confirmations, 1);
    if (!approved) {
        assert.equal(posts.length, 0, 'Cancelar nunca debe llamar al backend');
        assert.equal(JSON.parse(sent[0].item.output).cancelado_por_usuario, true);
    } else {
        assert.equal(posts.length, 1);
        assert.equal(posts[0].url, '/tool');
        assert.equal(posts[0].body.arguments.usuario_autorizo_creacion, true);
    }
}
(async () => {
    await scenario(false, true); // El modelo no puede saltarse el diálogo.
    await scenario(false, false);
    await scenario(true, false);
    console.log('3 escenarios de confirmación Calendar: OK (sin red)');
})().catch(error => { console.error(error); process.exitCode = 1; });
