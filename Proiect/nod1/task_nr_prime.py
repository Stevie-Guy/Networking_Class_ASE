import time
import math

class NrPrime:
    def execute(self, start, end):
        """
        Gaseste toate numerele prime intr-un interval [start, end].
        Este o metoda simpla ce solicita CPU-ul pentru a demonstra executia paralela.
        """
        print(f"[NrPrime] Incep cautarea numerelor prime intre {start} si {end}...")
        primes = []
        for num in range(max(2, start), end + 1):
            is_prime = True
            for i in range(2, int(math.sqrt(num)) + 1):
                if num % i == 0:
                    is_prime = False
                    break
            if is_prime:
                primes.append(num)
        
        # Simulează un pic de extra delay pentru a observa mai bine paralelismul
        time.sleep(1)
        print(f"[NrPrime] Cautarea finalizata. Gasite {len(primes)} numere prime.")
        return len(primes)
