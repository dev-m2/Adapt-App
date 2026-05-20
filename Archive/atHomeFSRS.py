import math

w = [0.0, 0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542]
# 0<w15<1 and 1<w16<6.


def R(t, S, w20, factor):
    R = (1 + factor * (t / S)) ** -w20
    return R

def factor(w20):
    factor = 0.9 ** (-1/w20) - 1#

def I(DR, S, w20):
    interval = (S / (0.9**(-1/w20 -1)) * (DR ** (-1/w20)-1))
    return interval

def SInc(D,R,w9, w15, w16, w8,w10):
    SInc = 1 + w15 * w16 * (e**w8) * (11-D) * (S ** -w9) * (math.e ** (w10 * (1-R)-1))
    # w8 controls the overall scale? w15 and w16 account for pressing "Hard" or "Easy"
    return SInc

def sIfAgain(D,S,R,w11,w12,w13,w14):
    newS = min(w11 * (D**-w12) * ((S+1)**w13 - 1) * (math.e ** (w14 * (1-R))), S)
    # w11 acts like e**w8, controlling the scale;
    return newS

def sameDayS(S,w17,G,w18,w19):
    newS = S * (e**w17) ** (G-3+w18)* (S**-w19)
    return newS

def initialD(G,w4,w5):
    initialD = w4 - math.e ** (w5 * (G-1)+1)

def nextD(w6, G, D, w7, D0):
    deltaD = -w6 * (G-3)
    Dprime1 = D + deltaD * ((10-D) / 9)
    Dprime2 = w7 * D0 + (1 - w7) * Dprime1
    #D0 = initialD(4)
    return Dprime2