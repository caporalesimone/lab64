/* c64-api.js: remote control API for VirtualC64 (window.c64).
   To be injected into the VirtualC64-vNN.html page AFTER loading (the c64d.js daemon does it by itself; by hand: paste into the console).
   Uses the page globals (frame, st, $, mountDisk, emu, ...). Documentation: C64-API.md
   Copyright © 2026 Simone Caporale */
const API_VERSION=Number('/*__API__*/');
(function(){
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const E=(code,msg)=>{ const e=new Error(msg); e.code=code; return e; };     // errors with a code: NOT_STARTED NOT_READY TIMEOUT BAD_ARG UNKNOWN_LABEL NO_STATE NO_SHOT CORE
  const W=()=>{ if(!frame||!st.running) throw E('NOT_STARTED','emulator not started: call c64.start()'); const w=frame.contentWindow; if(!w||typeof w.wasm_peek!=='function') throw E('NOT_READY','emulator not ready yet: call await c64.ready()'); if(!w.__trk) trkInstall(w); return w; };
  const toBytes=d=>{
    if(d instanceof Uint8Array) return d;
    if(Array.isArray(d)) return Uint8Array.from(d);
    if(typeof d==='string') return b64ToU8(d.replace(/^data:[^,]*,/,''));
    if(d&&d.buffer) return new Uint8Array(d.buffer);
    throw new Error('invalid data (Uint8Array, array or base64)');
  };
  // screen code -> testo
  function sc2txt(c,lower){
    const rev=c&0x80; c&=0x7f; let ch;
    if(c===0) ch='@'; else if(c<=26) ch=String.fromCharCode((lower?96:64)+c);
    else if(c===27) ch='['; else if(c===28) ch='£'; else if(c===29) ch=']'; else if(c===30) ch='↑'; else if(c===31) ch='←';
    else if(c<64) ch=String.fromCharCode(c);
    else if(c>=65&&c<=90&&lower) ch=String.fromCharCode(c); else ch='▒';
    return ch;
  }

  /* ---- basics: addresses, RAM view, core shell, freezing ---- */
  const FR=19656;                                   // cycles per PAL frame (63 x 312)
  let frozen=false, lastHalt=0, labels={}; const labelSets={default:labels};
  const hex=(v,n)=>(v>>>0).toString(16).toUpperCase().padStart(n||4,'0');
  const addr=a=>{
    if(typeof a==='number') return a&0xffff;
    const t=String(a).trim(); if(/^\$[0-9a-f]+$/i.test(t)) return parseInt(t.slice(1),16)&0xffff; if(/^0x[0-9a-f]+$/i.test(t)) return parseInt(t,16)&0xffff; if(/^\d+$/.test(t)) return (+t)&0xffff;
    if(t in labels) return labels[t]; { const ms=/^([\w-]+):(\S+)$/.exec(t); if(ms&&labelSets[ms[1]]&&ms[2] in labelSets[ms[1]]) return labelSets[ms[1]][ms[2]]; }
    throw E('UNKNOWN_LABEL','unknown address or label: '+t);
  };
  const withRam=f=>{ const w=W(), old=w.wasm_peek(1); w.wasm_poke(1,old&0xF8); try{ return f(); } finally{ w.wasm_poke(1,old); } };   // $01 = RAM everywhere, then restore
  const cyc=()=>Number(W().wasm_get_cpu_cycles());
  const setPausedUi=p=>{ st.paused=p; try{ $('bPause').textContent=p?'▶':'⏸'; $('bPause').classList.toggle('on',p); }catch(e){} };
  const halt=()=>{ W().wasm_halt(); frozen=true; lastHalt=performance.now(); setPausedUi(true); };
  // after a 30-250 ms pause the core "catches up" the lost frames (measured: up to +3): this wait avoids it
  const go=async(noGuard)=>{ const g=performance.now()-lastHalt; if(!noGuard&&g>15&&g<260) await sleep(260-g); const w=W(); w.wasm_halt(); w.wasm_run(); frozen=false; setPausedUi(false); };
  const rsh=s=>{ const w=W(); w.wasm_retro_shell_press_special(11,0); for(const ch of s) w.wasm_retro_shell_press_key(ch.charCodeAt(0)); w.wasm_retro_shell_press_special(10,0); return w.wasm_retro_shell_get_text(); };
  const lastLine=t=>{ const L=t.split('\n'); for(let i=L.length-1;i>=0;i--) if(L[i].trim()!=='') return L[i]; return ''; };
  const DBG=/\((\d+),(\d+)\) \$([0-9a-f ]{4}):/i;
  const ensureDbg=()=>{ rsh('clear'); if(!DBG.test(lastLine(rsh('')))){ rsh('.'); rsh('clear'); } };
  const bpList=()=>{ rsh('clear'); return [...rsh('break').matchAll(/Breakpoint (\d+) : 0x([0-9a-f]+)/gi)].map(m=>({id:+m[1],addr:parseInt(m[2],16)})); };
  const bpAdd=a=>{ rsh('break at 0x'+hex(a)); const l=bpList(); const b=l.filter(x=>x.addr===a).pop(); if(!b) throw new Error('breakpoint not set at $'+hex(a)); return b.id; };
  const bpDel=ids=>{ for(const id of [].concat(ids).sort((x,y)=>y-x)) rsh('break delete '+id); };
  const cpuPos=()=>{ rsh('clear'); rsh(''); const m=DBG.exec(lastLine(rsh(''))); if(!m) throw new Error('debugger not active'); return {pc:parseInt(m[3].trim(),16),line:+m[1],cycle:+m[2]}; };


  // register read with a small 6502 stub in RAM ($0334, tape buffer): saves A/X/Y/P/SP and puts everything back
  async function captureRegs(scr){
    scr=scr||0x0334; const V=scr+0x30, v=i=>[(V+i)&255,(V+i)>>8];
    const code=[0x8D,...v(0),0x8E,...v(1),0x8C,...v(2),0x08,0x68,0x8D,...v(3),0xBA,0x8E,...v(4),0xAE,...v(1),0xAC,...v(2),0xAD,...v(3),0x48,0xAD,...v(0),0x28,0xEA];
    const pc0=cpuPos().pc, w=W(), old=api.peek(scr,0x40,{ram:true}); api.poke(scr,code,{ram:true}); rsh('g 0x'+hex(scr));
    await run({maxFrames:30,pcs:[scr+code.length-1]});
    const o=api.peek(V,5,{ram:true}); api.poke(scr,old,{ram:true}); rsh('g 0x'+hex(pc0));
    return {a:o[0],x:o[1],y:o[2],p:o[3]|0x30,sp:o[4]};
  }
  async function execRestore(r,scr){
    scr=scr||0x0334; const code=[0xA2,r.x&255,0xA0,r.y&255,0xA9,(r.p&0xCF|0x20)&255,0x48,0xA9,r.a&255,0x28,0xEA];
    const old=api.peek(scr,0x40,{ram:true}); api.poke(scr,code,{ram:true}); rsh('g 0x'+hex(scr));
    await run({maxFrames:30,pcs:[scr+code.length-1]}); api.poke(scr,old,{ram:true});
  }

  // Runs until: n frames / condition / breakpoint. At the end the emulator stays STOPPED.
  // API 18: runs are SERIALIZED (one at a time). Before, two concurrent runFrames (e.g. joy(port,state,frames) not awaited inside runLoop) stopped each other
  // (halt() of the first while the second waited for the cycles) and the call never returned.
  let runQ=Promise.resolve(), abortGen=0; const prog={run:null,loop:null};   // prog = progress of the long jobs (progress())
  function run0(o){ const p=runQ.then(()=>run0i(o)); runQ=p.catch(()=>{}); return p; }
  async function run0i(o){
    const g0=abortGen; const w=W(); const max=o.maxFrames, start=cyc(), limit=start+max*FR, _pr=prog.run={start,limit,max}, pcs=(o.pcs||[]).map(addr), wps=(o.watch||[]).map(addr); let ids=[], wids=[], reason='frames';
    try{
      if(pcs.length||wps.length) ensureDbg();
      if(pcs.length) ids=pcs.map(bpAdd);
      if(wps.length) wids=wps.map(wpAdd);
      if(o.cond&&o.cond()) return {reason:'cond',cycles:cyc(),frames:0};
      await go(o.noGuard);   // API 23: in exact mode the anti-catch-up wait is not needed (the overshoot is corrected)
      let ref=cyc(), refT=performance.now(), ref2=ref, refT2=refT;
      for(;;){
        await sleep(0); const c=cyc();
        if(abortGen!==g0) throw E('ABORTED','run interrupted by abort()');
        if(o.cond&&o.cond()){ reason='cond'; break; }
        if(pcs.length||wps.length){ if(c!==ref){ ref=c; refT=performance.now(); } else if(performance.now()-refT>45){ reason='pc'; break; } }
        if(c>=limit){ reason='frames'; break; }
        if(c!==ref2){ ref2=c; refT2=performance.now(); } else if(performance.now()-refT2>5000) throw E('STALL','the core has not advanced for 5 s (stopped by a breakpoint/watchpoint or by a concurrent call?): cycles '+c+' su '+limit);
      }
    } finally { if(prog.run===_pr) prog.run=null; halt(); if(ids.length){ try{ bpDel(ids); }catch(e){} } if(wids.length){ try{ wpDel(wids); }catch(e){} } }
    const e=cyc(); const res={reason,cycles:e,frames:(e-start)/FR};
    if(reason==='pc'&&wps.length){ try{ const p=cpuPos().pc; res.pc=p; if(!pcs.includes(p)) res.reason='watch'; }catch(_){ } }
    return res;
  }


  /* ---- grabBrowserVideoAndAudio (API 16): browser recording (canvas video + audio) in real time, with NO link to emulated time ---- */
  let gbr=null;
  const GK_ROWS=[   // [key name in KM, label, width]
    [['<-','<-',1],['1','1',1],['2','2',1],['3','3',1],['4','4',1],['5','5',1],['6','6',1],['7','7',1],['8','8',1],['9','9',1],['0','0',1],['+','+',1],['-','-',1],['£','£',1],['HOME','HOME',1.5],['DEL','DEL',1.5]],
    [['CTRL','CTRL',1.5],['Q','Q',1],['W','W',1],['E','E',1],['R','R',1],['T','T',1],['Y','Y',1],['U','U',1],['I','I',1],['O','O',1],['P','P',1],['@','@',1],['*','*',1],['^','^',1],['RESTORE','REST',1.5]],
    [['STOP','STOP',1.5],['A','A',1],['S','S',1],['D','D',1],['F','F',1],['G','G',1],['H','H',1],['J','J',1],['K','K',1],['L','L',1],[':',':',1],[';',';',1],['=','=',1],['RETURN','RET',2]],
    [['C=','C=',1.5],['LSHIFT','SHFT',1.5],['Z','Z',1],['X','X',1],['C','C',1],['V','V',1],['B','B',1],['N','N',1],['M','M',1],[',',',',1],['.','.',1],['/','/',1],['RSHIFT','SHFT',1.5],['CRSR_D','v',1],['CRSR_R','>',1]],
    [['SPACE','SPACE',8]]];
  const GK_F=[['F1','F1'],['F3','F3'],['F5','F5'],['F7','F7']];
  function grabDraw(g){
    const c=g.cx, W0=g.w, ex=g.ex, cv0=g.cv0, ctx=g.ctx, vh=cv0.height*g.sc, I=g.input, orange='#ff9f1a', pos=g.pos;
    ctx.imageSmoothingEnabled=false; ctx.fillStyle='#111'; ctx.fillRect(0,0,c.width,c.height); ctx.drawImage(cv0,0,0,W0,vh);
    const lab=(t,x,y,s)=>{ ctx.fillStyle='#ddd'; ctx.font=Math.round(s*.17)+'px sans-serif'; ctx.textAlign='center'; ctx.fillText(t,x,y); };
    const fireBtn=(cx,cy,r,port,fill)=>{ const on=I.joy[port].fire; ctx.beginPath(); ctx.arc(cx,cy,r,0,6.2832); ctx.fillStyle=on?'#ff3b30':fill; ctx.fill(); ctx.fillStyle='#fff'; ctx.font=Math.round(r*.55)+'px sans-serif'; ctx.textAlign='center'; ctx.fillText('FIRE',cx,cy+r*.2); };
    const dpad=(cx,cy,s,port)=>{ const J=I.joy[port], u=s/3.4, on=d=>J[d]?orange:'rgba(255,255,255,.28)';
      ctx.fillStyle=on('up'); ctx.fillRect(cx-u/2,cy-u*1.5,u,u); ctx.fillStyle=on('down'); ctx.fillRect(cx-u/2,cy+u/2,u,u); ctx.fillStyle=on('left'); ctx.fillRect(cx-u*1.5,cy-u/2,u,u); ctx.fillStyle=on('right'); ctx.fillRect(cx+u/2,cy-u/2,u,u); ctx.fillStyle='rgba(255,255,255,.12)'; ctx.fillRect(cx-u/2,cy-u/2,u,u); };
    const stick2=(cx,cy,r,port)=>{ const J=I.joy[port], dx=(J.right?1:0)-(J.left?1:0), dy=(J.down?1:0)-(J.up?1:0), k=dx&&dy?.7071:1, mv=dx||dy;   // overlay: two circles (base + moving knob)
      ctx.beginPath(); ctx.arc(cx,cy,r,0,6.2832); ctx.fillStyle='rgba(255,255,255,.16)'; ctx.fill(); ctx.lineWidth=2; ctx.strokeStyle='rgba(255,255,255,.45)'; ctx.stroke();
      ctx.beginPath(); ctx.arc(cx+dx*k*r*.5,cy+dy*k*r*.5,r*.42,0,6.2832); ctx.fillStyle=mv?'rgba(255,159,26,.85)':'rgba(255,255,255,.35)'; ctx.fill(); };
    const joyBelow=(x,y,s,port)=>{ ctx.fillStyle='rgba(0,0,0,.55)'; ctx.fillRect(x,y,s*2.1,s); const cy=y+s*.52;   // FIRE a sinistra, stick a destra
      lab('JOY'+port,x+s*.55,y+s*.17,s); fireBtn(x+s*.55,cy,s*.27,port,'rgba(255,255,255,.28)'); dpad(x+s*1.55,cy,s,port); };
    const joyGroup=(x,y,s,port)=>{ const r=s*.5; lab('JOY'+port,x+s*1.55,y+s*.09,s); fireBtn(x+s*.5,y+s*.62,s*.34,port,'rgba(255,255,255,.22)'); stick2(x+s*1.6,y+s*.62,r*.85,port); };   // overlay compatto (fire sx, stick dx)
    const kb=(x0,y0,w,h,alpha)=>{ ctx.save(); ctx.globalAlpha=alpha; const rows=GK_ROWS.length, unit=w/(17+0.2+2.5), rh=h/rows; ctx.fillStyle='rgba(0,0,0,.5)'; ctx.fillRect(x0,y0,w,h); ctx.textAlign='center'; ctx.font=Math.round(rh*.42)+'px sans-serif';
      GK_ROWS.forEach((r,i)=>{ let x=x0+(i===4?unit*3.5:0)+2; const y=y0+i*rh;
        for(const [n,l,wd] of r){ const kw=wd*unit-2, k=KM[n], dn=k&&I.keys.has(k[0]+','+k[1]); ctx.fillStyle=dn?orange:'rgba(255,255,255,.22)'; ctx.fillRect(x,y+1,kw,rh-2); ctx.fillStyle=dn?'#000':'#fff'; ctx.fillText(l,x+kw/2,y+rh*.64); x+=wd*unit; } });
      const fx=x0+17.2*unit+2, fw=2.3*unit; GK_F.forEach(([n,l],i)=>{ const k=KM[n], dn=I.keys.has(k[0]+','+k[1]), y=y0+i*rh; ctx.fillStyle=dn?orange:'rgba(255,255,255,.22)'; ctx.fillRect(fx,y+1,fw,rh-2); ctx.fillStyle=dn?'#000':'#fff'; ctx.fillText(l,fx+fw/2,y+rh*.64); });
      ctx.restore(); };
    // --- panel below the video: first the joysticks (fire on the left, stick on the right), the keyboard below
    let y=vh; const jb=[1,2].filter(p=>pos['joy'+p]==='below'), jo=[1,2].filter(p=>pos['joy'+p]==='overlay');
    if(jb.length){ const sz=Math.min(ex.jh*.9,W0/(jb.length*2.3)), gap=W0/jb.length; jb.forEach((p,i)=>joyBelow(i*gap+(gap-sz*2.1)/2,y+(ex.jh-sz)/2,sz,p)); y+=ex.jh; }
    if(pos.keyboard==='below') kb(0,y,W0,ex.kh,1);
    // --- overlay on the screen
    const kOv=pos.keyboard==='overlay', sz=Math.round(W0*.09), gw=sz*2.2, bm=8, by=vh-sz-bm;
    if(jo.length){
      if(!kOv&&jo.length===1){   // one joystick in overlay and keyboard not in overlay: fire bottom left, stick bottom right of the screen
        const p=jo[0], R=Math.round(W0*.075); ctx.save(); ctx.globalAlpha=.65; lab('JOY'+p,W0-bm-R,vh-bm-R*2-6,R*2); lab('JOY'+p,bm+R,vh-bm-R*2-6,R*2);
        fireBtn(bm+R,vh-bm-R,R*.95,p,'rgba(255,255,255,.22)'); stick2(W0-bm-R,vh-bm-R,R,p); ctx.restore(); }
      else if(!kOv){ ctx.save(); ctx.globalAlpha=.65; joyGroup(bm,by,sz,jo[0]); joyGroup(W0-gw-bm,by,sz,jo[1]); ctx.restore(); }   // two joysticks: one per side
      else { const jw=(gw+bm)*jo.length; ctx.save(); ctx.globalAlpha=.65; jo.forEach((p,i)=>joyGroup(W0-jw+i*(gw+bm),by,sz,p)); ctx.restore(); }
    }
    if(kOv){ const jw=jo.length?(gw+bm)*jo.length:0, kw=Math.min(W0*.62,W0-jw-24), kh=kw*.2; kb(bm,vh-kh-bm,kw,kh,.5); }
  }
  const grabHook=g=>{   // hooks the functions the API (and the page) use to press keys/joysticks, to show them
    const w=W(), k0=w.wasm_schedule_key, a0=w.action; g.orig={k0,a0,w};
    w.wasm_schedule_key=function(row,col,press,delay){ const id=row+','+col, ap=()=>{ if(press) g.input.keys.add(id); else g.input.keys.delete(id); }; if(delay>0) setTimeout(ap,delay*20); else ap(); return k0.apply(this,arguments); };
    w.action=function(name){ const m=/^j([12])(up|down|left|right|fire)([01])$/.exec(String(name)); if(m) g.input.joy[m[1]][m[2]]=m[3]==='1'; return a0.apply(this,arguments); };
  };
  async function grabStop(){
    const g=gbr; await sleep(80); g.rec.stop(); await g.done; g.on=false; clearInterval(g.pk);
    if(g.aud){ try{ g.aud.gn.disconnect(g.aud.mg); g.aud.mg.disconnect(); }catch(e){} }
    if(g.orig){ g.orig.w.wasm_schedule_key=g.orig.k0; g.orig.w.action=g.orig.a0; }
    gbr=null; const buf=new Uint8Array(await new Blob(g.ch,{type:g.mime}).arrayBuffer());
    return {data:u8ToB64(buf),mime:g.mime,bytes:buf.length,seconds:+((performance.now()-g.t0)/1000).toFixed(2),width:g.cx.width,height:g.cx.height,audio:g.hasAudio,audioPeak:g.hasAudio?+g.peak.toFixed(4):null,controls:g.controls,warnings:g.warn};
  }
  /* ---- frame capture while running (API 14): a screenshot every 'every' emulated frames ---- */
  let cap=null;
  async function capShot(){ if(!cap||!cap.on) return; while(cap&&cap.on&&cap.q.length>=cap.max) await sleep(10); if(cap&&cap.on) cap.q.push(api.screenshot().split(',')[1]); }
  // API 23: EXACT stepping. The core advances in blocks of frames driven by real time: if the browser is late it computes 2 frames at once
  // and a stop by count overshoots by 1 frame (measured: ~1 step in 800-1000 in runLoop). Here: snapshot before, check after, on overshoot restore and repeat.
  // API 24: model of the held INPUTS (joysticks and keyboard). The core does not save the joystick ports in the snapshot and an input already delivered
  // to the core is lost with wasm_loadfile (measured in a project chat: after the restore $DC00=127 with the joystick "held").
  // action('jPDIR0/1') and wasm_schedule_key(row,col,press,delayFrames) are hooked and the state is rebuilt at a given cycle.
  const INP={joy:{1:{},2:{}},held:new Map(),ev:[],seq:0};
  function trkInstall(w){ w.__trk=1; const k0=w.wasm_schedule_key, a0=w.action; w.__k0=k0; w.__a0=a0; INP.joy={1:{},2:{}}; INP.held=new Map(); INP.ev=[];
    w.wasm_schedule_key=function(row,col,press,delay){ try{ INP.ev.push({c:Number(w.wasm_get_cpu_cycles())+Math.max(0,delay|0)*FR,row,col,press:!!press,q:INP.seq++}); }catch(e){} return k0.apply(this,arguments); };
    w.action=function(name){ const m=/^j([12])(up|down|left|right|fire)([01])$/.exec(String(name)); if(m) INP.joy[m[1]][m[2]]=m[3]==='1'; return a0.apply(this,arguments); }; }
  function inpAt(c){   // folds the events <= c into the held-keys model; returns {joy,held,pending}
    INP.ev.sort((a,b)=>a.c-b.c||a.q-b.q); let k=0; for(;k<INP.ev.length&&INP.ev[k].c<=c;k++){ const e=INP.ev[k], id=e.row+','+e.col; if(e.press) INP.held.set(id,[e.row,e.col]); else INP.held.delete(id); } INP.ev.splice(0,k);
    return {joy:{1:Object.assign({},INP.joy[1]),2:Object.assign({},INP.joy[2])},held:new Map(INP.held),pending:INP.ev.map(e=>Object.assign({},e))}; }
  function inpApply(snap,c0,o={}){   // after a restore at cycle c0: puts back joysticks and held keys as in 'snap' and reschedules the future events already consumed
    const w=W(), D=['up','down','left','right','fire'];
    for(const p of [1,2]){ for(const d of D) w.__a0('j'+p+d+'0'); for(const d of D) if(snap.joy[p][d]) w.__a0('j'+p+d+'1'); INP.joy[p]=Object.assign({},snap.joy[p]); }
    for(const k in KM){ const rc=KM[k]; if(rc[0]<8&&!snap.held.has(rc[0]+','+rc[1])) w.__k0(rc[0],rc[1],0,0); }   // releases ALL the other keys: same messages to the core whatever the history (matrix and joystick ports are not in the snapshot)
    for(const [id,rc] of snap.held) w.__k0(rc[0],rc[1],1,0);
    INP.held=new Map(snap.held);
    if(o.resched!==undefined){ for(const e of snap.pending){ if(e.c>o.resched) continue; w.__k0(e.row,e.col,e.press?1:0,Math.max(0,Math.round((e.c-c0)/FR))); } }
  }
  const xst={retries:0,inexact:0};
  async function run0x(o){
    if(!o.exact||!frozen||o.cond||(o.pcs&&o.pcs.length)||(o.watch&&o.watch.length)) return run0(o);
    const n=o.maxFrames, w=W(); let pre=null;
    if(n>8){ const c0=cyc(); pre=await run0(Object.assign({},o,{maxFrames:n-4})); const done=Math.round((cyc()-c0)/FR); if(done>=n) return Object.assign(pre,{frames:(cyc()-c0)/FR,exact:done===n}); return run0x(Object.assign({},o,{maxFrames:n-done})).then(r=>Object.assign(r,{frames:(cyc()-c0)/FR})); }
    for(let t=0;;t++){
      const j=JSON.parse(w.wasm_take_user_snapshot()), b=w.Module.HEAPU8.slice(j.address,j.address+j.size), c0=cyc(), in0=inpAt(c0);
      if(t===0&&o.restoreFirst!==false){ w.wasm_halt(); w.wasm_loadfile('state.vc64',b,b.length); frozen=true; inpApply(in0,c0,{}); }   // API 24: always start from a freshly restored state: the restore is not transparent (measured: with no input, a repeated step changes the CIA state), so first try and repeats must start the same way
      const r=await run0(Object.assign({},o,{noGuard:o.noGuard!==false&&t===0})), cBad=cyc(), d=Math.round((cyc()-c0)/FR), bad=d!==n||(o._forceRetry&&t<o._forceRetry);
      if(!bad||r.reason!=='frames'){ if(t) r.retries=t; return r; }
      xst.retries++;
      if(t>=8){ xst.inexact++; return Object.assign(r,{exact:false,retries:t}); }
      w.wasm_halt(); w.wasm_loadfile('state.vc64',b,b.length); frozen=true; setPausedUi(true); inpApply(in0,c0,{resched:o._noResched?undefined:cBad});   // API 24: puts the inputs back
    }
  }
  async function run(o){
    if(!cap||!cap.on) return run0x(o);
    let left=o.maxFrames, tot=0, last={reason:'frames'};
    while(left>0){ const k=Math.min(cap.every,left); last=await run0x(Object.assign({},o,{maxFrames:k})); tot+=last.frames; await capShot(); if(last.reason!=='frames') break; left-=k; }
    return Object.assign({},last,{frames:tot});
  }
  /* ---- helper API 6 ---- */
  const snaps={}, shots={}, encs={};   // encs: named encodings (API 23)
  const u8ToB64=b=>{ let s=''; for(let i=0;i<b.length;i+=0x8000) s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000)); return btoa(s); };
  // C64 keyboard matrix: row = PRA line, column = PRB bit (RESTORE = [9,9], as in the core)
  const KROWS=[['DEL','RETURN','CRSR_R','F7','F1','F3','F5','CRSR_D'],['3','W','A','4','Z','S','E','LSHIFT'],['5','R','D','6','C','F','T','X'],['7','Y','G','8','B','H','U','V'],
    ['9','I','J','0','M','K','O','N'],['+','P','L','-','.',':','@',','],['£','*',';','HOME','RSHIFT','=','^','/'],['1','<-','CTRL','2','SPACE','C=','Q','STOP']];
  const KM={}; KROWS.forEach((r,l)=>r.forEach((n,b)=>{ KM[n]=[l,b]; })); KM.RESTORE=[9,9];
  const SHIFTED={'!':'1','"':'2','#':'3','$':'4','%':'5','&':'6',"'":'7','(':'8',')':'9','<':',','>':'.','?':'/','[':':',']':';'};
  const NAMED={'RUN/STOP':['STOP'],RUNSTOP:['STOP'],STOP:['STOP'],RETURN:['RETURN'],ENTER:['RETURN'],CR:['RETURN'],F1:['F1'],F2:['LSHIFT','F1'],F3:['F3'],F4:['LSHIFT','F3'],F5:['F5'],F6:['LSHIFT','F5'],F7:['F7'],F8:['LSHIFT','F7'],
    HOME:['HOME'],CLR:['LSHIFT','HOME'],DEL:['DEL'],INST:['LSHIFT','DEL'],RIGHT:['CRSR_R'],CRSR_RIGHT:['CRSR_R'],DOWN:['CRSR_D'],CRSR_DOWN:['CRSR_D'],LEFT:['LSHIFT','CRSR_R'],CRSR_LEFT:['LSHIFT','CRSR_R'],UP:['LSHIFT','CRSR_D'],CRSR_UP:['LSHIFT','CRSR_D'],
    SPACE:['SPACE'],RESTORE:['RESTORE'],POUND:['£'],ARROW_UP:['^'],ARROW_LEFT:['<-'],CTRL:['CTRL'],CBM:['C='],'C=':['C='],SHIFT:['LSHIFT'],LSHIFT:['LSHIFT'],RSHIFT:['RSHIFT']};
  function charKeys(c,keepCase){
    if(c==='\n'||c==='\r') return ['RETURN']; if(c===' ') return ['SPACE'];
    if(SHIFTED[c]) return ['LSHIFT',SHIFTED[c]]; if(c==='_') return ['<-']; if(c==='\\') return ['£'];
    const u=c.toUpperCase(); if(/^[A-Z]$/.test(c)) return (keepCase&&c===u)?['LSHIFT',u]:[u];
    if(KM[u]&&u.length===1) return [u];
    throw E('BAD_ARG','character cannot be typed: '+JSON.stringify(c));
  }
  function sendParse(text,keepCase){
    const out=[]; const re=/\{([^}]*)\}|([\s\S])/g; let m;
    while((m=re.exec(text))){
      if(m[2]!==undefined){ out.push({keys:charKeys(m[2],keepCase)}); continue; }
      const tok=m[1]; let u=tok.toUpperCase(); const wm=/^WAIT:(\d+)$/.exec(u); if(wm){ out.push({wait:+wm[1]}); continue; }
      if(tok==='{'||tok==='+'||tok==='}'){ out.push({keys:charKeys(tok,keepCase)}); continue; }
      const parts=tok.split('+').filter(x=>x!==''), keys=[];
      for(const p of parts){ const up=p.toUpperCase(); if(NAMED[up]) keys.push(...NAMED[up]); else if(p.length===1) keys.push(...charKeys(p,keepCase)); else throw E('BAD_ARG','unknown token: {'+tok+'}'); }
      out.push({keys:[...new Set(keys)]});
    } return out;
  }
  const wpList=()=>{ rsh('clear'); return [...rsh('watch').matchAll(/Watchpoint (\d+) : 0x([0-9a-f]+)/gi)].map(m=>({id:+m[1],addr:parseInt(m[2],16)})); };
  const wpAdd=a=>{ rsh('watch at 0x'+hex(a)); const b=wpList().filter(x=>x.addr===a).pop(); if(!b) throw E('CORE','watchpoint not set at $'+hex(a)); return b.id; };
  const wpDel=ids=>{ for(const id of [].concat(ids).sort((x,y)=>y-x)) rsh('watch delete '+id); };
  // one instruction: "s" works only with a wasm_run; the core stops again by itself after the instruction. The shell text shows the state AFTER (next pc + log of the last instructions).
  // NB: the register line printed by the shell has some register nibbles swapped (e.g. X=1 printed "10"): it is NOT used. For the registers: regs().
  const INSL=/^->\s+([0-9A-Fa-f]{4})\s+((?:[0-9A-Fa-f]{2} )+)\s*(.*?)\s*$/m;
  const parseIns=t=>{ const m=INSL.exec(t); if(!m) throw E('CORE','step: disassembly not readable'); return {pc:parseInt(m[1],16),bytes:m[2].trim(),asm:m[3]}; };
  const curInstr=()=>{ rsh('clear'); return parseIns(rsh('d')); };
  async function stepOnce(){
    const w=W(); rsh('clear'); const c0=cyc(); rsh('s');
    w.wasm_run(); const t0=performance.now(); while(cyc()===c0&&performance.now()-t0<300) await sleep(0); w.wasm_halt();
    if(cyc()===c0) throw E('CORE','step: the instruction was not executed');
    return {next:parseIns(w.wasm_retro_shell_get_text()),cycles:c0};
  }
  function sidDecode(r){
    const voices=[0,1,2].map(v=>{ const b=v*7, f=r[b]|(r[b+1]<<8), c=r[b+4]; return {freq:f,hz:+(f*985248/16777216).toFixed(2),pulseWidth:r[b+2]|((r[b+3]&15)<<8),gate:!!(c&1),sync:!!(c&2),ring:!!(c&4),test:!!(c&8),tri:!!(c&16),saw:!!(c&32),pulse:!!(c&64),noise:!!(c&128),attack:r[b+5]>>4,decay:r[b+5]&15,sustain:r[b+6]>>4,release:r[b+6]&15}; });
    return {voices,filterCutoff:(r[21]&7)|(r[22]<<3),filterRes:r[23]>>4,filterRoute:r[23]&15,volume:r[24]&15,filterMode:{lp:!!(r[24]&16),bp:!!(r[24]&32),hp:!!(r[24]&64)},mute3:!!(r[24]&128)};
  }
  function grab(o){
    const cv=W().document.querySelector('canvas'); const t=document.createElement('canvas'); t.width=cv.width; t.height=cv.height; const x=t.getContext('2d'); x.drawImage(cv,0,0);
    const r=o&&o.rect||{x:0,y:0,w:cv.width,h:cv.height}; const id=x.getImageData(r.x,r.y,r.w,r.h); return {w:r.w,h:r.h,d:id.data};
  }
  function gifEncode(frames,w,h,delay){
    const map=new Map(); let over=false;
    for(const f of frames){ for(let i=0;i<f.length;i+=4){ const k=(f[i]<<16)|(f[i+1]<<8)|f[i+2]; if(!map.has(k)){ if(map.size>=256){ over=true; break; } map.set(k,map.size); } } if(over) break; }
    const pal=new Uint8Array(768); if(over){ for(let i=0;i<256;i++){ pal[i*3]=((i>>5)&7)*255/7; pal[i*3+1]=((i>>2)&7)*255/7; pal[i*3+2]=(i&3)*255/3; } } else map.forEach((i,k)=>{ pal[i*3]=k>>16; pal[i*3+1]=(k>>8)&255; pal[i*3+2]=k&255; });
    const out=[]; const P=(...a)=>out.push(...a), P16=v=>out.push(v&255,v>>8);
    P(0x47,0x49,0x46,0x38,0x39,0x61); P16(w); P16(h); P(0xF7,0,0); out.push(...pal); P(0x21,0xFF,0x0B,...[...'NETSCAPE2.0'].map(c=>c.charCodeAt(0)),3,1,0,0,0);
    for(const f of frames){
      const ix=new Uint8Array(w*h); for(let i=0,p=0;i<f.length;i+=4,p++) ix[p]=over?((f[i]&0xE0)|((f[i+1]&0xE0)>>3)|(f[i+2]>>6)):map.get((f[i]<<16)|(f[i+1]<<8)|f[i+2]);
      P(0x21,0xF9,4,0); P16(delay); P(0,0); P(0x2C); P16(0); P16(0); P16(w); P16(h); P(0,8);
      const bytes=lzw(ix); for(let i=0;i<bytes.length;i+=255){ const c=bytes.subarray(i,i+255); out.push(c.length); for(let j=0;j<c.length;j++) out.push(c[j]); } P(0);
    }
    P(0x3B); return Uint8Array.from(out);
  }
  function lzw(ix){            // LZW GIF (min code size 8), omggif scheme
    const buf=[]; const clear=256, eoi=257; let next=258, size=9, cur=0, shift=0, tbl=new Map();
    const emit=c=>{ cur|=c<<shift; shift+=size; while(shift>=8){ buf.push(cur&255); cur>>=8; shift-=8; } };
    emit(clear); let ib=ix[0];
    for(let i=1;i<ix.length;i++){ const k=ix[i], key=(ib<<8)|k, c=tbl.get(key);
      if(c===undefined){ emit(ib); if(next===4096){ emit(clear); next=258; size=9; tbl=new Map(); } else { if(next>=(1<<size)) size++; tbl.set(key,next++); } ib=k; } else ib=c; }
    emit(ib); emit(eoi); if(shift>0) buf.push(cur&255); return Uint8Array.from(buf);
  }
  // recording -> input script (API 14): type, sendText, joy(port,state,frames); the rest becomes a comment
  function recToText(r){
    const L=['# exported by recordStop: '+r.events.length+' events, '+r.frames+' frames (time from the start of the recording)']; let lost=0;
    for(const e of r.events){ const a=e.a||[];
      if(e.m==='type'){ const ks=[].concat(a[0]), o=a[1]||{}; const ex=[]; if(o.shift) ex.push('SHIFT'); if(o.ctrl) ex.push('CTRL'); if(o.cbm) ex.push('C='); L.push(e.f+' '+ks.concat(ex).join('&')+(o.frames?' '+o.frames:'')); }
      else if(e.m==='sendText'){ const o=a[1]||{}; L.push(e.f+' text '+JSON.stringify(String(a[0]))+(o.framesPerKey?' '+o.framesPerKey:'')); }
      else if(e.m==='joy'&&(typeof a[0]==='number')&&a[1]&&typeof a[1]==='object'&&a[2]!==undefined){ const ds=Object.keys(a[1]).filter(d=>a[1][d]&&JDIR[d.toUpperCase()]); if(ds.length) L.push(e.f+' '+ds.map(d=>'JOY'+a[0]+'-'+d.toUpperCase()).join('&')+' '+Math.max(1,a[2])); }
      else { lost++; L.push('# not exported: '+e.f+' '+e.m+'('+JSON.stringify(a).slice(1,-1).slice(0,60)+')'); } }
    return {text:L.join('\n')+'\n',frames:r.frames,events:r.events.length,notExported:lost};
  }
  /* ---- input scripts (API 11): lines «<frame> <input> [duration]», «wait ...» ---- */
  const JDIR={UP:'up',DOWN:'down',LEFT:'left',RIGHT:'right',FIRE:'fire'};
  const pnum=(s,what,n,err)=>{ const t=String(s).trim(); if(/^\$[0-9a-f]+$/i.test(t)) return parseInt(t.slice(1),16); if(/^0x[0-9a-f]+$/i.test(t)) return parseInt(t,16); if(/^\d+$/.test(t)) return +t; err(n,what+' not numeric: '+t); };
  function parseCmd(cmd,args,n,err){
    const nm=(s,w)=>{ if(!/^[\w.\-]+$/.test(s)) err(n,w+': invalid name (only letters, digits, _ . -): '+s); return s; };
    const base={kind:'cmd',line:n}; let m;
    switch(cmd){
      case 'poke': { m=/^(\S+)\s+(.+?)(?:\s+(ram))?$/i.exec(args); if(!m) err(n,'poke: forma «poke ADDR v1,v2,.. [ram]»');
        const vals=m[2].split(/[,\s]+/).filter(Boolean).map(x=>{ const v=pnum(x,'value',n,err); if(v>255) err(n,'poke: value > 255: '+x); return v; }); return Object.assign(base,{cmd:'poke',addr:m[1],vals,ram:!!m[3]}); }
      case 'assert': {
        if(m=/^mem\s*(!?=)\s*(\S+)\s+(\S+)(?:\s+&(\S+))?$/i.exec(args)) return Object.assign(base,{cmd:'assert',what:'mem',addr:m[2],value:pnum(m[3],'value',n,err),mask:m[4]!==undefined?pnum(m[4],'mask',n,err):undefined,not:m[1]==='!='});
        if(m=/^screen\s+("(?:[^"\\]|\\.)*")$/i.exec(args)){ let t; try{ t=JSON.parse(m[1]); }catch(e){ err(n,'invalid string: '+m[1]); } return Object.assign(base,{cmd:'assert',what:'screen',text:t}); }
        if(m=/^text\s+("(?:[^"\\]|\\.)*")((?:\s+(?:enc|addr|len)=\S+)*)$/i.exec(args)){ let t; try{ t=JSON.parse(m[1]); }catch(e){ err(n,'invalid string: '+m[1]); } const to={}; for(const kv of m[2].trim().split(/\s+/).filter(Boolean)){ const [k,v]=kv.split('='); to[k.toLowerCase()]=k.toLowerCase()==='len'?+v:v; } return Object.assign(base,{cmd:'assert',what:'text',text:t,textOpts:to}); }   // API 24
        err(n,'assert: forms «assert mem=ADDR VALUE [&MASK]» (also mem!=) | «assert screen "text"» | «assert text "text" [enc=] [addr=] [len=]» (screen code)'); }
      case 'savestate': return Object.assign(base,{cmd:'saveState',name:nm(args,'saveState')});
      case 'loadstate': return Object.assign(base,{cmd:'loadState',name:nm(args,'loadState')});
      case 'screenshot': { const f=nm(args,'screenshot'); return Object.assign(base,{cmd:'screenshot',file:/\.[A-Za-z0-9]+$/.test(f)?f:f+'.png'}); }
      case 'regress': { m=/^(save|check)\s+([\w.\-]+)((?:\s+\S+)*)$/i.exec(args); if(!m) err(n,'regress: forms «regress save NAME» | «regress check NAME [tolerance=N] [ignore=A-B ...]»');
        const o=Object.assign(base,{cmd:'regress',op:m[1].toLowerCase(),name:m[2],ignore:[]}); for(const t of m[3].trim().split(/\s+/).filter(Boolean)){ const q=/^(tolerance|ignore)=(\S+)$/i.exec(t); if(!q) err(n,'regress: unknown option '+t); if(q[1].toLowerCase()==='tolerance') o.tolerance=pnum(q[2],'tolerance',n,err); else o.ignore.push(q[2]); } return o; }
      case 'call': { m=/^(\S+)((?:\s+\S+)*)$/.exec(args); if(!m) err(n,'call: forma «call ADDR [a=N] [x=N] [y=N] [timeout=N] [nowait]»');
        const o=Object.assign(base,{cmd:'call',addr:m[1],regs:{}}); for(const t of m[2].trim().split(/\s+/).filter(Boolean)){ if(/^nowait$/i.test(t)){ o.noWait=true; continue; } const q=/^(a|x|y|timeout)=(\S+)$/i.exec(t); if(!q) err(n,'call: unknown option '+t); const v=pnum(q[2],q[1],n,err); if(q[1].toLowerCase()==='timeout') o.timeout=v; else { if(v>255) err(n,'call: '+q[1]+' > 255'); o.regs[q[1].toLowerCase()]=v; } } return o; }
      case 'video': case 'rec': { const tk=args.split(/\s+/).filter(Boolean), op=(tk.shift()||'').toLowerCase(); if(op!=='start'&&op!=='stop') err(n,cmd+': forma «'+cmd+' start [NAME] [keep]'+(cmd==='video'?' [every=N] [scale=N] [crf=N]':'')+'» | «'+cmd+' stop»');
        const o=Object.assign(base,{cmd,op,keep:false}); if(op==='stop'){ if(tk.length) err(n,cmd+' stop takes no parameters'); return o; }
        for(const t of tk){ if(/^keep$/i.test(t)) o.keep=true; else if(/^autostop$/i.test(t)) o.keep=false; else { const q=/^(every|scale|crf)=(\d+)$/i.exec(t); if(q&&cmd==='video'){ const v=+q[2], k=q[1].toLowerCase(); if(k==='every'&&v<1) err(n,'every >= 1'); if(k==='scale'&&(v<1||v>4)) err(n,'scale: 1-4'); if(k==='crf'&&v>51) err(n,'crf: 0-51'); o[k]=v; } else if(!q&&!o.name&&/^[\w.\-]+$/.test(t)) o.name=t; else err(n,cmd+' start: unknown parameter '+t); } }
        return o; }
    }
  }
  function scriptParse(text){
    if(typeof text!=='string') throw E('BAD_ARG','script: a text string is needed');
    const ev=[], warn=[]; let seg=[], prev=0;      // seg = events of the current segment (between two waits); prev = frame of the previous event
    const items=[]; const err=(n,m)=>{ throw E('BAD_ARG','script line '+n+': '+m); };
    text.split(/\r?\n/).forEach((raw,i)=>{
      const n=i+1; let l=raw.replace(/(^|\s)#.*$/,'').trim(); if(l==='') return;
      { const CM=/^(poke|assert|savestate|loadstate|screenshot|regress|call|video|rec)(?:\s+(.*))?$/i; let cm=CM.exec(l), tf;
        if(!cm){ const t2=/^(\+?\d+)\s+(.+)$/.exec(l); if(t2){ const c2=CM.exec(t2[2]); if(c2){ cm=c2; tf=t2[1]; } } }
        if(cm){ const o=parseCmd(cm[1].toLowerCase(),(cm[2]||'').trim(),n,err);
          if(tf!==undefined){ if(o.cmd==='loadState') err(n,'loadState cannot have a frame in front (it resets time): write it on its own'); const f=tf[0]==='+'?prev+(+tf.slice(1)):+tf; if(f<prev) err(n,'frame '+f+' earlier than the one of the line before ('+prev+')'); prev=f; o.f=f; }
          else prev=0;       // command with no frame = sequence point: it starts after the previous events and time restarts from 0 (like wait)
          items.push(o); return; } }
      const mw=/^wait\s+(.+)$/i.exec(l);
      if(mw){
        const r=mw[1].trim(); let o={kind:'wait',line:n,timeout:3000};
        const tm=/\s+(\d+)(s?)$/.exec(r), body=tm&&!/^["]/.test(r.slice(tm.index+1))? r.slice(0,tm.index).trim():r;
        if(tm&&body!==''){ o.timeout=tm[2]?(+tm[1])*50:+tm[1]; }
        let m;
        let mm;
        if(mm=/^mem\s*(!?=)\s*(\S+)\s+(\S+)(?:\s+&(\S+))?(?:\s+(\d+)(s?))?$/i.exec(r)){ o.mem={addr:mm[2],value:pnum(mm[3],'value',n,err),mask:mm[4]!==undefined?pnum(mm[4],'mask',n,err):undefined,not:mm[1]==='!='}; o.timeout=mm[5]?(mm[6]?(+mm[5])*50:+mm[5]):3000; items.push(o); prev=0; return; }
        if(/^\d+$/.test(r)) o.frames=+r, o.timeout=undefined;
        else if(m=/^"(.*)"$/.exec(body)) o.screen=JSON.parse('"'+m[1]+'"');
        else if(m=/^text\s+"(.*)"((?:\s+(?:enc|addr|len)=\S+)*)$/i.exec(body)){ o.stext=JSON.parse('"'+m[1]+'"'); if(m[2].trim()){ o.stextOpts={}; for(const kv of m[2].trim().split(/\s+/)){ const [k,v]=kv.split('='); o.stextOpts[k.toLowerCase()]=k.toLowerCase()==='len'?+v:v; } } }   // API 23: options enc= addr= len=   // API 18: wait text "TEXT" [timeout]: searches as screen code (screen RAM), also with custom charsets
        else if(m=/^pc\s*=\s*(\S+)$/i.exec(body)) o.pc=m[1];
        else err(n,'invalid wait: '+r+'  (forms: wait N | wait "text" [timeout] | wait text "text" [enc=NAME] [addr=A] [len=N] [timeout] (screen code) | wait pc=0xADDR [timeout] | wait mem=ADDR VALUE [&MASK] [timeout] (also mem!=); timeout in frames or with s = seconds)');
        items.push(o); prev=0; return;
      }
      const m=/^(\+?\d+)\s+(.+)$/.exec(l); if(!m) err(n,'expected «<frame> <input> [duration]» or «wait ...»: '+raw.trim());
      let f=m[1][0]==='+'?prev+(+m[1].slice(1)):+m[1]; const rest=m[2].trim();
      if(f<prev) err(n,'frame '+f+' earlier than the one of the line before ('+prev+'): lines must be in order (between one wait and the next time restarts from 0)');
      prev=f; let o;
      const mt=/^text\s+("(?:[^"\\]|\\.)*")(?:\s+(\d+))?$/i.exec(rest);
      if(mt){ let s; try{ s=JSON.parse(mt[1]); }catch(e){ err(n,'invalid string: '+mt[1]); } o={kind:'text',f,line:n,text:s,framesPerKey:mt[2]?+mt[2]:undefined}; }
      else {
        const parts=rest.split(/\s+/), hold=parts.length>1?+parts[1]:DEF_HOLD;
        if(parts.length>2||!Number.isInteger(hold)||hold<MIN_HOLD) err(n,'invalid duration (integer >= '+MIN_HOLD+' frames): '+rest);
        const keys=[], joys=[];
        for(const tok of parts[0].split('&')){
          const mj=/^JOY([12])-(UP|DOWN|LEFT|RIGHT|FIRE)$/i.exec(tok);
          if(mj) joys.push({port:+mj[1],dir:JDIR[mj[2].toUpperCase()]});
          else { try{ keys.push(...keysOf(tok)); }catch(e){ err(n,e.message); } }
        }
        if(keys.length&&joys.length) err(n,'keys and joystick in the same event: use two lines');
        o=joys.length?{kind:'joy',f,line:n,joys,hold}:{kind:'key',f,line:n,keys:[...new Set(keys)],hold};
      }
      items.push(o);
    });
    { let vid=false, rc=false;       // consistency of video/rec start-stop
      for(const o of items){ if(o.kind!=='cmd') continue;
        if(o.cmd==='video'){ if(o.op==='start'){ if(vid) err(o.line,'video start: a video is already active (video stop needed first)'); vid=true; } else { if(!vid) warn.push('line '+o.line+': video stop without video start in this script (ok only if a «keep» video is active from a previous call)'); vid=false; } }
        if(o.cmd==='rec'){ if(o.op==='start'){ if(rc) err(o.line,'rec start: recording already active in the script'); rc=true; } else { if(!rc) warn.push('line '+o.line+': rec stop without rec start in this script'); rc=false; } } } }
    // warnings: same key pressed again before release + MIN_REL frames
    let t0=0; const last={};
    for(const o of items){ if(o.kind==='wait'||(o.kind==='cmd'&&o.f===undefined)){ for(const k in last) delete last[k]; continue; } if(o.kind==='cmd') continue;
      const ids=o.kind==='key'?o.keys:o.kind==='joy'?o.joys.map(j=>'J'+j.port+j.dir):[];
      for(const id of ids){ if(last[id]!==undefined&&o.f<last[id]+MIN_REL) warn.push('line '+o.line+': '+id+' pressed again less than '+MIN_REL+' frames after release (release too short: presses may be lost)'); last[id]=o.f+o.hold; } }
    return {items,warnings:warn};
  }
  /* ---- helper API 7 ---- */
  // the KERNAL scans the keyboard only after init (~2.7 M cycles from reset): earlier keys are lost (measured: reset+20 frames = all lost, +80 = only the last part, +140 = ok)
  const BOOT_CYC=2750000, FAST_MARGIN=70;
  const bootWait=async o=>{ if(o&&o.noWait) return; const need=BOOT_CYC-cyc(); if(need>0){ if(frozen) await api.runFrames(Math.ceil(need/FR)); else await sleep(need/985+50); } };
  /* ---- input API 9: parameters and key resolution ---- */
  // measured (BASIC, 8 phase shifts): press 1-4 frames with release >=2 = 100% correct; release 1 frame: ok only with press 2, fails with 3-4 (1/8)
  const MIN_HOLD=1, DEF_HOLD=3, MIN_REL=2, DEF_REL=3;
  const chk=(n,v,min)=>{ if(!Number.isInteger(v)||v<min) throw E('BAD_ARG',n+': intero >= '+min+' (value '+v+')'); return v; };
  function keysOf(spec,o={}){
    const list=Array.isArray(spec)?spec:[spec], set=[];
    const one=k=>{ if(typeof k!=='string'||k==='') throw E('BAD_ARG','invalid key: '+JSON.stringify(k));
      if(k.length===1) return charKeys(k,false); const up=k.toUpperCase(); if(NAMED[up]) return NAMED[up];
      if(k.includes('+')&&!/^\++$/.test(k)){ const r=[]; for(const p of k.split('+').filter(x=>x!=='')) r.push(...one(p)); return r; }
      if(/^(UP|DOWN|LEFT|RIGHT|FIRE)$/i.test(k)) throw E('BAD_ARG','unknown key: '+JSON.stringify(k)+' (in scripts the joystick must be written in full also after &: JOY2-UP&JOY2-FIRE, not JOY2-UP&FIRE)');   // API 23
      throw E('BAD_ARG','unknown key: '+JSON.stringify(k)+' (one key, or a list for several simultaneous keys; for strings use sendText)'); };
    for(const k of list) set.push(...one(k));
    if(o.shift) set.push('LSHIFT'); if(o.ctrl) set.push('CTRL'); if(o.cbm) set.push('C=');
    return [...new Set(set)];
  }
  // waits n EMULATED frames: with the emulator stopped it advances them, otherwise it waits on the cycle counter (robust if the browser is slower than real time)
  const waitFrames=async n=>{ if(frozen){ await api.runFrames(n); return; } const target=cyc()+n*FR, t0=Date.now(); while(cyc()<target&&Date.now()-t0<n*200+2000) await sleep(5); };
  /* ---- API 10 regression ---- */
  const parseRange=x=>{ if(Array.isArray(x)) return [addr(x[0]),addr(x[1])]; if(typeof x==='string'){ const m=/^\s*(.+?)\s*-\s*(.+?)\s*$/.exec(x); if(m) return [addr(m[1]),addr(m[2])]; } const a=addr(x); return [a,a]; };
  const u8b64=u=>u8ToB64(u), b64u8=t=>b64ToU8(t);
  const pngPixels=url=>new Promise((ok,ko)=>{ const im=new Image(); im.onload=()=>{ const c=document.createElement('canvas'); c.width=im.width; c.height=im.height; const x=c.getContext('2d'); x.drawImage(im,0,0); ok({w:im.width,h:im.height,d:x.getImageData(0,0,im.width,im.height).data}); }; im.onerror=()=>ko(E('BAD_ARG','baseline image unreadable')); im.src=url; });
  const diffPix=(A,B,tol,dd)=>{ let n=0,x0=1e9,y0=1e9,x1=-1,y1=-1; for(let p=0;p<A.d.length;p+=4){ const d=Math.max(Math.abs(A.d[p]-B.d[p]),Math.abs(A.d[p+1]-B.d[p+1]),Math.abs(A.d[p+2]-B.d[p+2])); const hit=d>tol; if(hit){ n++; const q=p/4,x=q%A.w,y=(q/A.w)|0; if(x<x0)x0=x; if(x>x1)x1=x; if(y<y0)y0=y; if(y>y1)y1=y; } if(dd){ dd[p]=hit?255:A.d[p]>>2; dd[p+1]=hit?0:A.d[p+1]>>2; dd[p+2]=hit?0:A.d[p+2]>>2; dd[p+3]=255; } } return {diffPixels:n,bbox:n?{x:x0,y:y0,w:x1-x0+1,h:y1-y0+1}:null}; };
  const baselines={};
  const rams={}; let recd=null, inRec=0, replaying=false;
  const mem64=(from,to,ram)=>{ const f=()=>{ const w=W(), n=to-from+1, o=new Uint8Array(n); for(let i=0;i<n;i++) o[i]=w.wasm_peek(from+i); return o; }; return ram?withRam(f):f(); };
  const hash53=(str,seed=0)=>{ let h1=0xdeadbeef^seed,h2=0x41c6ce57^seed; for(let i=0;i<str.length;i++){ const c=str.charCodeAt(i); h1=Math.imul(h1^c,2654435761); h2=Math.imul(h2^c,1597334677); } h1=Math.imul(h1^(h1>>>16),2246822507)^Math.imul(h2^(h2>>>13),3266489909); h2=Math.imul(h2^(h2>>>16),2246822507)^Math.imul(h1^(h1>>>13),3266489909); return (4294967296*(2097151&h2)+(h1>>>0)).toString(16); };
  const LSP='c64.store.'; const memStore={};
  const lsOk=()=>{ try{ localStorage.setItem('c64.t','1'); localStorage.removeItem('c64.t'); return true; }catch(e){ return false; } };
  const METHODS=['start(opts)','ready()','stop()','reset({hard})','pause()','resume()','warp(on)','state()','type(key|[keys],{frames,releaseFrames,shift,ctrl,cbm})','keyDown(key|[keys])','keyUp(key|[keys])','sendText(text,{framesPerKey,releaseFrames,keepCase,noWait})','keyNames()','joy(dir,on,port) | joy(port,{up,down,left,right,fire},frames)','joyPulse(dir,ms,port)','fire(ms,port)',
    'loadRom(kind,data,{name})','clearRoms(kind)','roms()','loadFile(name,data,{autoload,program})','eject()','attach(8,data,name)','detach()','diskImage(drive,{bytes})','driveState(drive)','peek(a,n,{ram})','peekRange','peekWord','poke(a,v,{ram})','pokeRange','dump(a,n)','loadLabels(text)','label(name)',
    'screenInfo()','screenText()','screenCodes({addr})','loadEncoding(name,mapOrCdef,{block})','encodings()','findText(text|codes,{raw,all,exact,addr,len,map,enc})','border()','background()','cursor()','screenshot({rect,raw})','screenSave(name)','screenDiff(a,b,{tolerance,rect,image})','recordGif({frames,every,rect})','cycles()','frames()','framesExact()','runFrames(n)','runCycles(n)','runUntil(cond,{timeoutFrames,all}) cond: pc|pcIn|addr|mem|watch|screenText|screenRegex|text|cycles|when',
    'breakpoint(a)','breakpoints()','clearBreakpoints()','watch(a)','watchpoints()','clearWatchpoints()','regs()','measure(from,to,{timeoutFrames,n})','setRegs(r)','call(a,r,{timeoutFrames,noWait,frames})','step(n)','trace({until,max,last})','inspect(name)','sid()','sidTrace(frames,{every})','saveState(name,{export})','loadState(name|data)','states()','dropState(name)','regressSave(name,{ram,screen,only,exclude})','regressCheck(name|bundle,{ignore,tolerance,only,exclude,ram,screen,strict,includeCpu,image})','regressList()','recordVideo({frames,seconds,fps,mime,bitrate,scale})','grabBrowserVideoAndAudio({action,seconds,keyboard,joy1,joy2,scale,audio,audioGain})','runLoop(codice,{frames,every})','capStart({every})','capRun(kind,arg)','capTake(n)','capStop()','driveTrace(frames,{every,drive})','useLabels(set)','labelSets()','sprites()','stateHash({only,exclude})','disasm(a,n)','find(bytes|text,{from,to,ram,screen,max})','ramSnap(name,{from,to})','ramDiff(a,b)','recordStart()','recordStop()','replay(rec)','sendJoy(script,{port})','runScript(testo,{noWait})','scriptCheck(testo)','storeSet(k,v)','storeGet(k,def)','storeDel(k)','storeKeys()','storeExport()','storeImport(obj)','wasm(name,...args)','eval(code)','waitFor(text,ms)','info()','methods()','abort()','progress()','sleep(ms)'];
  const api={
    apiVersion:API_VERSION, build:APP_BUILD,
    info(){ return {build:APP_BUILD,api:API_VERSION,core:'VirtualC64 5.x (vc64web)',driveRom:st.drvRom||'1541-II'}; },
    /* ---- life cycle ---- */
    loadRom(kind,data,o={}){            // API 17: user ROMs instead of the embedded ones (effective from the next start()). kind = kernal(8192) | basic(8192) | chargen(4096) | floppy(16384: 1541 family only)
      const SZ={kernal:8192,basic:8192,chargen:4096,floppy:16384}; if(!SZ[kind]) throw E('BAD_ARG','kind: kernal | basic | chargen | floppy');
      const u=toBytes(data); if(u.length!==SZ[kind]) throw E('BAD_ARG','ROM '+kind+': attesi '+SZ[kind]+' byte, ricevuti '+u.length);
      st.roms[kind]={b64:u8ToB64(u),name:o.name||kind}; return {kind,bytes:u.length,name:st.roms[kind].name,needsRestart:true};
    },
    clearRoms(kind){ if(kind){ delete st.roms[kind]; } else st.roms={}; return {user:Object.keys(st.roms)}; },     // back to the embedded ROMs
    roms(){ const o={}; for(const k in st.roms) o[k]={name:st.roms[k].name,bytes:Math.floor(st.roms[k].b64.length*3/4)-(st.roms[k].b64.endsWith('==')?2:st.roms[k].b64.endsWith('=')?1:0)}; return {user:o,driveRom:st.drvRom||'1541-II',builtinDriveRoms:Object.keys(DRVROMS)}; },
    async start(opts={}){
      if(opts.roms){ for(const k in opts.roms) api.loadRom(k,opts.roms[k]); }
      if(opts.port) setPort(opts.port);
      if(opts.driveRom){ if(!DRVROMS[opts.driveRom]) throw new Error('invalid driveRom: '+opts.driveRom+' (1541 | 1541-II)'); st.drvRom=opts.driveRom; $('drvRom').value=opts.driveRom; savePrefs(); }
      if(opts.disk) st.disk={name:opts.disk.name,bin:toBytes(opts.disk.data)};
      if(typeof opts.autoload==='boolean') $('autoStart').checked=opts.autoload;
      if(typeof opts.program==='string') $('prgName').value=opts.program.toLowerCase();   // typed on the keyboard: the uppercase PETSCII name is written with the lowercase keys
      launch(); return api.ready(opts.timeout);
    },
    async ready(timeout=30000){
      const t0=Date.now();
      while(Date.now()-t0<timeout){
        try{ const w=W(); if(st.injected && Number(w.wasm_get_cpu_cycles())>3000000 && w.is_running()) return api.state(); }catch(e){}
        await sleep(100);
      }
      throw E('TIMEOUT','timeout waiting for the C64 to be ready');
    },
    stop(){ stop(); return true; },
    reset(o){ const w=W(); if(o&&o.hard) w.Module._wasm_hard_reset(); else w.wasm_reset(); w.reset_keyboard(); return true; },   // {hard:true} = spegni/riaccendi
    pause(){ halt(); return true; },
    async resume(){ await go(); return true; },
    warp(on){ const w=W(); const cur=Number(w.wasm_get_config('OPT_C64_WARP_MODE'))===2; if(on===undefined||on!==cur) w.action('toggle_warp'); return true; },
    state(){
      const o={started:st.running,injected:st.injected,port:st.port,kbd:$('app').dataset.kbd==='1',disk:st.disk?st.disk.name:null};
      try{ const w=W(); o.running=!frozen&&!!w.is_running(); o.frozen=frozen; o.warp=!!w.Module._wasm_is_warping(); o.cycles=Number(w.wasm_get_cpu_cycles()); o.disk8=!!w.wasm_has_disk('drive8'); o.driveRom=st.drvRom||'1541-II'; o.roms=JSON.parse(w.wasm_rom_info()); }catch(e){ o.error=e.message; }
      return o;
    },
    /* ---- input ---- */
    /* ---- keyboard input (API 9): C64 matrix, one command for keys, one for strings ---- */
    async type(keys,o={}){              // ONE key (character or name: 'w','RETURN','F1','RUN/STOP','SHIFT+A') or a LIST of simultaneous keys (['w','d']). {frames:3 (min 1), releaseFrames:3 (min 2), shift,ctrl,cbm,noWait}. For strings: sendText
      const ks=keysOf(keys,o), hold=chk('frames',o.frames===undefined?DEF_HOLD:o.frames,MIN_HOLD), rel=chk('releaseFrames',o.releaseFrames===undefined?DEF_REL:o.releaseFrames,MIN_REL);
      await bootWait(o); const w=W();
      ks.forEach(k=>w.wasm_schedule_key(KM[k][0],KM[k][1],1,0)); ks.forEach(k=>w.wasm_schedule_key(KM[k][0],KM[k][1],0,hold));
      await waitFrames(hold+rel); return {keys:ks,frames:hold+rel};
    },
    keyDown(keys,o={}){ const w=W(); keysOf(keys,o).forEach(k=>w.wasm_schedule_key(KM[k][0],KM[k][1],1,0)); return true; },     // held down (effective at the next emulated frame)
    keyUp(keys,o={}){ const w=W(); keysOf(keys,o).forEach(k=>w.wasm_schedule_key(KM[k][0],KM[k][1],0,0)); return true; },
    joy(dir,on,port){                  // joy('up',1[,port])  or  joy(port,{up,down,left,right,fire}[,frames]) = full state, with duration in frames
      if(typeof dir==='number'||(dir&&typeof dir==='object')){
        const pt=typeof dir==='number'?dir:st.port, S=typeof dir==='number'?on:dir, fr=typeof dir==='number'?port:on;
        const set=v=>{ const D=['up','down','left','right','fire']; for(const on of [0,1]) D.forEach(d=>{ const want=v&&!!S[d]; if((want?1:0)===on) W().action('j'+pt+d+on); }); };   // first the releases, then the presses (up/down share the axis)
        set(true); if(fr===undefined) return true;
        return api.runFrames(fr).then(()=>{ set(false); return true; });
      }
      W().action('j'+(port||st.port)+String(dir).toLowerCase()+(on?1:0)); return true; },   // up|down|left|right|fire
    async joyPulse(dir,ms=150,port){ api.joy(dir,1,port); await sleep(ms); api.joy(dir,0,port); return true; },
    fire(ms=120,port){ return api.joyPulse('fire',ms,port); },
    /* ---- file ---- */
    async loadFile(name,data,opts={}){   // .d64/.g64/.prg/.t64/.crt ; opts.autoload (d64), opts.program
      if(typeof opts.autoload==='boolean') $('autoStart').checked=opts.autoload;
      if(typeof opts.program==='string') $('prgName').value=opts.program.toLowerCase();   // typed on the keyboard: the uppercase PETSCII name is written with the lowercase keys
      mountDisk(name,toBytes(data));
      if(!st.running||!st.injected) return api.ready(opts.timeout);
      await sleep(600);
      // API 6: with autoload it waits for the sequence (reset, LOAD, RUN) to finish: before, loadFile returned after 0.6 s while the autoload went on (and could reset the machine in the middle of a test). {wait:false} = old behavior. With the emulator stopped it does not wait (the sequence cannot advance).
      if(opts.wait!==false&&!frozen){ const t0=Date.now(), lim=opts.timeout||180000; while(Date.now()-t0<lim&&frame.contentWindow.__autoDone===false) await sleep(100); if(frame.contentWindow.__autoDone===false) throw E('TIMEOUT','loadFile: autoload not finished in '+lim+' ms'); }
      return api.state();
    },
    eject(){ W().wasm_eject_disk('drive8'); st.disk=null; return true; },
    async runKeyTest(){ runTestPrg(); if(!st.running||!st.injected) await api.ready(); return api.waitFor('KEY AND JOYSTICK TEST',30000); },
    /* ---- memory (CPU view, I/O included) ---- */
    peek(a,n,o){                       // peek(a) -> byte ; peek(a,n) -> array of n bytes ; o={ram:true} = plain RAM (ignores $01)
      if(n&&typeof n==='object'){ o=n; n=undefined; } a=addr(a);
      const f=()=>{ const w=W(); if(n===undefined) return w.wasm_peek(a); const r=new Array(n); for(let i=0;i<n;i++) r[i]=w.wasm_peek((a+i)&0xffff); return r; };
      return o&&o.ram?withRam(f):f();
    },
    peekRange(a,n,o){ return api.peek(a,n,o); },
    peekWord(a,o){ const r=api.peek(a,2,o); return r[0]|(r[1]<<8); },
    poke(a,v,o){                       // v = byte or array/Uint8Array of bytes ; o={ram:true}
      a=addr(a); const b=typeof v==='number'?[v]:Array.from(toBytes(v));
      return (o&&o.ram?withRam:(f=>f()))(()=>{ const w=W(); for(let i=0;i<b.length;i++) w.wasm_poke((a+i)&0xffff,b[i]&0xff); return b.length; });
    },
    pokeRange(a,bytes,o){ return api.poke(a,bytes,o); },
    dump(a,n,o){ a=addr(a); const b=api.peek(a,n,o), L=[]; for(let i=0;i<n;i+=16){ const r=b.slice(i,i+16); L.push(hex(a+i,4)+': '+r.map(x=>hex(x,2)).join(' ')); } return L.join('\n'); },
    loadLabels(text,o={}){             // VICE format (.lbl) "al C:0840 .name"  or "name = $0840". {set:'lobby'} = separate set (it becomes the active one, unless activate:false; from any set it is read with 'lobby:name')
      const tgt=o.set?(labelSets[o.set]=o.replace===false&&labelSets[o.set]?labelSets[o.set]:{}):labels; let n=0; for(const ln of String(text).split(/\r?\n/)){
        let m=/^\s*al\s+(?:[A-Za-z]:)?([0-9a-fA-F]+)\s+\.?(\S+)/.exec(ln), v, k;
        if(m){ v=m[1]; k=m[2]; } else { m=/^\s*\.?([A-Za-z_][\w.]*)\s*=\s*\$?([0-9a-fA-F]+)/.exec(ln); if(m){ k=m[1]; v=m[2]; } }
        if(k){ tgt[k]=parseInt(v,16)&0xffff; n++; }
      } if(o.set&&o.activate!==false) labels=tgt; return n;
    },
    label(name){ return addr(name); },
    useLabels(set='default'){ if(!labelSets[set]) throw E('BAD_ARG','unknown label set: '+set+' ('+Object.keys(labelSets).join(', ')+')'); labels=labelSets[set]; return {set,count:Object.keys(labels).length}; },
    labelSets(){ const o={}; for(const k in labelSets) o[k]=Object.keys(labelSets[k]).length; return o; },
    /* ---- screen ---- */
    screenInfo(){                      // where the VIC reads screen and characters
      const w=W(), d11=w.wasm_peek(0xD011), d16=w.wasm_peek(0xD016), d18=w.wasm_peek(0xD018), dd=w.wasm_peek(0xDD00);
      const bank=3-(dd&3), screen=bank*0x4000+((d18>>4)&15)*0x400, chOff=((d18>>1)&7)*0x800, rom=(bank===0||bank===2)&&(chOff===0x1000||chOff===0x1800);
      return {bank,screen,charset:bank*0x4000+chOff,charsetRom:rom,lowercase:rom?chOff===0x1800:null,bitmap:!!(d11&0x20),ecm:!!(d11&0x40),multicolor:!!(d16&0x10),textMode:!(d11&0x20)};
    },
    screenText(){                     // 25 rows of 40 columns from the screen RAM chosen by the VIC ($D018/$DD00); lowercase from the character set
      const i=api.screenInfo(), lower=i.lowercase===null?!!(W().wasm_peek(0xD018)&2):i.lowercase;
      const b=withRam(()=>{ const w=W(), o=new Array(1000); for(let k=0;k<1000;k++) o[k]=w.wasm_peek(i.screen+k); return o; }), L=[];
      for(let r=0;r<25;r++){ let line=''; for(let c=0;c<40;c++) line+=sc2txt(b[r*40+c],lower); L.push(line.replace(/\s+$/,'')); }
      return L.join('\n');
    },
    screenCodes(o){                   // API 18: the 1000 raw screen codes of the screen RAM chosen by the VIC, as an array; independent of the character set. API 20: {addr} = RAM address to read instead of the VIC one (games with the text screen elsewhere / double buffer)
      const base=(o&&o.addr!==undefined)?addr(o.addr):api.screenInfo().screen; return withRam(()=>{ const w=W(), r=new Array(1000); for(let k=0;k<1000;k++) r[k]=w.wasm_peek(base+k); return r; });
    },
    loadEncoding(name,src,o={}){            // API 23: registers a named encoding for findText/runUntil/wait text ({enc:name}). src = object {"A":57,"0-9":45,...} or text with 64tass .cdef lines
      if(!name) throw E('BAD_ARG','loadEncoding: name missing'); let m={};
      if(typeof src==='string'){ let n=0;
        // API 24: symbols as code (".cdef "A","A",G_A") resolved from "NAME = value" lines of the same text or from the loaded labels;
        // with .enc "name" blocks only the .cdef of the block with the same name as the encoding (or o.block) are read
        const lines=src.split(/\r?\n/).map(r=>r.replace(/;.*$/,'').trim()), sym={}, blk=(o&&o.block)||name, hasEnc=lines.some(l=>/^\.enc\b/i.test(l));
        for(const l of lines){ const m=/^([A-Za-z_][\w.]*)\s*(?:=|\.equ\b|:=)\s*(\$[0-9a-f]+|0x[0-9a-f]+|%[01]+|\d+)\s*$/i.exec(l); if(m){ const t=m[2]; sym[m[1]]=t[0]==='$'?parseInt(t.slice(1),16):t[0]==='%'?parseInt(t.slice(1),2):/^0x/i.test(t)?parseInt(t,16):+t; } }
        const val=t=>{ t=t.trim(); if(/^\$[0-9a-f]+$/i.test(t)) return parseInt(t.slice(1),16); if(/^0x[0-9a-f]+$/i.test(t)) return parseInt(t,16); if(/^%[01]+$/.test(t)) return parseInt(t.slice(1),2); if(/^\d+$/.test(t)) return +t; if(t in sym) return sym[t]; if(t in labels) return labels[t]; return null; };
        let cur=null;
        for(const l of lines){ const me=/^\.enc\s+"([^"]*)"/i.exec(l); if(me){ cur=me[1]; continue; } if(!/^\.cdef\b/i.test(l)) continue; if(hasEnc&&cur!==blk) continue;
          const a=l.replace(/^\.cdef\s*/i,''), q=[...a.matchAll(/"((?:[^"\\]|\\.)*)"/g)].map(x=>x[1]), last=a.slice(a.lastIndexOf(',')+1), code0=val(last); if(code0===null) throw E('BAD_ARG','loadEncoding: unresolved code «'+last.trim()+'» in the line: '+l+' (NAME = value lines in the same text or loadLabels are needed)'); const code=code0;
          let lo,hi; if(q.length===2){ lo=q[0]; hi=q[1]; } else if(q.length===1&&[...q[0]].length===2){ [lo,hi]=[...q[0]]; } else if(q.length===1&&[...q[0]].length===1){ lo=hi=q[0]; } else throw E('BAD_ARG','loadEncoding: .cdef line not recognized: '+l);
          for(let c=lo.charCodeAt(0),k=0;c<=hi.charCodeAt(0);c++,k++){ m[String.fromCharCode(c)]=(code+k)&255; n++; } }
        if(!n) throw E('BAD_ARG','loadEncoding: no .cdef line found'+(hasEnc?' in the .enc block "'+blk+'" (use {"block":"name"})':'')); }
      else if(src&&typeof src==='object'){ for(const k of Object.keys(src)){ const v=src[k]|0; if(k.length===3&&k[1]==='-'){ for(let c=k.charCodeAt(0);c<=k.charCodeAt(2);c++) m[String.fromCharCode(c)]=(v+c-k.charCodeAt(0))&255; } else if([...k].length===1) m[k]=v&255; else throw E('BAD_ARG','loadEncoding: chiave «'+k+'»'); } }
      else throw E('BAD_ARG','loadEncoding: an object or the .cdef text is needed');
      encs[name]=m; return {name,chars:Object.keys(m).length};
    },
    encodings(){ const o={}; for(const k in encs) o[k]=Object.keys(encs[k]).length; return o; },
    findText(t,o={}){                 // API 18: searches text in the screen RAM as SCREEN CODE (not as KERNAL text): it also works with custom fonts/charsets if the codes are the standard ones.
      // t = string (A-Z case-insensitive, 0-9 and punctuation 0x20-0x3F as ASCII, '@'=0) or array of raw codes (o={raw:true} or array). Ignores bit 7 (reverse) unless o.exact.
      // Returns {row,col,addr} of the first occurrence (row from 0, column from 0) or null; o.all=true -> list. The match stays within one row.
      if(o.enc!==undefined){ if(!encs[o.enc]) throw E('BAD_ARG','unknown encoding: '+o.enc+' (loaded: '+(Object.keys(encs).join(', ')||'none')+'; use loadEncoding)'); o=Object.assign({},o,{map:Object.assign({},encs[o.enc],o.map||{})}); }   // API 23: named encoding (loadEncoding)
      const cmap=(()=>{ if(!o.map) return null; const m={}; for(const k of Object.keys(o.map)){ const v=o.map[k]|0; if(k.length===3&&k[1]==='-'){ for(let q=k.charCodeAt(0);q<=k.charCodeAt(2);q++) m[String.fromCharCode(q)]=v+q-k.charCodeAt(0); } else if([...k].length===1) m[k]=v; else throw E('BAD_ARG','findText map: chiave «'+k+'»: use a character or a range «a-b»'); } return m; })();   // API 21: map={"0-9":45,"/":55,"A-Z":1} = the game's own encoding (character or range -> code); the text is translated with the map, with no automatic case folding
      const raw=!!cmap||Array.isArray(t), codes=cmap?[...String(t)].map(ch=>{ const k=(ch in cmap)?ch:(ch.toUpperCase() in cmap)?ch.toUpperCase():(ch.toLowerCase() in cmap)?ch.toLowerCase():null; if(k===null) throw E('BAD_ARG','findText: «'+ch+'» not in map'); return cmap[k]&255; }):Array.isArray(t)?t.map(x=>x&255):[...String(t)].map(ch=>{ let c=ch.toUpperCase().charCodeAt(0); if(c>=65&&c<=90) return c-64; if(ch==='@') return 0; if(c>=32&&c<=63) return c; if(ch==='\u00a3') return 28; throw E('BAD_ARG','findText: character not representable as screen code: '+JSON.stringify(ch)+' (use an array of codes)'); });
      if(!codes.length) throw E('BAD_ARG','findText: testo vuoto');
      if(o.len!==undefined){   // API 23: linear search in [addr, addr+len) without 40-column paging (buffer, not screen). Returns {offset,addr}
        if(o.addr===undefined) throw E('BAD_ARG','findText: len richiede addr'); const a0=addr(o.addr), L=Math.max(0,Math.min(65536-a0,Math.floor(o.len))), buf=withRam(()=>{ const w=W(), b=new Array(L); for(let k=0;k<L;k++) b[k]=w.wasm_peek(a0+k); return b; }), norm=c=>o.exact?c:(c&127), nz=x=>{ x=norm(x); return (!raw&&!o.exact&&x>=65&&x<=90)?x-64:x; }, res=[];
        for(let c=0;c+codes.length<=L;c++){ let ok=true; for(let k=0;k<codes.length;k++){ if(nz(buf[c+k])!==(raw?norm(codes[k]):codes[k])){ ok=false; break; } } if(ok){ res.push({offset:c,addr:a0+c}); if(!o.all) return res[0]; } }
        return o.all?res:null;
      }
      const scr=api.screenCodes(o.addr!==undefined?{addr:o.addr}:undefined), i=o.addr!==undefined?{screen:addr(o.addr)}:api.screenInfo(), norm=c=>o.exact?c:(c&127), nz=x=>{ x=norm(x); return (!raw&&!o.exact&&x>=65&&x<=90)?x-64:x; }, res=[];
      for(let r=0;r<25;r++) for(let c=0;c+codes.length<=40;c++){ let ok=true; for(let k=0;k<codes.length;k++){ if(nz(scr[r*40+c+k])!==(raw?norm(codes[k]):codes[k])){ ok=false; break; } } if(ok){ res.push({row:r,col:c,addr:i.screen+r*40+c}); if(!o.all) return res[0]; } }
      return o.all?res:null;
    },
    border(){ return W().wasm_peek(0xD020)&15; },
    background(){ return W().wasm_peek(0xD021)&15; },
    cursor(){ const w=W(); return {col:w.wasm_peek(0xD3),row:w.wasm_peek(0xD6)}; },
    screenshot(o){                      // with no arguments: PNG data-URL. {rect:{x,y,w,h}} crop ; {raw:true} -> {width,height,data:base64 RGBA}
      if(!o) return W().document.querySelector('canvas').toDataURL('image/png');
      const g=grab(o); if(o.raw) return {width:g.w,height:g.h,data:u8ToB64(new Uint8Array(g.d.buffer))};
      const c=document.createElement('canvas'); c.width=g.w; c.height=g.h; c.getContext('2d').putImageData(new ImageData(g.d,g.w,g.h),0,0); return c.toDataURL('image/png'); },
    /* ---- deterministic time: the emulator stays STOPPED between one call and the next ---- */
    cycles(){ return cyc(); },
    frames(){ return Math.floor(cyc()/FR); },            // whole frames since power-on (API 6: before it was fractional)
    framesExact(){ return cyc()/FR; },
    async runFrames(n,o={}){            // advances exactly n frames (PAL, 19656 cycles) and stops
      n=Math.max(0,Math.floor(n)); if(n===0){ halt(); return {reason:'frames',cycles:cyc(),frames:0}; }
      if(o.fast&&n>2*FAST_MARGIN&&!(cap&&cap.on)){   // API 14: the bulk with warp, the last FAST_MARGIN frames at normal speed: exact (if warp overshoots the margin, exact:false)
        const w=W(), start=cyc(), was=Number(w.wasm_get_config('OPT_C64_WARP_MODE'))===2; if(!was) api.warp(true);
        let r; try{ r=await run0({maxFrames:n-FAST_MARGIN}); } finally{ if(!was) api.warp(false); }
        if(!was) await run0({maxFrames:1});   // the first run after warp(false) still advances at warp speed (measured +26 frames): a separate step absorbs it
        const rest=Math.round(n-(cyc()-start)/FR); if(rest<0) return Object.assign(r,{exact:false,frames:(cyc()-start)/FR,overshoot:-rest});
        if(rest>0) await run0x({maxFrames:rest,exact:o.exact!==false}); return {reason:'frames',cycles:cyc(),frames:(cyc()-start)/FR,exact:Math.abs((cyc()-start)/FR-n)<0.01}; }
      return run({maxFrames:n,exact:o.exact!==false,_forceRetry:o._forceRetry,_noResched:o._noResched});   // API 23: exact by default (snapshot+check+repeat); {exact:false} = previous behavior
    },
    async runCycles(n,o={}){            // rounds up to whole frames: the core offers no finer granularity
      return api.runFrames(Math.ceil(n/FR),o);
    },
    async runUntil(c,o={}){             // {pc|[pc..]} {pcIn:[a,b]} {addr,value,mask,not} {mem:[a,v]} {watch:a|[a..]} {screenText|screenRegex} {cycles} {when:{addr,value}} ; o={timeoutFrames,all}
      const max=o.timeoutFrames||3000, conds=[], desc=[]; let pcs=[], wps=[];
      const mk=x=>{ const a=addr(x.addr), m=x.mask===undefined?0xff:x.mask, v=x.value&m; return ()=>{ const hit=(W().wasm_peek(a)&m)===v; return x.not?!hit:hit; }; };
      if(c.pc!==undefined){ pcs=[].concat(c.pc).map(addr); desc.push('pc '+pcs.map(x=>'$'+hex(x)).join('|')); }
      if(c.pcIn!==undefined){ const lo=addr(c.pcIn[0]), hi=addr(c.pcIn[1]); if(hi<lo||hi-lo>63) throw E('BAD_ARG','pcIn: range of 1 to 64 addresses (one breakpoint per address)'); for(let a=lo;a<=hi;a++) pcs.push(a); desc.push('pc in $'+hex(lo)+'-$'+hex(hi)); }
      if(c.watch!==undefined){ wps=[].concat(c.watch).map(addr); if(wps.length>16) throw E('BAD_ARG','watch: at most 16 addresses'); desc.push('watch '+wps.map(x=>'$'+hex(x)).join('|')); }
      if(c.addr!==undefined){ conds.push(mk(c)); desc.push('['+'$'+hex(addr(c.addr))+']'+(c.not?'!=':'==')+'$'+hex(c.value&(c.mask===undefined?0xff:c.mask),2)); }
      if(c.mem!==undefined){ conds.push(mk({addr:c.mem[0],value:c.mem[1],mask:c.mem[2]})); desc.push('mem[$'+hex(addr(c.mem[0]))+']==$'+hex(c.mem[1],2)); }
      if(c.text!==undefined){ const tx=c.text, to=c.textOpts||{}; conds.push(()=>api.findText(tx,to)!==null); desc.push('findText '+JSON.stringify(tx)); }   // API 18: {text:'...'|[codes]} searches in screen code (see findText)
      if(c.screenText!==undefined||c.screenRegex!==undefined){
        let re; const t=c.screenRegex!==undefined?c.screenRegex:c.screenText;
        if(t instanceof RegExp) re=t; else if(c.screenRegex!==undefined){ const m=/^\/(.*)\/([a-z]*)$/s.exec(String(t)); re=m?new RegExp(m[1],m[2]):new RegExp(String(t),'i'); }
        else { const m=/^\/(.*)\/([a-z]*)$/s.exec(String(t)); re=m?new RegExp(m[1],m[2]):null; }
        const needle=re?null:String(t).toUpperCase();
        conds.push(()=>{ const x=api.screenText(); return re?re.test(x):x.toUpperCase().includes(needle); });
        desc.push('screenText '+(re||JSON.stringify(t)));
      }
      if(c.screenMatch!==undefined){ const nm=c.screenMatch, mx=c.maxDiff||0, tl=c.tolerance||0; if(!shots[nm]) throw E('NO_SHOT','screen not saved: '+nm); conds.push(()=>api.screenDiff(nm,null,{tolerance:tl,rect:c.rect}).diffPixels<=mx); desc.push('screenMatch '+nm+' (<='+mx+' pixel diversi)'); }
      if(c.cycles!==undefined){ conds.push(()=>cyc()>=c.cycles); desc.push('cycles>='+c.cycles); }
      if(!pcs.length&&!wps.length&&!conds.length) throw E('BAD_ARG','runUntil: condition missing (pc, pcIn, watch, addr, mem, screenText, screenRegex, screenMatch or cycles)');
      const when=c.when?mk(c.when):null; let left=max, acc=0, r;
      for(;;){
        r=await run({maxFrames:left,pcs,watch:wps,cond:conds.length?()=>(o.all?conds.every(f=>f()):conds.some(f=>f())):null});
        acc+=r.frames;
        if(r.reason==='pc'&&c.whenRegs){ const rg=await api.regs(); const ok=Object.keys(c.whenRegs).every(k=>{ if(!['a','x','y','p'].includes(k)) throw E('BAD_ARG','whenRegs: only a, x, y, p'); return (rg[k]&255)===(addr(c.whenRegs[k])&255); }); if(!ok){ left-=r.frames; if(left<=0){ r.reason='frames'; break; } continue; } }   // API 21: {pc, whenRegs:{a,x,y,p}}: stops only if the registers match (read with regs(): ~40 cycles added at every stop)
        if((r.reason==='pc'||r.reason==='watch')&&when&&!when()){ left-=r.frames; if(left<=0){ r.reason='frames'; break; } continue; }   // "pc with condition": if the condition does not hold it resumes
        break;
      }
      r.frames=acc;
      if(r.reason==='frames') throw E('TIMEOUT','timeout: '+desc.join(' / ')+' not reached in '+max+' frames');
      if(r.reason==='pc'){ try{ r.pc=cpuPos().pc; }catch(e){} }
      return r;
    },
    async measure(from,to,o={}){        // API 21: exact cycles between two PCs: runs to PC=from (then cycles=0), then to PC=to. {timeoutFrames} for each step (default 3000). Returns {from,to,cycles,fromCycles,toCycles}.
      // API 22: {n:N} repeats N times (after to it goes back to from) and also returns {n,min,max,mean,samples} (samples at most 200). Every pass costs ~0.2-0.4 s of wall clock (core halt/run)
      const N=Math.max(1,Math.floor(o.n||1)), S=[]; let last=null;
      for(let k=0;k<N;k++){
        const a=await api.runUntil({pc:from},{timeoutFrames:o.timeoutFrames}); const c0=cyc(); const b=await api.runUntil({pc:to},{timeoutFrames:o.timeoutFrames}); const c1=cyc();
        S.push(c1-c0); last={from:addr(from),to:addr(to),cycles:c1-c0,fromCycles:c0,toCycles:c1,frames:Math.round((c1-c0)/FR*100)/100,framesToFrom:a.frames,framesToTo:b.frames};
      }
      if(N===1) return last;
      return Object.assign(last,{n:N,min:Math.min(...S),max:Math.max(...S),mean:Math.round(S.reduce((x,y)=>x+y,0)/N*10)/10,samples:S.slice(0,200)});
    },
    /* ---- CPU (through the core debugger; see the limits in the documentation) ---- */
    breakpoint(a){ ensureDbg(); return bpAdd(addr(a)); },
    clearBreakpoints(){ ensureDbg(); const l=bpList(); bpDel(l.map(x=>x.id)); return l.length; },
    breakpoints(){ ensureDbg(); return bpList(); },
    async regs(o={}){                   // {pc,line,cycle,cycles} ; with full (default) also a,x,y,p,sp: uses 33 bytes of RAM and ~40 cycles
      ensureDbg(); const r=Object.assign(cpuPos(),{cycles:cyc()}); if(o.full!==false) Object.assign(r,await captureRegs(o.scratch)); return r;
    },
    async setRegs(r,o={}){              // {pc,a,x,y,p} ; sp cannot be changed. The emulator must be stopped.
      if(r.pc!==undefined) r=Object.assign({},r,{pc:addr(r.pc)});          // API 6: pc also as a label or the string '$C000'
      ensureDbg(); const cur=await api.regs({scratch:o.scratch}); const v=Object.assign({},cur,r);
      if(['a','x','y','p'].some(k=>r[k]!==undefined)) await execRestore(v,o.scratch);
      rsh('g 0x'+hex(v.pc)); return api.regs({scratch:o.scratch,full:false});
    },
    progress(){ const r=prog.run, l=prog.loop; return {frozen,cycles:cyc(),run:r?{frames:Math.round((cyc()-r.start)/FR*100)/100,of:r.max}:null,loop:l?{iterations:l.i,frames:l.fr,of:l.max}:null}; },   // API 18: progress of the running job (the daemon exposes it in /status, c64 status, also while a job runs)
    abort(){ abortGen++; try{ W().wasm_halt(); frozen=true; setPausedUi(true); }catch(e){} return {aborted:true,cycles:cyc()}; },   // API 18: interrupts the running execution (runFrames/runUntil/runLoop/script): the emulator stays stopped. The daemon calls it by itself if the client disconnects (/abort, c64 abort)
    async call(a,r={},o={}){            // JSR a (with a/x/y as input) and return; registers and PC restored. Returns {a,x,y,p}.  API 18: {noWait:true,frames:N} = jumps to the routine (JMP, a/x/y as input), lets it run N frames (default 2) and does NOT wait for the return: for routines that do not return (e.g. level change)
      if(o.noWait){ ensureDbg(); const scr=o.scratch||0x0334, A=addr(a); api.poke(scr,[0xA9,(r.a||0)&255,0xA2,(r.x||0)&255,0xA0,(r.y||0)&255,0x4C,A&255,A>>8],{ram:true}); rsh('g 0x'+hex(scr)); const rr=await run({maxFrames:o.frames||2}); return {started:true,pc:cpuPos().pc,frames:rr.frames}; }
      ensureDbg(); const scr=o.scratch||0x0334, pc0=cpuPos().pc, saved=Object.assign({},await captureRegs(scr),{pc:pc0});
      const V=scr+0x30, A=addr(a), code=[0xA9,(r.a||0)&255,0xA2,(r.x||0)&255,0xA0,(r.y||0)&255,0x20,A&255,A>>8,
        0x8D,V&255,V>>8, 0x8E,(V+1)&255,(V+1)>>8, 0x8C,(V+2)&255,(V+2)>>8, 0x08,0x68,0x8D,(V+3)&255,(V+3)>>8, 0xEA];
      const old=api.peek(scr,0x40,{ram:true}); api.poke(scr,code,{ram:true}); rsh('g 0x'+hex(scr));
      try{ await run({maxFrames:o.timeoutFrames||600,pcs:[scr+code.length-1]}); }
      catch(e){ throw e; }
      const out=api.peek(V,4,{ram:true}); api.poke(scr,old,{ram:true});
      const endPc=cpuPos().pc; if(endPc!==scr+code.length-1) { api.poke(scr,old,{ram:true}); rsh('g 0x'+hex(pc0)); throw E('CALL_TIMEOUT','call: the subroutine $'+hex(A)+' did not return within '+(o.timeoutFrames||600)+' frames (PC=$'+hex(endPc)+'); only PC and work area restored (registers a/x/y/p not). If the routine never returns by design use {noWait:true}: call(a,r,{noWait:true}); from a script: «call ADDR nowait»'); }
      await execRestore(saved,scr); rsh('g 0x'+hex(pc0));
      return {a:out[0],x:out[1],y:out[2],p:out[3]};
    },
    /* ---- disks and drive ---- */
    attach(drive,data,name){ if(drive&&drive!==8) throw new Error('only drive 8 is supported'); return api.loadFile(name||'disk.d64',data,{autoload:false}); },
    detach(){ return api.eject(); },
    diskImage(drive=8,o={}){            // current d64 from the drive (e.g. after a SAVE); base64, or Uint8Array with {bytes:true}
      const w=W(); if(!w.wasm_has_disk('drive'+drive)) throw new Error('no disk in drive '+drive);
      const j=JSON.parse(w.wasm_export_disk(drive)); const b=new Uint8Array(w.Module.HEAPU8.buffer,j.address,j.size).slice(0,j.size); w.Module._wasm_delete_disk();
      if(o.bytes) return b; let s=''; for(let i=0;i<b.length;i+=0x8000) s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000)); return btoa(s);
    },
    driveState(drive=8){                // drive status from the core debugger (the LED is not exposed)
      ensureDbg(); rsh('clear'); const t=rsh('? drive'+drive), g=k=>{ const m=new RegExp(k+'\\s*:\\s*(\\S+(?: \\S+)*?)(?:\\s{2,}|$)','m').exec(t); return m?m[1].trim():null; };
      const hd=/(\d+):(\d+)/.exec(g('Head position')||''), ht=hd?+hd[1]:null;
      return {type:g('TYPE'),hasDisk:g('Has disk')==='yes',motor:g('Motor')==='on',powerSave:g('In Power-Save Mode')==='yes',syncMark:g('SYNC')==='yes',readMode:g('Read mode')==='yes',
        halftrack:ht,track:ht===null?null:(ht+1)/2,headOffset:hd?+hd[2]:null};
    },
    /* ---- API 6: text, state, watchpoints, chips, trace, images ---- */
    async sendText(text,o={}){          // presses the keys in the keyboard MATRIX (does not write to $0277). "\n"=RETURN. Tokens {RUN/STOP} {F1}..{F8} {HOME} {CLR} {DEL} {INST} {UP}... {SHIFT+A} {CTRL+3} {C=+Q} {WAIT:30} {{}=brace
      const hold=chk('framesPerKey',o.framesPerKey===undefined?DEF_HOLD:o.framesPerKey,MIN_HOLD), gap=chk('releaseFrames',o.releaseFrames===undefined?DEF_REL:o.releaseFrames,MIN_REL), steps=sendParse(String(text),!!o.keepCase), ev=[]; let t=0, n=0; await bootWait(o);
      for(const s of steps){ if(s.wait){ t+=s.wait; continue; } for(const k of s.keys) ev.push([t,KM[k],1]); for(const k of s.keys) ev.push([t+hold,KM[k],0]); t+=hold+gap; n++; }
      const total=t+1, fz=frozen;
      // events are scheduled in windows of ~60 frames (the wasm_schedule_key delay is in emulated frames)
      const w=W(); let base=0, i=0;
      while(i<ev.length||base<total){
        const lim=Math.min(base+60,total);
        for(;i<ev.length&&ev[i][0]<lim;i++){ const e=ev[i]; w.wasm_schedule_key(e[1][0],e[1][1],e[2],e[0]-base); }
        await waitFrames(lim-base);
        base=lim;
      }
      return {keys:n,frames:total};
    },
    keyNames(){ return {keys:Object.keys(KM),named:Object.keys(NAMED),shifted:SHIFTED}; },
    async saveState(name='default',o={}){   // full core snapshot (CPU, RAM, VIC, SID, CIA, drive, disk). Kept in JS memory under 'name'; {export:true} -> also base64
      const w=W(), was=frozen; if(!was) halt();
      const j=JSON.parse(w.wasm_take_user_snapshot()), b=w.Module.HEAPU8.slice(j.address,j.address+j.size);
      const ip=inpAt(cyc()); snaps[name]={bytes:b,cycles:cyc(),inp:{joy:ip.joy,held:ip.held}}; if(!was) await go();
      const r={name,size:b.length,cycles:snaps[name].cycles}; if(ip.pending.length) r.pendingInputs=ip.pending.length; if(o.export) r.data=u8ToB64(b); return r;   // API 24: held inputs saved with the state (only in memory, not in the exported file); pendingInputs = keyboard events still scheduled, not part of the state
    },
    async loadState(src='default'){      // src = saved name, base64 or Uint8Array. Cycles and RAM go back exactly to the saved state; breakpoints and watchpoints must be checked again
      const w=W(), was=frozen; let b;
      if(typeof src==='string'&&snaps[src]) b=snaps[src].bytes; else if(typeof src==='string'&&!/^[A-Za-z0-9+\/=]{64,}$/.test(src)) throw E('NO_STATE','unknown state: '+src+' (salvati: '+Object.keys(snaps).join(', ')+')'); else b=toBytes(src);
      const cB=cyc(); w.wasm_halt(); const r=w.wasm_loadfile('state.vc64',b,b.length);
      frozen=true; setPausedUi(true);
      const pend=INP.ev.filter(e=>e.c>cB).length; INP.ev=[]; const tgt=(typeof src==='string'&&snaps[src]&&snaps[src].inp)||{joy:{1:{},2:{}},held:new Map()}; inpApply(tgt,cyc(),{});   // API 24: inputs as at save time (named state) or all released (file/base64) if(!was) await go(); if(!was) await go();
      const res={cycles:cyc(),result:r||'ok'}; if(pend) res.warning=pend+' keyboard events scheduled before loadState may still reach the core (the core queue is not emptied): wait for type/sendText to finish before saving or restoring'; return res;
    },
    states(){ const o={}; for(const k in snaps) o[k]={size:snaps[k].bytes.length,cycles:snaps[k].cycles}; return o; },
    dropState(name){ delete snaps[name]; return true; },
    watch(a){ ensureDbg(); return [].concat(a).map(x=>wpAdd(addr(x))); },     // watchpoint (stops AFTER the instruction that accesses the address)
    watchpoints(){ ensureDbg(); return wpList(); },
    clearWatchpoints(){ ensureDbg(); const l=wpList(); wpDel(l.map(x=>x.id)); return l.length; },
    inspect(name){                      // state of a core component via "? name": cpu mem vic cia1 cia2 sid c64 drive8 ...  -> {config,state,raw}
      ensureDbg(); rsh('clear'); const raw=rsh('? '+name); if(/Syntax error|Too few/.test(raw)) throw E('BAD_ARG','unknown component: '+name);
      const o={config:{},state:{},raw}; let sec=null;
      for(const ln of raw.split('\n')){ if(/^\s*Configuration:/.test(ln)){ sec='config'; continue; } if(/^\s*State:/.test(ln)){ sec='state'; continue; }
        const m=sec&&/^\s*([A-Za-z0-9][^:]*?)\s*:\s*(\S.*?)\s*$/.exec(ln); if(!m||/^\(\d+,\d+\)/.test(ln)||/0x[0-9a-f]{2}: 0x/.test(ln)&&m[1]==='Registers') continue;
        let v=m[2].split(/\s{2,}/)[0]; if(/^0x[0-9a-fA-F]+$/.test(v)) v=parseInt(v,16); else if(/^-?\d+$/.test(v)) v=+v; o[sec][m[1].trim()]=v; }
      return o;
    },
    sid(){                              // SID registers as the core sees them (29 bytes) + decoding of the 3 voices
      const i=api.inspect('sid'), regs=new Array(29).fill(0); for(const m of i.raw.matchAll(/0x([0-9a-f]{2}): 0x([0-9a-f]{2})/gi)) regs[parseInt(m[1],16)]=parseInt(m[2],16);
      return Object.assign({regs},sidDecode(regs),{model:i.config.REVISION,engine:i.config.ENGINE});
    },
    async sidTrace(frames=50,o={}){      // SID registers read every 'every' frames while the emulator advances (to check music)
      const every=o.every||1, out=[]; for(let f=0;f<frames;f+=every){ await api.runFrames(every); const s=api.sid(); out.push({frame:f+every,cycles:cyc(),regs:s.regs,voices:s.voices}); } return out;
    },
    async step(n=1){                    // executes n instructions (emulator stopped). Returns the executed instructions [{pc,bytes,asm,cycles}] (cycles = value BEFORE the instruction)
      ensureDbg(); const out=[]; let cur=curInstr(); for(let i=0;i<n;i++){ const r=await stepOnce(); out.push(Object.assign(cur,{cycles:r.cycles})); cur=r.next; } return out;
    },
    async trace(o={}){                  // executes instructions while pc is in o.until (max o.max, default 20000) and returns the LAST o.last (default 32): post-mortem diagnosis. Use it after loadState.
      ensureDbg(); const until=[].concat(o.until===undefined?[]:o.until).map(addr), max=o.max||20000, last=o.last||32, ring=[]; let reached=false, i=0, cur=curInstr();
      for(;i<max;i++){ if(i>0&&until.includes(cur.pc)){ reached=true; break; } const r=await stepOnce(); ring.push(Object.assign(cur,{cycles:r.cycles})); if(ring.length>last) ring.shift(); cur=r.next; }
      return {instructions:i,reached,pc:cur.pc,last:ring};
    },
    wasm(name,...args){ const w=W(); if(typeof w[name]!=='function') throw E('BAD_ARG','unknown wasm function: '+name); return w[name](...args); },
    screenSave(name='default',o={}){ const g=grab(o); shots[name]=g; return {name,width:g.w,height:g.h}; },
    screenDiff(a,b,o={}){               // compares two saved screens (or null = the current one). {tolerance:0..255 per channel, rect:{x,y,w,h}, image:true -> PNG of the differences}
      const A=a?shots[a]:grab(o), B=b?shots[b]:grab(o); if(!A||!B) throw E('NO_SHOT','screen not saved: '+(a&&!shots[a]?a:b));
      if(A.w!==B.w||A.h!==B.h) throw E('BAD_ARG','dimensioni diverse'); const tol=o.tolerance||0; let n=0,x0=1e9,y0=1e9,x1=-1,y1=-1; const dd=o.image?new Uint8ClampedArray(A.d.length):null;
      for(let p=0;p<A.d.length;p+=4){ const d=Math.max(Math.abs(A.d[p]-B.d[p]),Math.abs(A.d[p+1]-B.d[p+1]),Math.abs(A.d[p+2]-B.d[p+2])); const hit=d>tol; if(hit){ n++; const q=p/4,x=q%A.w,y=(q/A.w)|0; if(x<x0)x0=x; if(x>x1)x1=x; if(y<y0)y0=y; if(y>y1)y1=y; }
        if(dd){ dd[p]=hit?255:A.d[p]>>2; dd[p+1]=hit?0:A.d[p+1]>>2; dd[p+2]=hit?0:A.d[p+2]>>2; dd[p+3]=255; } }
      const r={same:n===0,diffPixels:n,ratio:n/(A.w*A.h),width:A.w,height:A.h,bbox:n?{x:x0,y:y0,w:x1-x0+1,h:y1-y0+1}:null};
      if(dd){ const c=document.createElement('canvas'); c.width=A.w; c.height=A.h; c.getContext('2d').putImageData(new ImageData(dd,A.w,A.h),0,0); r.image=c.toDataURL('image/png'); } return r;
    },
    async recordGif(o={}){              // advances o.frames frames (emulator stopped) capturing every o.every and returns an animated GIF in base64 {data,frames,width,height,bytes}
      const n=o.frames||50, every=o.every||2, shotsA=[]; let w0=0,h0=0;
      for(let f=0;f<n;f+=every){ if(f>0||o.skipFirst) await api.runFrames(every); const g=grab(o); shotsA.push(g.d); w0=g.w; h0=g.h; }
      const gif=gifEncode(shotsA,w0,h0,Math.max(2,Math.round(every*2))); return {data:u8ToB64(gif),frames:shotsA.length,width:w0,height:h0,bytes:gif.length,mime:'image/gif'};
    },
    /* ---- API 7 ---- */
    sprites(){                          // 8 sprites from the VIC registers + pointers (current VIC bank). x includes bit 8 ($D010)
      const w=W(), i=api.screenInfo(), g=a=>w.wasm_peek(a), msb=g(0xD010), en=g(0xD015), xe=g(0xD01D), ye=g(0xD017), mc=g(0xD01C), pr=g(0xD01B);
      const ptr=withRam(()=>[0,1,2,3,4,5,6,7].map(n=>w.wasm_peek(i.screen+0x3F8+n)));
      const list=[0,1,2,3,4,5,6,7].map(n=>({n,enabled:!!(en>>n&1),x:g(0xD000+2*n)|((msb>>n&1)<<8),y:g(0xD001+2*n),color:g(0xD027+n)&15,multicolor:!!(mc>>n&1),expandX:!!(xe>>n&1),expandY:!!(ye>>n&1),behindBackground:!!(pr>>n&1),pointer:ptr[n],dataAddr:i.bank*0x4000+ptr[n]*64}));
      return {sprites:list,multicolor1:g(0xD025)&15,multicolor2:g(0xD026)&15,bank:i.bank};
    },
    stateHash(o={}){                    // per-component hash from the core "checksums" command (Memory=RAM+I/O, CPU, CIA1/2, VIC, SID, Drive8...) + overall hash. o.only / o.exclude = component names
      ensureDbg(); rsh('clear'); const t=rsh('checksums'), comp={}, cnt={}, only=o.only&&[].concat(o.only), ex=[].concat(o.exclude||[]);
      for(const m of t.matchAll(/^\s*(\S+)\s*:\s*0x([0-9a-f]+)\s+(\d+) bytes/gim)){ const k=m[1]; if(only&&!only.includes(k)) continue; if(ex.includes(k)) continue; cnt[k]=(cnt[k]||0)+1; comp[cnt[k]>1?k+'#'+cnt[k]:k]=m[2]; }
      if(!Object.keys(comp).length) throw E('CORE','checksums not readable');
      return {hash:hash53(Object.entries(comp).filter(e=>o.includeCpu||e[0]!=='CPU').map(e=>e[0]+'='+e[1]).join(';')),components:comp,cycles:cyc(),cpuInHash:!!o.includeCpu};   // API 14: the CPU component (it depends on the debugger history: the first call after the debugger starts differs) is excluded from the overall hash, unless includeCpu
    },
    disasm(a,n=16){                     // disassembles n instructions of the CPU view from a (the core prints blocks of 16): [{pc,bytes,asm}]
      ensureDbg(); const out=[]; let cur=addr(a);
      while(out.length<n){ rsh('clear'); const t=rsh('d 0x'+hex(cur)); let got=0;
        for(const m of t.matchAll(/^(?:->|  )\s*([0-9A-F]{4})\s+((?:[0-9A-F]{2} )+)\s*(.*?)\s*$/gm)){ const bytes=m[2].trim(); out.push({pc:parseInt(m[1],16),bytes,asm:m[3]}); got++; cur=(parseInt(m[1],16)+bytes.split(' ').length)&0xffff; if(out.length>=n) break; }
        if(!got) throw E('CORE','disasm: no instruction read at $'+hex(cur)); }
      return out;
    },
    find(pat,o={}){                     // searches a byte sequence (array) or an ASCII string; {from,to,ram:true,max:256,screen:true (screen codes)} -> addresses
      const from=o.from===undefined?0:addr(o.from), to=o.to===undefined?0xffff:addr(o.to);
      let b=typeof pat==='string'?[...pat].map(c=>{ let v=c.charCodeAt(0); if(o.screen){ if(v>=64&&v<96) v-=64; } return v&255; }):Array.from(pat);
      if(!b.length) throw E('BAD_ARG','find: sequenza vuota'); const m=mem64(from,to,o.ram), out=[], max=o.max||256;
      for(let i=0;i+b.length<=m.length&&out.length<max;i++){ let k=0; while(k<b.length&&m[i+k]===b[k]) k++; if(k===b.length) out.push(from+i); } return out;
    },
    ramSnap(name='default',o={}){       // snapshots a memory range (default $0000-$FFFF, RAM view) for ramDiff
      const from=o.from===undefined?0:addr(o.from), to=o.to===undefined?0xffff:addr(o.to); rams[name]={from,to,d:mem64(from,to,o.ram!==false)}; return {name,from,to,size:to-from+1};
    },
    ramDiff(a,b,o={}){                  // differences between two snapshots (b=null: current state): {count,changes:[{addr,a,b}]} (max o.max=1000). Finds the address of score/lives
      const A=rams[a]; if(!A) throw E('NO_SHOT','memory snapshot not saved: '+a); let Bd; if(b){ if(!rams[b]) throw E('NO_SHOT','memory snapshot not saved: '+b); Bd=rams[b].d; } else Bd=mem64(A.from,A.to,o.ram!==false);
      const ch=[]; let n=0, max=o.max||1000; for(let i=0;i<A.d.length;i++) if(A.d[i]!==Bd[i]){ n++; if(ch.length<max) ch.push({addr:A.from+i,a:A.d[i],b:Bd[i]}); } return {count:n,changes:ch};
    },
    driveTrace(frames=50,o={}){ return (async()=>{ const every=o.every||1, out=[]; for(let f=0;f<=frames;f+=every){ if(f) await api.runFrames(every); const s=api.driveState(o.drive||8); out.push({frame:f,cycles:cyc(),track:s.track,halftrack:s.halftrack,headOffset:s.headOffset,motor:s.motor,syncMark:s.syncMark,readMode:s.readMode}); } return out; })(); },   // head history: one sample every 'every' frames (the LED is not exposed)
    async runLoop(code,o={}){           // API 14: runs a control loop INSIDE the page (no HTTP per step). code = JS function body with (c64,i,state); return false = end. o={frames:N (maximum), every:2 (frames per step)}
      // API 18: inside the loop joy(port,state,frames) does NOT advance the emulator: it presses at once and releases after 'frames' loop frames (no await needed). Before it did its own runFrames
      // concurrently with the loop one, and the loop got stuck.
      const AF=Object.getPrototypeOf(async function(){}).constructor, fn=new AF('c64','i','state',String(code)), every=Math.max(1,Math.floor(o.every||2)), max=o.frames||1e9, state={}; let i=0, fr=0;
      const gA=abortGen, pend=[], loopApi=Object.create(api), lp=prog.loop={i:0,fr:0,max:o.frames||null};
      loopApi.joy=(a,b,c)=>{ const num=typeof a==='number', obj=a&&typeof a==='object', S=num?b:a, hold=num?c:b;
        if(!(num||obj)||hold===undefined) return api.joy(a,b,c);
        const pt=num?a:st.port; api.joy(pt,S); pend.push({at:fr+Math.max(1,Math.floor(hold)),pt}); return true; };
      const rel=p=>p.fn?p.fn():api.joy(p.pt,{});
      loopApi.type=(keys,to={})=>{ const ks=keysOf(keys,to), hold=chk('frames',to.frames===undefined?DEF_HOLD:to.frames,MIN_HOLD), w=W(); ks.forEach(k=>w.wasm_schedule_key(KM[k][0],KM[k][1],1,0)); pend.push({at:fr+hold,fn:()=>{ const w2=W(); ks.forEach(k=>w2.wasm_schedule_key(KM[k][0],KM[k][1],0,0)); }}); return {keys:ks,frames:hold}; };   // API 24: release handled by the loop (like joy with a duration), no future event in the core queue   // API 24: inside runLoop type() does not advance the core (before it started a concurrent runFrames)
      const ex=o.exact!==false, RF=n=>api.runFrames(n,{exact:ex,_forceRetry:o._forceRetry&&(i%(o._forceEvery||1)===0)?o._forceRetry:0,_noResched:o._noResched}), cS=cyc(), anom=[], r0=xst.retries; let rPrev=xst.retries;   // API 23: passi esatti + diagnostica
      try{
        for(;fr<max;i++){
          if(abortGen!==gA) throw E('ABORTED','runLoop interrupted by abort()');
          lp.i=i; lp.fr=fr; const r=await fn(loopApi,i,state); if(r===false) break;
          const next=fr+every;
          pend.sort((x,y)=>x.at-y.at);
          while(pend.length&&pend[0].at<next){ const p=pend.shift(); if(p.at>fr){ await RF(p.at-fr); } fr=Math.max(fr,p.at); rel(p); }
          if(next>fr){ await RF(next-fr); fr=next; }
          if(xst.retries!==rPrev){ if(anom.length<200) anom.push([i,xst.retries-rPrev]); rPrev=xst.retries; }
          while(pend.length&&pend[0].at<=fr) rel(pend.shift());
        }
      } finally { if(prog.loop===lp) prog.loop=null; while(pend.length) rel(pend.shift()); }
      const fa=(cyc()-cS)/FR; const rt=xst.retries-r0; return {iterations:i,frames:fr,framesActual:fa,exact:Math.abs(fa-fr)<0.01,retriesTotal:rt,retriesTruncated:anom.length>=200&&anom.reduce((a,x)=>a+x[1],0)<rt,retries:anom,state};   // API 25: retries lists at most 200 steps; retriesTotal = true total of the repeats   // retries=[[step,repeats],...]: steps where the core had overshot and was brought back
    },
    capStart(o={}){ if(!frozen) throw E('BAD_ARG','capture needs the emulator stopped: call pause()'); cap={every:Math.max(1,Math.floor(o.every||2)),max:o.max||200,q:[],done:false,err:null,res:null,on:true}; return {every:cap.every}; },
    capArm(o={}){ if(!frozen) throw E('BAD_ARG','capture needs the emulator stopped: call pause()'); cap={every:2,max:o.max||200,q:[],done:false,err:null,res:null,on:false,armed:true,seq:0,clip:null}; return {armed:true}; },   // API 15: prepares the capture (daemon only): the runScript «video start/stop» commands turn it on
    async capClipStop(){ if(!cap||!cap.on||!cap.clip) throw E('BAD_ARG','no active video'); await capShot(); cap.q.push({ctl:'stop',id:cap.clip.id}); cap.on=false; cap.clip=null; return true; },
    capRun(kind,arg){ if(!cap) throw E('BAD_ARG','capStart missing'); const f=kind==='script'?()=>api.runScript(arg):kind==='loop'?()=>api.runLoop(arg.code,arg.opts||{}):kind==='frames'?()=>api.runFrames(arg):null; if(!f) throw E('BAD_ARG','capRun: kind = script | loop | frames');
      cap.done=false; cap.err=null; cap.res=null; cap.p=(async()=>{ await capShot(); try{ cap.res=await f(); }catch(e){ cap.err={code:e.code||'ERROR',message:String(e.message||e),outputs:e.outputs,log:e.log}; } cap.done=true; })(); return {started:true}; },
    capTake(n=50){ if(!cap) throw E('BAD_ARG','capStart missing'); const fr=cap.q.splice(0,n); return {frames:fr,done:cap.done&&cap.q.length===0,error:cap.err,result:cap.res,queued:cap.q.length}; },
    capStop(){ cap=null; return true; },
    recordStart(){ if(recd) throw E('BAD_ARG','recording already active'); recd={c0:cyc(),ev:[]}; return {cycles:recd.c0}; },
    recordStop(o={}){ if(!recd) throw E('BAD_ARG','no active recording'); const r={startCycles:recd.c0,frames:Math.round((cyc()-recd.c0)/FR),events:recd.ev}; recd=null; if(o.format==='text') return recToText(r); return r; },
    async replay(rec,o={}){             // replays the recorded calls at the same RELATIVE frames: start from the same state (loadState or reset). With the emulator stopped it is exact
      const evs=Array.isArray(rec)?rec:rec.events, c0=cyc(); replaying=true;
      try{ for(const e of evs){ const gap=e.f-Math.round((cyc()-c0)/FR); if(gap>0) await api.runFrames(gap); await api[e.m](...e.a); } const tail=(rec.frames||0)-Math.round((cyc()-c0)/FR); if(o.toEnd&&tail>0) await api.runFrames(tail); }
      finally{ replaying=false; } return {events:evs.length,frames:Math.round((cyc()-c0)/FR)};
    },
    scriptCheck(text){ const r=scriptParse(text); return {events:r.items.length,warnings:r.warnings}; },     // validation only (errors with line number)
    async runScript(text,o={}){         // runs an input script; see scripting.md. o={noWait}. Returns {events,frames,warnings,outputs?,log?}; on error the exception carries .outputs/.log
      const {items,warnings}=scriptParse(text); await bootWait(o); const w=W(), startCyc=cyc(); let c0=startCyc, ran=0;
      const outputs=[], log=[]; let myClip=null, myRec=false;
      const advance=async f=>{ const need=Math.round((c0+f*FR-cyc())/FR); if(need>0) await waitFrames(need); };
      const recEv=(m,a)=>{ if(recd&&!replaying) recd.ev.push({f:Math.round((cyc()-recd.c0)/FR),m,a}); };
      const vStop=async()=>{ await api.capClipStop(); myClip=null; };
      const rStop=()=>{ const nm=recd.name||('rec'+(outputs.length+1)+'.txt'); const r=api.recordStop({format:'text'}); myRec=false; outputs.push({type:'rec',name:nm,text:r.text,frames:r.frames,events:r.events,notExported:r.notExported}); };
      const memOk=(e)=>{ const a=addr(e.addr), m=e.mask===undefined?0xff:e.mask, v=W().wasm_peek(a); return {a,v,m,ok:((v&m)===(e.value&m))!==!!e.not}; };
      const ex=async e=>{ try{ switch(e.cmd){
        case 'poke': { const a=addr(e.addr); api.poke(a,e.vals,{ram:e.ram}); recEv('poke',[a,e.vals,{ram:e.ram}]); break; }
        case 'assert': { if(e.what==='mem'){ const r=memOk(e); if(!r.ok) throw E('ASSERT','assert failed: mem[$'+hex(r.a)+']=$'+hex(r.v,2)+', expected '+(e.not?'!=':'==')+' $'+hex(e.value&r.m,2)+(r.m!==0xff?' (mask $'+hex(r.m,2)+')':'')); }
          else if(e.what==='text'){ if(api.findText(e.text,e.textOpts||{})===null) throw E('ASSERT','assert failed: text (screen code) not found: '+JSON.stringify(e.text)+(Object.keys(e.textOpts||{}).length?' '+JSON.stringify(e.textOpts):'')); }
          else if(!api.screenText().toUpperCase().includes(e.text.toUpperCase())) throw E('ASSERT','assert failed: text not on the screen: '+JSON.stringify(e.text)); break; }
        case 'saveState': await api.saveState(e.name); break;
        case 'loadState': await api.loadState(e.name); break;
        case 'screenshot': outputs.push({type:'screenshot',name:e.file,mime:'image/png',line:e.line,data:api.screenshot().split(',')[1]}); break;
        case 'regress': if(e.op==='save'){ api.regressSave(e.name); break; }
          { const r=await api.regressCheck(e.name,{tolerance:e.tolerance||0,ignore:e.ignore.length?e.ignore:undefined}); log.push({line:e.line,cmd:'regress check',name:e.name,pass:r.pass}); if(!r.pass) throw E('REGRESS','regress check '+e.name+' failed: '+r.reasons.join('; ')); } break;
        case 'call': { const r=await api.call(e.addr,e.regs,{timeoutFrames:e.timeout,noWait:e.noWait}); log.push({line:e.line,cmd:'call',addr:'$'+hex(addr(e.addr)),result:r}); break; }
        case 'video': if(e.op==='start'){
            if(!cap||!cap.armed) throw E('NO_RECORDER','video start needs the c64d daemon with ffmpeg (c64 script FILE); it is not available calling runScript directly');
            if(!frozen) throw E('BAD_ARG','video start: the emulator must be stopped (pause()): capture is deterministic only in emulated time');
            if(cap.on) throw E('BAD_ARG','video already active: video stop needed first');
            const every=e.every||2, id=++cap.seq; let nm=e.name||('clip'+id); if(!/\.mp4$/i.test(nm)) nm+='.mp4';
            cap.every=every; cap.clip={id,keep:e.keep}; cap.q.push({ctl:'start',id,name:nm,every,scale:e.scale||3,crf:e.crf===undefined?20:e.crf,fps:Math.max(1,Math.round(50/every))}); cap.on=true; myClip=e.keep?null:id; await capShot();
          } else { if(!cap||!cap.on) throw E('BAD_ARG','video stop: no active video'); await vStop(); } break;
        case 'rec': if(e.op==='start'){ api.recordStart(); recd.name=e.name?(/\.[A-Za-z0-9]+$/.test(e.name)?e.name:e.name+'.txt'):null; recd.keep=e.keep; myRec=!e.keep; }
          else { if(!recd) throw E('BAD_ARG','rec stop: no active recording'); rStop(); } break;
        } }catch(err){ if(!/^script line /.test(String(err.message))) err.message='script line '+e.line+': '+err.message; throw err; } };
      let seg=[]; const flush=async()=>{       // runs the segment events in time order; joystick release actions are separate events
        const acts=[]; for(const e of seg){ acts.push({t:e.f,e,p:0}); if(e.kind==='joy') acts.push({t:e.f+e.hold,e,p:1}); if(e.kind==='key') acts.push({t:e.f+e.hold+MIN_REL,e,p:2}); }   // p=2: wait only, to let the key release complete
        acts.sort((x,y)=>x.t-y.t||(x.p===0)-(y.p===0)||y.p-x.p);   // at equal time first the releases (p=1), then the presses (p=0)
        for(const a of acts){ await advance(a.t); const e=a.e;
          if(e.kind==='key'&&a.p===0){ e.keys.forEach(k=>w.wasm_schedule_key(KM[k][0],KM[k][1],1,0)); e.keys.forEach(k=>w.wasm_schedule_key(KM[k][0],KM[k][1],0,e.hold)); recEv('type',[e.keys,{frames:e.hold}]); }
          else if(e.kind==='joy'){ for(const j of e.joys){ w.action('j'+j.port+j.dir+(a.p?0:1)); if(!a.p) recEv('joy',[j.port,{[j.dir]:true},e.hold]); } }
          else if(e.kind==='text'&&a.p===0){ recEv('sendText',[e.text,{framesPerKey:e.framesPerKey}]); await api.sendText(e.text,{noWait:true,framesPerKey:e.framesPerKey}); }
          else if(e.kind==='cmd'&&a.p===0) await ex(e);
          if(a.p===0) ran++; }
        seg=[]; };
      try{
        for(const it of items){
          if(it.kind==='cmd'&&it.f!==undefined){ seg.push(it); continue; }
          if(it.kind!=='wait'&&it.kind!=='cmd'){ seg.push(it); continue; }
          await flush();
          if(it.kind==='cmd'){ await ex(it); c0=cyc(); continue; }
          if(it.frames!==undefined) await waitFrames(it.frames);
          else { const c=it.stext!==undefined?(it.stextOpts?{text:it.stext,textOpts:it.stextOpts}:{text:it.stext}):it.screen!==undefined?{screenText:it.screen}:it.mem?{addr:it.mem.addr,value:it.mem.value,mask:it.mem.mask,not:it.mem.not}:{pc:it.pc};
            try{ await api.runUntil(c,{timeoutFrames:it.timeout}); }catch(e){ if(e.code==='TIMEOUT') throw E('TIMEOUT','script line '+it.line+': '+e.message); throw e; } }
          c0=cyc();
        }
        await flush();
      }catch(err){ err.outputs=outputs; err.log=log; throw err; }
      finally{   // automatic stop (default): videos and recordings started by this script without «keep» are closed here, also on error
        try{ if(myClip!==null&&cap&&cap.on&&cap.clip&&cap.clip.id===myClip) await vStop(); }catch(_){}
        try{ if(myRec&&recd) rStop(); }catch(_){}
      }
      const res={events:items.length,frames:Math.round((cyc()-startCyc)/FR),warnings};
      if(outputs.length) res.outputs=outputs; if(log.length) res.log=log; if(cap&&cap.on&&cap.clip) res.videoOpen=true; if(recd) res.recOpen=true;
      return res;
    },
    async sendJoy(script,o={}){         // "R10 UF8 W5 L3": directions U D L R + F (fire) held N frames; Wn = wait; port o.port (default the chosen one)
      const port=o.port||st.port; let n=0;
      for(const tok of String(script).trim().split(/\s+/).filter(Boolean)){ const m=/^([UDLRF]+)(\d*)$/i.exec(tok), wm=/^W(\d+)$/i.exec(tok);
        if(wm){ await api.runFrames(+wm[1]); n+=+wm[1]; continue; } if(!m) throw E('BAD_ARG','unknown joystick token: '+tok);
        const f=m[2]===''?4:+m[2], S={}; for(const c of m[1].toUpperCase()) S[{U:'up',D:'down',L:'left',R:'right',F:'fire'}[c]]=true;
        await api.joy(port,S,f); n+=f; }
      return {frames:n};
    },
    storeSet(k,v){ const s=JSON.stringify(v); if(lsOk()){ localStorage.setItem(LSP+k,s); } else memStore[k]=s; return true; },    // JSON key/value in the browser: survives page reloads; across different builds (different file names) only if the browser shares localStorage for file:// (Chromium yes; Firefox/Safari not verified)
    storeGet(k,def=null){ let s=lsOk()?localStorage.getItem(LSP+k):(k in memStore?memStore[k]:null); return s===null?def:JSON.parse(s); },
    storeDel(k){ if(lsOk()) localStorage.removeItem(LSP+k); delete memStore[k]; return true; },
    storeKeys(){ if(!lsOk()) return Object.keys(memStore); const o=[]; for(let i=0;i<localStorage.length;i++){ const k=localStorage.key(i); if(k.startsWith(LSP)) o.push(k.slice(LSP.length)); } return o; },
    storeExport(){ const o={}; for(const k of api.storeKeys()) o[k]=api.storeGet(k); return o; },
    storeImport(obj){ let n=0; for(const k in obj){ api.storeSet(k,obj[k]); n++; } return n; },
    /* ---- API 10: regression (recorded state vs new state) ---- */
    regressSave(name='default',o={}){   // baseline = component hashes + RAM (RAM view, default $0000-$FFFF; o.ram=[[a,b],..]) + screen (PNG) + cycles. Returns the JSON bundle (can be saved to a file) and keeps it in memory under 'name'
      const ranges=(o.ram||[[0,0xffff]]).map(parseRange), h=api.stateHash(o);
      const b={version:1,name,cycles:cyc(),hash:h,ram:ranges.map(([a,z])=>({from:a,to:z,data:u8b64(mem64(a,z,true))})),screen:o.screen===false?null:(()=>{ const cv=W().document.querySelector('canvas'); return {png:cv.toDataURL('image/png'),w:cv.width,h:cv.height}; })()};
      baselines[name]=b; return b;
    },
    async regressCheck(base,o={}){      // base = name, bundle or JSON string. o={ignore:[[a,b]|'a-b'|a], tolerance:0, only, exclude, ram:true, screen:true, strict:false, includeCpu:false, image:false, maxGroups:50}. Returns {pass,reasons,hash,ram,screen}
      let b=base; if(typeof b==='string'){ if(baselines[b]) b=baselines[b]; else { try{ b=JSON.parse(b); }catch(e){ throw E('NO_STATE','unknown baseline: '+String(base).slice(0,40)); } } }
      if(!b||b.version!==1) throw E('BAD_ARG','invalid baseline');
      const ign=(o.ignore||[]).map(parseRange), isIgn=a=>ign.some(r=>a>=r[0]&&a<=r[1]), reasons=[], res={pass:true,reasons};
      // 1) per-component hash
      const cur=api.stateHash({only:o.only,exclude:o.exclude}), diffc=[]; for(const k in cur.components) if(b.hash.components[k]!==undefined&&b.hash.components[k]!==cur.components[k]) diffc.push(k);
      // the CPU hash depends on the debugger history (instruction log): without o.includeCpu it is not compared
      const cpuIdx=diffc.indexOf('CPU'); let cpuDiff=false; if(cpuIdx>=0&&!o.includeCpu){ diffc.splice(cpuIdx,1); cpuDiff=true; }
      res.hash={same:diffc.length===0,differing:diffc,cpuIgnored:cpuDiff,baseline:b.hash.hash,current:cur.hash};
      // 2) RAM
      if(o.ram!==false){ const groups=[]; let total=0, ignored=0;
        for(const r of b.ram){ const A=b64u8(r.data), B=mem64(r.from,r.to,true); let g=null;
          for(let i=0;i<A.length;i++){ if(A[i]===B[i]) continue; const a=r.from+i; if(isIgn(a)){ ignored++; continue; } total++;
            if(g&&a-g.to<=4){ g.to=a; g.count++; } else { g={from:a,to:a,count:1,first:{addr:a,baseline:A[i],current:B[i]}}; if(groups.length<(o.maxGroups||50)) groups.push(g); else g=null; } } }
        res.ram={same:total===0,count:total,ignored,groups:groups.map(g=>({from:g.from,to:g.to,count:g.count,first:g.first}))}; if(total) reasons.push('RAM: '+total+' byte diversi in '+groups.length+(groups.length>=(o.maxGroups||50)?'+':'')+' intervalli'); }
      // 3) screen
      if(o.screen!==false&&b.screen){ const A=await pngPixels(b.screen.png), B=grab(); if(A.w!==B.w||A.h!==B.h) throw E('BAD_ARG','screen size differs from the baseline'); const dd=o.image?new Uint8ClampedArray(A.d.length):null, d=diffPix(A,B,o.tolerance||0,dd);
        res.screen=Object.assign({same:d.diffPixels===0,width:A.w,height:A.h},d); if(dd){ const c=document.createElement('canvas'); c.width=A.w; c.height=A.h; c.getContext('2d').putImageData(new ImageData(dd,A.w,A.h),0,0); res.screen.image=c.toDataURL('image/png'); }
        if(d.diffPixels) reasons.push('screen: '+d.diffPixels+' pixel diversi'); }
      if(o.strict&&diffc.length) reasons.push('hash diversi: '+diffc.join(', '));
      res.cycles={baseline:b.cycles,current:cyc()}; res.pass=reasons.length===0; return res;
    },
    async grabBrowserVideoAndAudio(o={}){   // API 16: records video (canvas + optional control panel) AND browser audio, in real time, in a separate recorder (MediaRecorder): no synchronization with the emulator, which is not touched.
      // o={action:'start'|'stop'|'status'} or o={seconds:N} (starts, waits N wall-clock seconds, stops). Options: keyboard|joy1|joy2: 'none'(default)|'below'|'overlay' each; scale:1-4 (default 2), fps:50, bitrate:4000000, audio:true, mime
      const act=o.action||(o.seconds!==undefined?'run':'start');
      if(act==='status') return gbr?{recording:true,seconds:(performance.now()-gbr.t0)/1000,controls:gbr.controls}:{recording:false};
      if(act==='stop'){ if(!gbr) throw E('BAD_ARG','no active grabBrowserVideoAndAudio recording'); return await grabStop(); }
      if(gbr) throw E('BAD_ARG','recording already active: use {action:"stop"}');
      const w=W(), cv0=w.document.querySelector('canvas'); if(typeof MediaRecorder==='undefined'||!cv0.captureStream) throw E('UNSUPPORTED','MediaRecorder/captureStream not available');
      const sc=o.scale===undefined?2:chk('scale',o.scale,1); if(sc>4) throw E('BAD_ARG','scale: intero 1-4');
      const pos={}; for(const k of ['keyboard','joy1','joy2']){ const v=o[k]===undefined?'none':o[k]; if(!['none','below','overlay'].includes(v)) throw E('BAD_ARG',k+': none | below | overlay'); pos[k]=v; }
      const W0=cv0.width*sc, vh=cv0.height*sc, anyJ=pos.joy1==='below'||pos.joy2==='below', jh=anyJ?Math.round(W0*.16):0, kh=pos.keyboard==='below'?Math.round(W0*.27):0, exh=jh+kh, controls=pos;
      const cx=document.createElement('canvas'); cx.width=W0; cx.height=vh+exh;
      const want=o.audio!==false, mimes=want?['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm']:['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'];
      const mime=o.mime||mimes.find(t=>MediaRecorder.isTypeSupported(t)); if(!mime) throw E('UNSUPPORTED','no supported format');
      const g=gbr={t0:performance.now(),cv0,cx,ctx:cx.getContext('2d'),w:W0,sc,controls,pos,ex:{jh,kh},input:{keys:new Set(),joy:{1:{},2:{}}},on:true,peak:0,warn:[],ch:[]};
      grabHook(g);
      const drawLoop=()=>{ if(!g.on) return; grabDraw(g); requestAnimationFrame(drawLoop); }; drawLoop();
      const stream=cx.captureStream(o.fps||50); g.hasAudio=false;
      if(want){ try{ const ac=w.eval('typeof audioContext!=="undefined"?audioContext:null'), gn=w.eval('typeof gainNode!=="undefined"?gainNode:null');
          if(!ac||!gn) g.warn.push('audio not connected in the page (no gainNode): video without audio'); else { if(ac.state!=='running') await ac.resume().catch(()=>{});
            const dest=ac.createMediaStreamDestination(), an=ac.createAnalyser(), mg=ac.createGain(); mg.gain.value=o.audioGain===undefined?1:+o.audioGain; an.fftSize=1024; gn.connect(mg); mg.connect(dest); mg.connect(an); g.aud={ac,gn,mg,dest,an};   // API 18: audioGain = gain applied only to the recording (default 1), it does not change the page audio
            dest.stream.getAudioTracks().forEach(t=>stream.addTrack(t)); g.hasAudio=true; const buf=new Float32Array(an.fftSize);
            g.pk=setInterval(()=>{ an.getFloatTimeDomainData(buf); for(const v of buf){ const x=Math.abs(v); if(x>g.peak) g.peak=x; } },100); if(ac.state!=='running') g.warn.push('AudioContext not running ('+ac.state+')'); } }catch(e){ g.warn.push('audio: '+e.message); } }
      if(frozen) g.warn.push('emulator stopped: the video shows a still image (this recording does not advance the emulator)');
      g.rec=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:o.bitrate||4000000,audioBitsPerSecond:128000}); g.mime=mime;
      g.rec.ondataavailable=e=>{ if(e.data.size) g.ch.push(e.data); }; g.done=new Promise(r=>{ g.rec.onstop=r; }); g.rec.start(250);
      if(act==='run'){ await sleep(Math.round(o.seconds*1000)); return await grabStop(); }
      return {recording:true,mime,width:cx.width,height:cx.height,audio:g.hasAudio,controls,warnings:g.warn};
    },
    async recordVideo(o={}){            // canvas video (MediaRecorder, real time): {frames:100 | seconds:2, fps:50, mime, bitrate, scale:1 (integer 1-4, 4 = 1536x1080: sharp-pixel scaling)}. If the emulator is stopped it advances 'frames' frames; returns {data(base64),mime,bytes,frames,width,height}
      const cv0=W().document.querySelector('canvas'); if(typeof MediaRecorder==='undefined'||!cv0.captureStream) throw E('UNSUPPORTED','MediaRecorder/captureStream not available in this browser');
      const frames=o.frames||Math.round((o.seconds||2)*50), mime=o.mime||['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
      if(!mime) throw E('UNSUPPORTED','no supported video format'); const sc=o.scale===undefined?1:chk('scale',o.scale,1); if(sc>4) throw E('BAD_ARG','scale: intero 1-4 (4 = 1536x1080, circa full HD)');
      let cv=cv0, stopDraw=()=>{};
      if(sc>1){ const d=document.createElement('canvas'); d.width=cv0.width*sc; d.height=cv0.height*sc; const g=d.getContext('2d'); g.imageSmoothingEnabled=false; let on=true;
        const draw=()=>{ if(!on) return; g.drawImage(cv0,0,0,d.width,d.height); requestAnimationFrame(draw); }; draw(); stopDraw=()=>{ on=false; }; cv=d; }   // scaled helper canvas, redrawn at every browser frame
      const ch=[], rec=new MediaRecorder(cv.captureStream(o.fps||50),{mimeType:mime,videoBitsPerSecond:o.bitrate||2500000});
      rec.ondataavailable=e=>{ if(e.data.size) ch.push(e.data); }; const done=new Promise(r=>{ rec.onstop=r; });
      rec.start(); await waitFrames(frames); await sleep(60); rec.stop(); await done; stopDraw();
      const buf=new Uint8Array(await new Blob(ch,{type:mime}).arrayBuffer()); return {data:u8ToB64(buf),mime,bytes:buf.length,frames,width:cv.width,height:cv.height};
    },
    regressList(){ const o={}; for(const k in baselines) o[k]={cycles:baselines[k].cycles,ram:baselines[k].ram.map(r=>[r.from,r.to]),screen:!!baselines[k].screen}; return o; },
    methods(){ return METHODS; },
    /* ---- misc ---- */
    eval(codeStr){ return W().eval(codeStr); },     // arbitrary JS in the emulator context
    async waitFor(text,timeout=15000){ const t0=Date.now(); while(Date.now()-t0<timeout){ if(api.screenText().toUpperCase().includes(String(text).toUpperCase())) return true; await sleep(150); } return false; },
    sleep
  };
  window.c64=api;

  /* ---- hooking into the page (the page contains nothing of this API) ---- */
  // autoload (d64/prg): the page starts the script with emu(); it is wrapped to know when the sequence has finished (__autoDone)
  const emu0=window.emu;
  window.emu=function(code){ if(typeof code==='string'&&code.indexOf('wasm_auto_type')>=0){ try{ frame.contentWindow.__autoDone=false; }catch(e){} code+=';window.__autoDone=true;'; } return emu0.call(this,code); };
  // with the emulator frozen by the API the pause/resume button and the core status messages must reflect the freeze
  const bp=$('bPause'), bp0=bp.onclick; bp.onclick=()=>{ if(frozen) window.c64.resume(); else bp0(); };
  window.addEventListener('message',ev=>{ if(frame&&ev.source===frame.contentWindow&&ev.data&&ev.data.msg==='render_run_state'&&frozen) setPausedUi(true); });
  // input recording (API 7): top-level input calls are recorded with their relative frame
  ['keyDown','keyUp','joy','sendText','type','sendJoy','runScript','fire','joyPulse','poke','pokeRange'].forEach(m=>{
    const orig=api[m]; api[m]=function(...a){
      if(recd&&!inRec&&!replaying) recd.ev.push({f:Math.round((cyc()-recd.c0)/FR),m,a:JSON.parse(JSON.stringify(a,(k,v)=>v instanceof Uint8Array?Array.from(v):v))});
      inRec++; let r; try{ r=orig.apply(api,a); }catch(e){ inRec--; throw e; }
      if(r&&typeof r.then==='function') return r.then(v=>{ inRec--; return v; },e=>{ inRec--; throw e; }); inRec--; return r; };
  });

  // postMessage channel (for a container page / bridge): {c64:'call', id, method, args:[...]}
  window.addEventListener('message',async ev=>{
    const d=ev.data; if(!d||d.c64!=='call'||!api[d.method]) return;
    let out; try{ out={c64:'result',id:d.id,ok:true,value:await api[d.method](...(d.args||[]))}; }catch(e){ out={c64:'result',id:d.id,ok:false,error:String(e.message||e),code:e.code||'ERROR',method:d.method}; }
    try{ ev.source.postMessage(out,'*'); }catch(_){}
  });
})();


