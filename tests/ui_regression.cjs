const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
 const browser=await chromium.launch({headless:true, executablePath:process.env.CHROME_EXECUTABLE || undefined, args:process.env.CHROME_EXECUTABLE ? ["--no-sandbox", "--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader", "--single-process"] : []});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE',e.message);});
 await page.addInitScript(() => {
   window.micCalls=0; window.stopped=0; window.sent=[];
   const media={getUserMedia:async()=>{window.micCalls++;const track={kind:'audio',stop:()=>window.stopped++};return {getAudioTracks:()=>[track],getTracks:()=>[track]};}};
   Object.defineProperty(navigator,'mediaDevices',{value:media});
   window.RTCPeerConnection=class {
     constructor(){this.sender={track:null,replaceTrack:async t=>{this.sender.track=t}};}
     addTransceiver(){return {sender:this.sender};}
     getSenders(){return [this.sender];}
     createDataChannel(){this.channel={readyState:'connecting',send:x=>window.sent.push(JSON.parse(x)),close(){this.readyState='closed'}};return this.channel;}
     async createOffer(){return {type:'offer',sdp:'synthetic'};}
     async setLocalDescription(){}
     async setRemoteDescription(){this.channel.readyState='open';this.channel.onopen();}
     close(){}
   };
 });
 const posts=[];
 await page.route('**/*', async route=>{
   const url=new URL(route.request().url());
   if(url.hostname==='api.openai.com')return route.fulfill({status:200,body:'synthetic-sdp'});
   if(url.origin!=='http://localhost:8000')return route.abort();
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'..','realtime.html'),'utf8')});
   const req=route.request(); if(req.method()==='POST')posts.push({path:url.pathname,body:req.postDataJSON()});
   const results={
    '/session':{csrf:'synthetic'},'/health':{status:'ok',version:'2.4-rc1',rag_documents:1,rag_fragments:2},
    '/conversations':{ok:true,result:[{id:1,titulo:'Conversación de prueba'}]},
    '/library':{ok:true,documentos:[{archivo:'Acta de prueba.pdf',origen:'local',indexado:true,fragmentos:2}]},
    '/conversation/start':{ok:true,conversacion_id:2},'/conversation/message':{ok:true,guardado:true},
    '/token':{value:'synthetic'},'/calendar/events':{ok:true,result:[]},
    '/calendar/proposals':{ok:true,propuesta_id:'test-proposal',evento:{titulo:'Prueba',inicio_iso:'2026-10-06T10:00:00-03:00',fin_iso:'2026-10-06T11:00:00-03:00'}},
    '/calendar/confirm':{ok:false,cancelado_por_usuario:true}
   };
   return route.fulfill({contentType:'application/json',body:JSON.stringify(results[url.pathname]||{ok:true,result:[]})});
 });
 await page.goto('http://localhost:8000');
 await page.locator('.file-card').waitFor();
 await page.locator('#textoMensaje').fill('Mensaje de prueba');await page.locator('#enviarTexto').click();
 await page.waitForFunction(()=>window.sent.some(x=>x.type==='response.create'));
 assert.equal(await page.evaluate(()=>window.micCalls),0,'Texto no debe abrir micrófono');
 assert.equal(await page.locator('.message.user').last().innerText(),'Tú\nMensaje de prueba');
 await page.locator('[data-section="agenda"]').click();await page.locator('[data-section="inicio"]').click();
 assert.equal(await page.locator('.message.user').count(),1,'Navegación conserva chat');
 await page.locator('#conectar').click();await page.waitForFunction(()=>window.micCalls===1);
 await page.locator('#desconectar').click();assert.equal(await page.evaluate(()=>window.stopped),1);
 page.on('dialog',dialog=>dialog.dismiss());
 await page.evaluate(async()=>{
   dc={readyState:'open',send:()=>{}};
   await ejecutarTool({name:'crear_evento_calendar',call_id:'fake',arguments:JSON.stringify({titulo:'Prueba',inicio_iso:'2026-10-06T10:00:00-03:00',fin_iso:'2026-10-06T11:00:00-03:00',usuario_autorizo_creacion:true})});
 });
 assert.equal(posts.find(x=>x.path==='/calendar/confirm').body.confirmar,false);
 assert.ok(!posts.some(x=>x.path==='/tool'&&x.body.name==='crear_evento_calendar'));
 for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[1024,768],[768,1024],[390,844]]){
   await page.setViewportSize({width,height});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight),true,`${width}: vertical overflow`);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${width}: horizontal overflow`);
   const box=await page.locator('#enviarTexto').boundingBox();assert.ok(box.y+box.height<=height);
 }
 await page.setViewportSize({width:1440,height:900});
 if(process.env.GRIFO_SCREENSHOT) await page.screenshot({path:process.env.GRIFO_SCREENSHOT,fullPage:true});
 assert.deepEqual(errors,[]);
 await browser.close();console.log('UI: texto sin micrófono, voz, navegación, cancelación Calendar y 6 resoluciones: OK');
})().catch(e=>{console.error(e);process.exit(1)});
