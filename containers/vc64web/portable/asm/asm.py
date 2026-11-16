import re,sys,json
OPS={ # mnemonic: {mode: opcode}
'LDA':{'imm':0xA9,'zp':0xA5,'abs':0xAD,'absx':0xBD,'indy':0xB1},
'STA':{'zp':0x85,'abs':0x8D,'absx':0x9D,'absy':0x99,'indy':0x91},
'LDX':{'imm':0xA2,'abs':0xAE},'LDY':{'imm':0xA0},
'STX':{'zp':0x86,'abs':0x8E},'STY':{'zp':0x84},
'ORA':{'zp':0x05,'abs':0x0D,'absx':0x1D},'AND':{'imm':0x29},'EOR':{'imm':0x49},
'CMP':{'imm':0xC9,'abs':0xCD,'absx':0xDD},'CPX':{'imm':0xE0},'CPY':{'imm':0xC0,'zp':0xC4,'abs':0xCC},
'ADC':{'imm':0x69},'LSR':{'a':0x4A,'zp':0x46},'ASL':{'a':0x0A},'ROL':{'zp':0x26},
'INC':{'abs':0xEE,'zp':0xE6},'DEC':{'abs':0xCE,'zp':0xC6},'JSR':{'abs':0x20},
'JMP':{'abs':0x4C,'ind':0x6C},
'BEQ':{'rel':0xF0},'BNE':{'rel':0xD0},'BCC':{'rel':0x90},'BCS':{'rel':0xB0},'BPL':{'rel':0x10},
'TXA':{'imp':0x8A},'TAX':{'imp':0xAA},'TAY':{'imp':0xA8},'TYA':{'imp':0x98},'PHA':{'imp':0x48},'PLA':{'imp':0x68},
'CLC':{'imp':0x18},'SEC':{'imp':0x38},'DEX':{'imp':0xCA},'INX':{'imp':0xE8},'INY':{'imp':0xC8},'DEY':{'imp':0x88},
'SEI':{'imp':0x78},'CLI':{'imp':0x58},'RTS':{'imp':0x60},'NOP':{'imp':0xEA},
}
def val(e,sym):
    e=e.strip()
    m=re.fullmatch(r'([<>])(.+)',e)
    if m: v=val(m.group(2),sym); return (v&255) if m.group(1)=='<' else (v>>8)&255
    if '+' in e and not e.startswith('$'):
        a,b=e.split('+',1); return val(a,sym)+val(b,sym)
    if e.startswith('$'): return int(e[1:],16)
    if re.fullmatch(r'\d+',e): return int(e)
    if e in sym: return sym[e]
    raise KeyError(e)
def parse(op,mn,sym,final):
    if op is None or op=='': return 'imp',None
    if op=='A': return 'a',None
    if op.startswith('#'): return 'imm',val(op[1:],sym) if final else 0
    m=re.fullmatch(r'\((.+)\),Y',op)
    if m: return 'indy',val(m.group(1),sym) if final else 0
    m=re.fullmatch(r'\((.+)\)',op)
    if m: return 'ind',val(m.group(1),sym) if final else 0
    m=re.fullmatch(r'(.+),X',op)
    if m: return 'absx',val(m.group(1),sym) if final else 0
    m=re.fullmatch(r'(.+),Y',op)
    if m: return 'absy',val(m.group(1),sym) if final else 0
    if mn in('BEQ','BNE','BCC','BCS','BPL'): return 'rel',op
    try: v=val(op,sym)
    except KeyError:
        if final: raise
        return 'abs',0
    if v<256 and 'zp' in OPS[mn]: return 'zp',v
    return 'abs',v
def assemble(src,org,sym0):
    lines=[]
    for ln in src.split('\n'):
        ln=ln.split(';')[0].strip()
        if not ln: continue
        lines.append(ln)
    sym=dict(sym0)
    for final in (False,True):
        pc=org; out=[]; 
        for ln in lines:
            m=re.match(r'^([A-Za-z_]\w*):\s*(.*)$',ln)
            if m:
                sym[m.group(1)]=pc; ln=m.group(2)
                if not ln: continue
            if ln.startswith('.org'): continue
            p=ln.split(None,1); mn=p[0].upper(); op=p[1].strip() if len(p)>1 else None
            mode,v=parse(op,mn,sym,final)
            if mode not in OPS[mn]: raise Exception('mode %s not valid for %s (%s)'%(mode,mn,ln))
            oc=OPS[mn][mode]
            if mode=='imp' or mode=='a': out.append(oc); pc+=1
            elif mode in('imm','zp','indy'): out+= [oc,v&255]; pc+=2
            elif mode=='rel':
                if final:
                    t=val(v,sym); d=t-(pc+2)
                    if not -128<=d<=127: raise Exception('branch out of range: '+ln+' %d'%d)
                else: d=0
                out+=[oc,d&255]; pc+=2
            else: out+=[oc,v&255,(v>>8)&255]; pc+=3
    return out,sym
SYM=dict(TABLO=0xC400,TABHI=0xC450,LENT=0xC4A0,NEW=0xC500,DISP=0xC550,TRIED=0xC5A0,COL=0xC5F0,REVT=0xC5F4,
 RSTC=0xC5F8,LAST=0xC5F9,EVT=0xC5FA,JA=0xC5FB,JB=0xC5FC,TCNT=0xC5FD,TCOL=0xC5FE,TREV=0xC5FF,OLDIRQ=0xC600,OLDNMI=0xC602)
SRC=r'''
irq:
  LDX #78
  LDA #0
c1: STA NEW,X
  DEX
  BPL c1x
  JMP c1done
c1x: JMP c1
c1done:
  LDA #$FF
  STA $DC00
  LDA $DC00
  EOR #$FF
  AND #$1F
  STA JA
  LDA $DC01
  EOR #$FF
  AND #$1F
  STA JB
  LDA #0
  STA $FE
  LDA #$FE
  STA $FB
scan: LDA $FB
  STA $DC00
  LDA $DC01
  EOR #$FF
  BEQ nxt
  STA $FC
  LDY #0
bit: LSR $FC
  BCC nb
  LDA $FE
  ASL A
  ASL A
  ASL A
  STY $FD
  ORA $FD
  TAX
  LDA #1
  STA NEW,X
nb: INY
  CPY #8
  BNE bit
nxt: SEC
  ROL $FB
  INC $FE
  LDA $FE
  CMP #8
  BNE scan
  LDA #$FF
  STA $DC00
  LDA JA
  LDX #0
ja: LSR A
  BCC ja1
  PHA
  LDA #1
  STA NEW+64,X
  PLA
ja1: INX
  CPX #5
  BNE ja
  LDA JB
  LDX #0
jb: LSR A
  BCC jb1
  PHA
  LDA #1
  STA NEW+69,X
  PLA
jb1: INX
  CPX #5
  BNE jb
  LDA NEW+15
  ORA NEW+52
  BEQ nof
  LDA NEW+4
  BEQ f2
  LDA #0
  STA NEW+4
  LDA #1
  STA NEW+75
f2: LDA NEW+5
  BEQ f3
  LDA #0
  STA NEW+5
  LDA #1
  STA NEW+76
f3: LDA NEW+6
  BEQ f4
  LDA #0
  STA NEW+6
  LDA #1
  STA NEW+77
f4: LDA NEW+3
  BEQ nof
  LDA #0
  STA NEW+3
  LDA #1
  STA NEW+78
nof: LDA RSTC
  BEQ r0
  DEC RSTC
  LDA #1
  STA NEW+74
r0: LDX #0
lp: LDA NEW,X
  BNE pr
  LDA TRIED,X
  JMP chk
pr: LDA #2
chk: CMP DISP,X
  BNE chg
  JMP nx
chg: STA DISP,X
  CMP #2
  BNE draw
  LDA #1
  STA TRIED,X
  TXA
  CLC
  ADC #1
  STA LAST
  INC EVT
draw: LDA LENT,X
  BNE dr1
  JMP nx
dr1: STA TCNT
  TXA
  PHA
  LDA TABLO,X
  STA $FB
  STA $F9
  LDA TABHI,X
  STA $FC
  CLC
  ADC #$D4
  STA $FA
  LDA DISP,X
  TAX
  LDA COL,X
  STA TCOL
  LDA REVT,X
  STA TREV
  LDY #0
dl: LDA ($FB),Y
  AND #$7F
  ORA TREV
  STA ($FB),Y
  LDA TCOL
  STA ($F9),Y
  INY
  CPY TCNT
  BNE dl
  PLA
  TAX
nx: INX
  CPX #79
  BEQ done
  JMP lp
done: JMP (OLDIRQ)
nmih: PHA
  LDA #8
  STA RSTC
  PLA
  JMP (OLDNMI)
install: SEI
  LDA $0315
  CMP #$C0
  BEQ ins2
  LDA $0314
  STA OLDIRQ
  LDA $0315
  STA OLDIRQ+1
  LDA #<irq
  STA $0314
  LDA #>irq
  STA $0315
ins2: LDA $0319
  CMP #$C0
  BEQ ins3
  LDA $0318
  STA OLDNMI
  LDA $0319
  STA OLDNMI+1
  LDA #<nmih
  STA $0318
  LDA #>nmih
  STA $0319
ins3: CLI
  RTS
'''
if __name__=='__main__':
    out,sym=assemble(SRC,0xC000,SYM)
    print(len(out),'byte; install=$%04X irq=$%04X nmih=$%04X'%(sym['install'],sym['irq'],sym['nmih']),file=sys.stderr)
    json.dump({'bytes':out,'install':sym['install'],'irq':sym['irq'],'nmih':sym['nmih']},open('ml.json','w'))
