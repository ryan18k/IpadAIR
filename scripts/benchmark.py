# Petit banc d'essai de la puce de l'iPad.
import sys, time, platform

print(f"Python {sys.version.split()[0]} sur {platform.system() or 'Emscripten'} (WebAssembly)")

t = time.perf_counter()
n = 2_000_000
crible = bytearray([1]) * (n + 1)
crible[0:2] = b"\x00\x00"
for i in range(2, int(n ** 0.5) + 1):
    if crible[i]:
        crible[i * i::i] = bytearray(len(range(i * i, n + 1, i)))
print(f"Nombres premiers jusqu'à {n:,} : {sum(crible):,} trouvés en {time.perf_counter() - t:.2f} s".replace(",", "'"))

import numpy as np
t = time.perf_counter()
a = np.random.rand(600, 600)
b = np.random.rand(600, 600)
for _ in range(5):
    c = a @ b
dt = time.perf_counter() - t
gflops = 5 * 2 * 600 ** 3 / dt / 1e9
print(f"Calcul matriciel 600×600 (×5) : {dt:.2f} s, environ {gflops:.1f} GFLOPS")
