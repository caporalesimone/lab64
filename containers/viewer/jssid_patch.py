#!/usr/bin/env python3
"""Lab64 additions to jsSID 0.9.1 (14/11), applied while the viewer image is built (WTFPL allows it). Copyright (c) 2026 - Simone Caporale

jsSID mixes the three voices inside its SID() function: to show the waveform of every voice and to mute voices or bypass the
SID filter, a few hooks are added (exact text replacements on the pinned commit of sources.conf: the build stops if they do not
match, e.g. after an update of jsSID):
  getscope()        {v: [Float32Array x3] voice outputs, m: Float32Array mix, pos}: ring buffers of the last 8192 samples
  setmute(ch, on)   voice ch (0..2) left out of the mix        setfilter(on)   false = the voices bypass the SID filter
  getmem()          the 64 KB memory of the emulated C64 (SID registers at $D400)
  getctx()          the AudioContext          setoutput(node)  the audio goes to node instead of the destination (filters, analysers)
  getcpu()          6510 cycles used by the last call of the play routine (jsSID counts instruction cycles: an estimate, not VICE)
  getenv()          {env: envelope counters 0..255, st: envelope state bits (0x80 attack, 0x40 decay/sustain, 0x01 gate)} per voice
  setoverride(o)    force parts of the SID filter registers instead of the tune's values, only while the sound is computed (the
                    tune's own values stay in memory): {fc 0..2047, res 0..15, lp, bp, hp, r1, r2, r3, v3off 0/1, vol 0..15},
                    -1 or missing = follow the tune
  geteff()          [$D415, $D416, $D417, $D418] as really used for the sound (after the override)
  setvideo(m)       'auto' | 'pal' | 'ntsc': video standard (clock, VBI rate, default CIA timer); restarts the subtune
  getvideo()        {sel, std: 'pal'|'ntsc' in use, hdr: 'unknown'|'pal'|'ntsc'|'both' (PSID flags), clk, fr}
  render(buf, n)    n samples into buf (what the AudioWorklet calls)     getscp()  ring position of the scope buffers
  scshare(sab)      the scope rings live in a SharedArrayBuffer (4 * 8192 floats)

6581 DC offsets (15/11, after reSID, which stays the reference). reSID: voice = (wave12 - wave_zero) * env + voice_DC, and
mixer_DC is added to the mix before the volume multiplication. 6581: wave_zero = 0x380, voice_DC = 0x800*0xff, mixer_DC =
(-0xfff*0xff/18) >> 7 (voices are shifted right by 7 before the mixer); 8580: wave_zero = 0x800, voice_DC = 0, mixer_DC = 0.
Mapping onto the jsSID scale: wfout is the 12-bit wave << 4 (0..0xFFFF, centred at 0x8000) and the envelope is envcnt/256, so a
jsSID unit is 1/16 of a reSID voice unit before the shift, and 8 jsSID units are one reSID unit after it:
  wave_zero 0x380            -> WZ6  = 0x380 << 4        = 0x3800   (8580: 0x8000, the old jsSID centre)
  voice_DC  0x800*0xff       -> DC6  = 0x800*0xff / 16   = 0x7F80   (8580: 0)
  mixer_DC  -454 (C integer arithmetic) -> MDC6 = -454 * 8 = -3632  (8580: 0)
SCALE is unchanged: the proportions of reSID are kept. Effect: on the 6581 the volume nibble of $D418 moves the output level
even with every voice silent (4-bit digis are heard); on the 8580 it does not. A muted voice keeps its constant DC (muting
must not click); voice 3 off (not filtered) leaves the mix with its DC, as in reSID; the filter sees the DC of the voices routed
through it (only a low-pass lets it pass; jsSID's filter returns its low-pass and high-pass outputs inverted, so the DC
enters it with the opposite sign and comes out as +DC, as in reSID). The per-voice hook vo[] (scope) stays the AC part, (wfout - 0x8000) * env: no
wave_zero offset and no DC. The final mix still contains the DC: the external filter (reSID extfilt) removes it.

Video standard (15/11). jsSID had PAL only (985248 Hz, 50 Hz VBI). The PSID v2+ flags (big endian word at $76-$77, so byte $77
bits 2-3: 01 PAL, 10 NTSC, 11 both, 00 unknown; ignored for a v1 header) set it in 'auto' mode: NTSC only for 10, PAL otherwise.
PAL: clock 985248 Hz, 19656 cycles per frame, default CIA 1 timer A $4025; NTSC: 1022727 Hz, 17095 cycles per frame, $4295 (the KERNAL's 60 Hz
values).
They are used when a tune is flagged CIA timing but its init routine leaves the timer high byte at 0 (jsSID put $4024 in both
cases: one cycle short on PAL, 5% fast on NTSC). Everything that depends on the clock is recomputed at every (re)start: cycles per
sample (frequency registers, ADSR periods) and cycles per play call.

Tempo (1.9, measured against reSIDfp / sidplayfp). jsSID called play exactly 50 / 60 times a second (smpr / 50), dropped the fraction of
a sample at every frame (fcnt = fspd) and used a CIA latch without the +1 (the timer counts latch + 1 cycles): -137 ms per minute against
the real C64 on PAL VBI tunes, +198 ms on NTSC VBI. Now: a VBI frame is FRC = 19656 (PAL) / 17095 (NTSC) cycles, a CIA frame is latch + 1
cycles, both divided by the cycles per sample (ckr) without rounding, and the frame counter keeps the fraction (fcnt += fspd). Play
calls in 180 s (44.1 and 48 kHz): 9023 PAL VBI, 10769 NTSC VBI, 9000 PAL CIA (latch 19705). getvideo() also gives frc (cycles per frame).
icyc = 6510 cycles of the init routine (an estimate, like getcpu); icia = the tune is CIA timed.

External output filter (15/11, reSID extfilt): on the final mix (after the $D418 volume, before the page volume), at the sample
rate fs of the AudioContext, a one-pole low-pass at 16 kHz and a one-pole high-pass at 16 Hz, as in reSID: lp = low-pass(x),
hp = low-pass-16Hz(lp), out = lp - hp. The 16 kHz pole is a bilinear transform with pre-warping (K = tan(pi fc / fs), -3 dB
exactly at 16 kHz even at 44.1 kHz; fc is limited to 0.45 fs): lp = K/(1+K) * (x + x1) + (1-K)/(1+K) * lp. The 16 Hz pole
is hp += (1 - exp(-2 pi 16 / fs)) * (lp - hp). After every (re)start the state is set to the steady state of the first
sample, so the DC level does not click. The output of this filter is also what the master scope
shows. The final clamp to [-1, 1] is hard on purpose: reSID clamps, it does not soft-clip.
AudioWorklet (15/11). jsSID computes the sound in a ScriptProcessorNode, on the main thread with all the drawing of SID Studio
(crackles under load). With a second argument the script also writes jssid-worklet.js: the same patched core (the strict-mode
module of an AudioWorklet: the three undeclared globals of jsSID are declared) without AudioContext, ScriptProcessor and XHR (the
page fetches the .sid and posts its bytes: loadinit(buffer, subtune); playcont / pause only set a flag, render() fills the
128-sample blocks), followed by jssid_worklet_tail.js (the AudioWorkletProcessor 'jssid': commands from the page, telemetry
about 60 times a second). The page side is www/sidengine.js: a proxy object with the same public API as jsSID. jsSID.js itself
stays the fallback engine (no secure context, no AudioWorklet).
Analyzer hooks (1.9, for the silent jsSID that follows the rendered WAV, see jssid_worklet_tail.js and www/sidengine.js):
getstate() / setstate(o) copy the whole emulation (64 KB of memory, the CPU, the three voices, the envelopes, the filter, the timers,
the play counters; about 66 KB), bit-exact: the samples after a restore are the same as after the original run, in any player of the
same tune. ff(n) computes n samples without output (checkpoints and seeks). setks(p, n) scales the CPU clock of the emulation (PAL p,
NTSC n; 1 = the C64's own clock, the default: the audible engine never uses it; the analyzer uses it to run on the time base of
sidplayfp's WAV, which is stretched by a fixed factor per video standard) and restarts the subtune. getinit() = {cyc, cia}: the
cycles the init routine used (counted, not estimated; the analyzer derives sidplayfp's first play call from it) and whether the
tune is CIA timed. The patch has 25 replacements (REP 19 + WK 6; 24 in 1.8: the hooks live in the API replacement and the init one).
Usage: python3 jssid_patch.py jsSID.js [jssid-worklet.js]    (jsSID.js rewritten in place; the second file is written)."""
import os
import sys

p = sys.argv[1]
s = open(p, encoding="latin-1").read()
# the complete emulation state, for getstate() / setstate() (checkpoints of the SID Studio analyzer): arrays (copied element by element: the
# sound code holds references to them) and scalars of the closure; everything else is a constant, a setting or a temporary of one call.
# Verified bit-exact: a state taken after N samples and restored into any player (fresh or dirty) of the same tune gives the same samples.
STATE_ARR = ['Ast', 'rcnt', 'envcnt', 'expcnt', 'pSR', 'pacc', 'pracc', 'sMSBrise', 'sMSB', 'nLFSR', 'prevwfout', 'pwv', 'plp', 'pbp', 'vo', 'eff', 'tmod']
STATE_SCA = ['PC', 'A', 'X', 'Y', 'SP', 'ST', 'CPUtime', 'fcnt', 'fspd', 'fin', 'pla', 'plf', 'ind', 'ldd', 'playtime', 'ended', 'efl', 'efh', 'efx', 'efi',
             'fcyc', 'pcyc', 'CLK', 'FR', 'FRC', 'ckr', 'CIAD', 'vntsc', 'hclk', 'subtune', 'ina', 'SIDm', 'mix', 'output', 'icyc', 'icia']
GETSET = ("this.getstate=function (){var o={M:M.slice()};" + "".join("o.%s=%s.slice();" % (n, n) for n in STATE_ARR) + "".join("o.%s=%s;" % (n, n) for n in STATE_SCA) + "return o;};"
          "this.setstate=function (o){M.set(o.M);" + "".join("for(var i=0;i<o.%s.length;i++)%s[i]=o.%s[i];" % (n, n, n) for n in STATE_ARR) +
          "".join("%s=o.%s;" % (n, n) for n in STATE_SCA) + "prd0=Math.max(ckr,9);Aprd[0]=prd0;Astp[0]=Math.ceil(prd0/9);};"
          "this.ff=function (n){for(var i=0;i<n;i++)play();};"                       # n samples without output (checkpoints, seeks)
          "this.setks=function (p,n){KSP=p;KSN=n;if(ldd)init(subtune);};"           # clock scale PAL / NTSC (1 = the C64's own clock), restarts the subtune
          "this.getinit=function (){return {cyc:icyc,cia:icia};};")                 # cycles of the init routine, CIA timed or not

REP = [
    # state of the hooks, next to the other variables of jsSID
    ("var SIDamount=1,mix=0;",
     "var SIDamount=1,mix=0;var SCN=8192,scV=[new Float32Array(SCN),new Float32Array(SCN),new Float32Array(SCN)],scM=new Float32Array(SCN),"
     "scP=0,vo=[0,0,0,0,0,0,0,0,0],vmute=[0,0,0,0,0,0,0,0,0],nofilt=0,fcyc=0,pcyc=0;"
     "var WZ6=0x3800,DC6=0x7F80,MDC6=-3632;"             # 6581 DC offsets, see the docstring
     # external filter (reSID extfilt): low-pass 16 kHz, high-pass 16 Hz, one pole each, at the sample rate
     "var EFK=Math.tan(Math.PI*Math.min(16000,0.45*smpr)/smpr),EFB=EFK/(1+EFK),EFA=(1-EFK)/(1+EFK),EFHP=1-Math.exp(-2*Math.PI*16/smpr),efl=0,efh=0,efx=0,efi=1;"
     "function extf(x){if(efi){efl=efh=efx=x;efi=0;}efl=EFB*(x+efx)+EFA*efl;efx=x;efh+=EFHP*(efl-efh);return efl-efh;}"
     # video standard: hclk = clock flags of the header (0 unknown, 1 PAL, 2 NTSC, 3 both), vsel = the page's choice
     "var wrun=1;"                                        # 0 = render() writes nothing (the worklet build: paused)
     "var hclk=0,vsel='auto',vntsc=0,CIAD=0x4025,FRC=19656,icyc=0,icia=0,KSP=1,KSN=1;"
     "function applyvid(){vntsc=vsel=='ntsc'||(vsel!='pal'&&hclk==2)?1:0;CLK=vntsc?1022727:985248;FRC=vntsc?17095:19656;FR=CLK/FRC;CIAD=vntsc?0x4295:0x4025;"
     "ckr=CLK*(vntsc?KSN:KSP)/smpr;prd0=Math.max(ckr,9);Aprd[0]=prd0;Astp[0]=Math.ceil(prd0/9);}"),
    # cycles of the play routine, frame by frame; the frame counter keeps the fraction of a sample (fcnt += fspd, not fcnt = fspd)
    ("if(fcnt<=0){fcnt=fspd;fin=0;PC=pla;SP=0xFF;}", "if(fcnt<=0){fcnt+=fspd;fin=0;PC=pla;SP=0xFF;pcyc=fcyc;fcyc=0;}"),
    ("else CPUtime+=cyc;", "else {CPUtime+=cyc;fcyc+=cyc;}"),
    # voice output (before the filter routing): AC part for the scope, reSID voice (with wave_zero and DC) for the mix; muted
    # voices keep only their constant DC; filter bypass
    ("if(M[SIDaddr+0x17]&FSW[chn])flin+=(wfout-0x8000)*(envcnt[chn]/256);else if((chn%CHA)!=2||!(M[SIDaddr+0x18]&OFF3))output+=(wfout-0x8000)*(envcnt[chn]/256);",
     "vo[chn]=(wfout-0x8000)*(envcnt[chn]/256);vv=vmute[chn]?0:(wfout-WZ)*(envcnt[chn]/256);"
     "if((M[SIDaddr+0x17]&FSW[chn])&&!nofilt)flin+=vv-DCV;else if((chn%CHA)!=2||!(M[SIDaddr+0x18]&OFF3))output+=vv+DCV;"),
    # 6581 / 8580 constants of this call and the mixer DC before the volume multiplication
    ("function SID(num,SIDaddr){flin=0;output=0;",
     "function SID(num,SIDaddr){flin=0;output=0;var vv,m6=SIDm!=8580.0,WZ=m6?WZ6:0x8000,DCV=m6?DC6:0;"),
    ("return (output/SCALE)*(M[SIDaddr+0x18]&0xF);", "return ((output+(m6?MDC6:0))/SCALE)*(M[SIDaddr+0x18]&0xF);"),
    # external filter on the mix, one sample of every voice and of the filtered mix into the ring buffers, then the page volume,
    # the dither and the hard clamp to [-1, 1] (reSID clamps: no soft clipping, on purpose)
    ("return mix*volume*SIDamount_vol[SIDamount]+(Math.random()*bgnoi-bgnoi/2);",
     "mix=extf(mix);scV[0][scP]=vo[0]/0x8000;scV[1][scP]=vo[1]/0x8000;scV[2][scP]=vo[2]/0x8000;scM[scP]=mix;scP=(scP+1)%SCN;"
     "mix=mix*volume*SIDamount_vol[SIDamount]+(Math.random()*bgnoi-bgnoi/2);return mix>1?1:(mix<-1?-1:mix);"),
    # a (re)start sets the external filter to the steady state of its first sample
    ("function init(subt){if(ldd){ind=0;", "function init(subt){if(ldd){ind=0;efi=1;applyvid();"),
    # clock flags of the PSID header (v2 and later); the default CIA timer follows the video standard
    ("SIDamount=1+(SID_address[1]>0)+(SID_address[2]>0);ldd=1;",
     "SIDamount=1+(SID_address[1]>0)+(SID_address[2]>0);hclk=(fdat[5]>=2&&offs>=0x7C&&fdat.length>0x77)?(fdat[0x77]>>2)&3:0;ldd=1;"),
    # init: its cycles are counted (icyc); a VBI tune's frame is FRC cycles (19656 PAL, 17095 NTSC: 50.1245 / 59.8261 Hz, not 50 / 60), a
    # CIA tune's is latch + 1 cycles (the timer counts latch+1 cycles), both converted to samples without rounding
    ("for(var tout=100000;tout>=0;tout--){if(CPU())break;}if(tmod[subtune]||M[0xDC05]){if(!M[0xDC05]){M[0xDC04]=0x24;M[0xDC05]=0x40;}fspd=(M[0xDC04]+M[0xDC05]*256)/ckr;}else fspd=smpr/FR;",
     "icyc=0;for(var tout=100000;tout>=0;tout--){var rr=CPU();icyc+=cyc;if(rr)break;}"
     "if(tmod[subtune]||M[0xDC05]){if(!M[0xDC05]){M[0xDC04]=CIAD&255;M[0xDC05]=CIAD>>8;}fspd=(M[0xDC04]+M[0xDC05]*256+1)/ckr;icia=1;}else{fspd=FRC/ckr;icia=0;}"),
    # a write to the CIA timer registers during play changes the period of a CIA tune (same +1)
    ("&&tmod[subtune])fspd=(M[0xDC04]+M[0xDC05]*256)/ckr;", "&&tmod[subtune])fspd=(M[0xDC04]+M[0xDC05]*256+1)/ckr;"),
    # audio routing: through an output node chosen by the page (default: the destination, as in jsSID)
    ("var smpr=aCtx.sampleRate;", "var smpr=aCtx.sampleRate;var outN=aCtx.destination;"),
    ("scrNod.connect(aCtx.destination)", "scrNod.connect(outN)"),
    ("scrNod.disconnect(aCtx.destination)", "scrNod.disconnect(outN)"),
    # filter override: the registers are changed only around the sound computation of the first SID, then put back
    ("mix=SID(0,0xD400);", "var ovs=ovr();mix=SID(0,0xD400);M[0xD415]=ovs[0];M[0xD416]=ovs[1];M[0xD417]=ovs[2];M[0xD418]=ovs[3];"),
    ("var SIDamount=1,mix=0;", "var SIDamount=1,mix=0;var OV={},eff=[0,0,0,0];function ovr(){var s=[M[0xD415],M[0xD416],M[0xD417],M[0xD418]],a=s[0],b=s[1],c=s[2],d=s[3],"
     "B=function(v,bit,on){return on<0||on===undefined?v:(on?v|bit:v&~bit);};"
     "if(OV.fc>=0){a=(a&0xF8)|(OV.fc&7);b=OV.fc>>3;}if(OV.res>=0)c=(c&15)|(OV.res<<4);c=B(B(B(c,1,OV.r1),2,OV.r2),4,OV.r3);"
     "d=B(B(B(B(d,0x10,OV.lp),0x20,OV.bp),0x40,OV.hp),0x80,OV.v3off);if(OV.vol>=0)d=(d&0xF0)|OV.vol;"
     "M[0xD415]=a;M[0xD416]=b;M[0xD417]=c;M[0xD418]=d;eff[0]=a;eff[1]=b;eff[2]=c;eff[3]=d;return s;}"),
    # the API
    ("this.setvolume=function (vol){volume=vol;};",
     "this.setvolume=function (vol){volume=vol;};this.getscope=function (){return {v:scV,m:scM,pos:scP,size:SCN};};"
     "this.setmute=function (ch,on){vmute[ch]=on?1:0;};this.setfilter=function (on){nofilt=on?0:1;};this.getmem=function (){return M;};"
     "this.getctx=function (){return aCtx;};this.setoutput=function (n){outN=n;};"
     "this.getcpu=function (){return pcyc;};this.getenv=function (){return {env:envcnt,st:Ast};};"
     "this.setoverride=function (o){OV=o||{};};this.geteff=function (){return eff;};"
     "this.setvideo=function (m){vsel=(m=='pal'||m=='ntsc')?m:'auto';if(ldd)init(subtune);};"
     "this.getvideo=function (){return {sel:vsel,std:vntsc?'ntsc':'pal',hdr:['unknown','pal','ntsc','both'][hclk],clk:CLK,fr:FR,frc:FRC};};"
     "this.render=function (b,n){if(wrun)for(var i=0;i<n;i++)b[i]=play();};this.getscp=function (){return scP;};" + GETSET +
     "this.scshare=function (b){scV=[new Float32Array(b,0,SCN),new Float32Array(b,SCN*4,SCN),new Float32Array(b,SCN*8,SCN)];scM=new Float32Array(b,SCN*12,SCN);};"),
    # undeclared globals of jsSID (a leak in a page, a ReferenceError in a strict module)
    ("startcallback=null;endcallback=null,playtime=0,ended=0;", "startcallback=null,endcallback=null,playtime=0,ended=0;"),
    ("trsaw=new Array(4096);cCmbWF(trsaw,0.8,2.4,0.64);pusaw=new Array(4096);cCmbWF(pusaw,1.4,1.9,0.68);Pulsetrsaw=new Array(4096);",
     "var trsaw=new Array(4096);cCmbWF(trsaw,0.8,2.4,0.64);var pusaw=new Array(4096);cCmbWF(pusaw,1.4,1.9,0.68);var Pulsetrsaw=new Array(4096);"),
]
for a, b in REP:
    n = s.count(a)
    if n != 1:
        sys.exit("jssid_patch: '%s...' found %d times (expected 1): jsSID changed?" % (a[:40], n))
    s = s.replace(a, b)
open(p, "w", encoding="latin-1").write("// jsSID 0.9.1 by Hermit (WTFPL) + Lab64 hooks (containers/viewer/jssid_patch.py)\n" + s)
print("jssid_patch: %d hooks" % len(REP))

if len(sys.argv) > 2:
    # the worklet build: the patched core without the page side (exact replacements too: the build stops if one does not match)
    WK = [
        ("if(typeof AudioContext!=='undefined'){var aCtx=new AudioContext();}else {var aCtx=new webkitAudioContext();};"
         "var smpr=aCtx.sampleRate;var outN=aCtx.destination;", "var smpr=sampleRate;"),
        ("if(typeof aCtx.createJavaScriptNode==='function'){var scrNod=aCtx.createJavaScriptNode(bufln,0,1);}else {var scrNod=aCtx.createScriptProcessor(bufln,0,1);}"
         "scrNod.onaudioprocess=function (e){var oBuf=e.outputBuffer;var oDat=oBuf.getChannelData(0);for(var sample=0;sample<oBuf.length;sample++){oDat[sample]=play();}};", ""),
        # the page posts the bytes of the file: loadinit(ArrayBuffer, subtune)
        ("var req=new XMLHttpRequest();req.open('GET',sidurl,true);req.responseType='arraybuffer';req.onload=function (){var fdat=new Uint8Array(req.response);",
         "var req={response:sidurl,send:function (){req.onload();}};req.onload=function (){var fdat=new Uint8Array(req.response);"),
        ("this.playcont=function (){scrNod.connect(outN);};this.pause=function (){if(ldd&&ind)scrNod.disconnect(outN);};",
         "this.playcont=function (){wrun=1;};this.pause=function (){wrun=0;};"),
        ("this.getctx=function (){return aCtx;};this.setoutput=function (n){outN=n;};", ""),
        ("var wrun=1;", "var wrun=0;"),
    ]
    w = s
    for a, b in WK:
        n = w.count(a)
        if n != 1:
            sys.exit("jssid_patch (worklet): '%s...' found %d times (expected 1): jsSID changed?" % (a[:40], n))
        w = w.replace(a, b)
    for a in ("aCtx", "scrNod", "XMLHttpRequest", "outN"):
        if a in w:
            sys.exit("jssid_patch (worklet): '%s' is left in the worklet build" % a)
    tail = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "jssid_worklet_tail.js"), encoding="utf-8").read()
    open(sys.argv[2], "w", encoding="latin-1").write(
        "// jsSID 0.9.1 by Hermit (WTFPL) + Lab64 hooks, AudioWorklet build (containers/viewer/jssid_patch.py, jssid_worklet_tail.js)\n"
        + w + "\n" + tail)
    print("jssid_patch: worklet build %s (%d replacements)" % (sys.argv[2], len(WK)))
