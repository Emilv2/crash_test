import math

a = []
b = 1.1
for i in range(500000000):
    a.append(b)
    try:
        b = b + math.log(b) * b**2
    except:
        b = min(1.2, b/100000)

print(a[-1])
