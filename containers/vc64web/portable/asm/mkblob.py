import ast,re,json,sys
import os
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
import asm
sh=open(os.path.join(HERE,'..','shell.html'),encoding='utf8').read()
m=re.search(r"const KT_KEYS=\[[^\n]*\n(.*?)\n\];",sh,re.S)
KEYS=ast.literal_eval('['+m.group(1)+']')
ml,sym=asm.assemble(asm.SRC,0xC000,asm.SYM)
BASE=0x0A00
SC={'@':0,'£':28,'←':31,'↑':30}
def sc(ch):
    if ch in SC: return SC[ch]
    o=ord(ch)
    if 'A'<=ch<='Z': return o-64
    if ch=='[': return 27
    if ch==']': return 29
    if 32<=o<=63: return o
    raise Exception('character not supported: %r'%ch)
scr=[32]*1000; col=[11]*1000
def put(x,y,t,c=None):
    for i,ch in enumerate(t):
        scr[y*40+x+i]=sc(ch)
        if c is not None: col[y*40+x+i]=c
for code,x,y,label in KEYS: put(x,y,label)
put(9,0,"KEY AND JOYSTICK TEST",1)
put(1,1,"GREY=TO BE TESTED  GREEN=TESTED")
put(0,13,"SHIFT+F1/F3/F5/F7 = F2/F4/F6/F8")
put(0,14,"JOYSTICK PORT 2"); put(0,17,"JOYSTICK PORT 1")
put(0,21,"LAST:  "); put(0,22,"EVENTS:")
put(0,23,"STOP DISABLED - TO EXIT: RESET")
tab=[0]*240
for code,x,y,label in KEYS:
    ad=1024+y*40+x; tab[code]=ad&255; tab[80+code]=ad>>8; tab[160+code]=len(label)
colrev=[11,13,1,0, 0,0,128,0]
# init code
INIT=r'''
init: LDA #225
  STA $0328
  LDA #11
  STA $0286
  LDA #0
  STA $D020
  STA $D021
  TAY
z: STA $C500,Y
  INY
  BNE z
  LDX #0
jb: LDA JOBS,X
  STA $FB
  LDA JOBS+1,X
  STA $FC
  LDA JOBS+2,X
  STA $FD
  LDA JOBS+3,X
  STA $FE
  LDA JOBS+4,X
  STA $F9
  LDA JOBS+5,X
  STA $FA
  LDY #0
cp: LDA $F9
  ORA $FA
  BEQ nj
  LDA ($FB),Y
  STA ($FD),Y
  INY
  BNE c2
  INC $FC
  INC $FE
c2: LDA $F9
  BNE c3
  DEC $FA
c3: DEC $F9
  JMP cp
nj: TXA
  CLC
  ADC #6
  TAX
  CPX #JOBSLEN
  BNE jb
  JSR INSTALL
  RTS
'''
payload=[('ml',ml,0xC000),('tab',tab,0xC400),('colrev',colrev,0xC5F0),('scr',scr,0x0400),('col',col,0xD800)]
S=dict(JOBS=0x0F00,JOBSLEN=6*len(payload),INSTALL=sym['install'])
code,_=asm.assemble(INIT,BASE,S)
jobs_at=BASE+len(code)
S['JOBS']=jobs_at
code,_=asm.assemble(INIT,BASE,S)
assert BASE+len(code)==jobs_at
addr=jobs_at+6*len(payload); jobs=[]; data=[]
for name,bs,dst in payload:
    jobs+=[addr&255,addr>>8,dst&255,dst>>8,len(bs)&255,len(bs)>>8]; data+=list(bs); addr+=len(bs)
blob=code+jobs+data
json.dump({'base':BASE,'bytes':blob},open(sys.argv[1] if len(sys.argv)>1 else os.path.join(HERE,'blob.json'),'w'))
print('blob',len(blob),'bytes; init $%04X'%BASE, file=sys.stderr)
