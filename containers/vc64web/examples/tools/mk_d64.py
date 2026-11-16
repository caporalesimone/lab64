#!/usr/bin/env python3
# Creates a test D64 disk image with a BASIC program (HELLO): used by the examples that attach a disk.
# usage: python3 mk_d64.py [output.d64]      Copyright © 2026 Simone Caporale
import sys
SPT = [21]*17 + [19]*7 + [18]*6 + [17]*5          # sectors per track, tracks 1-35
def off(t, s): return (sum(SPT[:t-1]) + s) * 256
d = bytearray(174848)
# BAM (18/0)
b = off(18, 0); d[b:b+4] = bytes([18, 1, 0x41, 0])
for t in range(1, 36):
    n = SPT[t-1]; bits = (1 << n) - 1
    if t == 18: bits &= ~0b11; n -= 2                  # 18/0 and 18/1 used
    d[b+4*t:b+4*t+4] = bytes([n, bits & 255, (bits >> 8) & 255, (bits >> 16) & 255])
name = b'TESTDISK'; d[b+0x90:b+0xA0] = name.ljust(16, b'\xa0'); d[b+0xA0:b+0xA2] = b'\xa0\xa0'; d[b+0xA2:b+0xA4] = b'AB'; d[b+0xA4] = 0xA0; d[b+0xA5:b+0xA7] = b'2A'; d[b+0xA7:b+0xAB] = b'\xa0'*4
# BASIC program:  10 PRINT"HELLO FROM D64"
line = bytes([0x0A, 0x00, 0x99, 0x20, 0x22]) + b'HELLO FROM D64' + bytes([0x22, 0x00])
prog = bytes([0x01, 0x08]) + bytes([(0x0801 + 2 + len(line)) & 255, (0x0801 + 2 + len(line)) >> 8]) + line + bytes([0, 0])
t0, s0 = 1, 0; o = off(t0, s0); d[o] = 0; d[o+1] = len(prog) + 1; d[o+2:o+2+len(prog)] = prog      # one sector only (<254 bytes)
b0 = b + 4*1; d[b0] -= 1; d[b0+1] &= ~1                                                                # 1/0 used
# directory (18/1)
o = off(18, 1); d[o] = 0; d[o+1] = 0xFF; d[o+2] = 0x82; d[o+3] = t0; d[o+4] = s0; d[o+5:o+21] = b'HELLO'.ljust(16, b'\xa0'); d[o+30] = 1; d[o+31] = 0
open(sys.argv[1] if len(sys.argv) > 1 else 'test.d64', 'wb').write(d)
