# Ghid Pas cu Pas pentru Înregistrarea Video Demo

Acest ghid conține pașii exacți pentru a bifa toate cerințele (scenariile) din temă și a obține punctajul maxim. 
Am pregătit deja mediul pentru tine: ai 3 foldere (`nod1`, `nod2` și `nod3`). Fișierul `task_example.py` se află intenționat **doar** în `nod1` pentru a putea demonstra transferul dinamic de clasă.

---

## Pregătirea
Deschide **3 ferestre de terminal distincte** (recomand PowerShell sau Command Prompt) și așează-le una lângă cealaltă pe ecran ca să se vadă toate concomitent.

---

## PASUL 1: Pornirea rețelei (Bifează Scenariile 1 și 2)

1. **În Terminalul 1**: scrie `cd nod1` și pornește primul nod folosind comanda:
   ```bash
   python node.py 5001
   ```
   *(El va deveni primul server din rețea).*

2. **În Terminalul 2**: scrie `cd nod2` și conectează-l la primul:
   ```bash
   python node.py 5002 127.0.0.1:5001
   ```
   *Arată în video cum primul terminal reacționează și se descoperă reciproc.*

3. **În Terminalul 3**: scrie `cd nod3` și conectează-l tot la primul:
   ```bash
   python node.py 5003 127.0.0.1:5001
   ```

4. Tastează comanda `nodes` în toate trei terminalele. 
   *Evidențiază faptul că, deși nodul 3 s-a conectat la nodul 1, nodul 2 știe și el de existența lui datorită propagării stării în rețea. Toate trei ar trebui să aibă load `0`.*

---

## PASUL 2: Execuția Paralelă și Transferul Clasei (Bifează Scenariile 3, 4, 5)

1. Revino în **Terminalul 1** (`nod1` este singurul care are fișierul `task_nr_prime.py`) și trimite un request greu către rețea scriind comanda:
   ```bash
   exec task_nr_prime NrPrime execute 3 1 1000000
   ```
   *(Cifra `3` reprezintă numărul de thread-uri, iar restul sunt intervalul în care va căuta numere prime).*

2. **Arată în video următoarele:**
   * Nodul 1 zice că a ales unul dintre serverele 5002/5003 pentru că aveau load 0. **(Scenariul 4: ales minimum load)**.
   * Privește spre terminalul serverului ales (ex. nod2). Acolo va apărea: 
     `[EXEC] Module task_nr_prime not found. Requesting from source...`
   * Imediat după, primește clasa prin rețea și scrie: `[CLASS] Received and saved task_nr_prime.py`. **(Scenariul 5: Transferul Clasei)**.

---

## PASUL 3: Urmărirea Sistemului și a Rezultatelor (Bifează Scenariile 6, 7)

1. Cât timp serverul ales procesează și caută numere prime, treci imediat într-un alt terminal și scrie din nou: `nodes`.
2. Arată pe video că Load-ul serverului ales a crescut la **3** (deoarece i-ai trimis executarea pe 3 threaduri), demonstrând **Scenariul 7 (Actualizarea și propagarea gradului de încărcare)**.
3. Când căutarea se va sfârși, în **Terminalul 1** se vor afișa rezultatele sosite treptat pe rețea: 
   `[RESULT] Task ... completed on thread X. Result: ...` **(Scenariul 6: Livrarea rezultatelor către client)**.
4. Scrie din nou `nodes` ca să arăți că load-ul serverului care a executat a coborât corect înapoi la `0`, eliberând serverul.

---

## PASUL 4: Deconectarea curată (Bifează Scenariul 8)

1. Du-te direct în **Terminalul 3** și oprește-l forțat (ori închizi pur și simplu fereastra de terminal cu 'X', ori apeși pe tastatură `CTRL + C`).
2. Treci rapid în **Terminalul 1** și **2**; vei vedea imediat mesajul: 
   `[CLUSTER] Node disconnected: 127.0.0.1:5003`.
3. Rulează din nou comanda `nodes` pe ele ca să arăți evaluatorului că nu a crăpat niciunul din procesele rămase, iar nodul deconectat a fost eliminat corect din evidență, fără blocaje (deadlocks).
