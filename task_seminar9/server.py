import socket

HOST        = '127.0.0.1'
PORT        = 9999
BUFFER_SIZE = 1024

clienti_conectati = {}

# Structura de stocare a mesajelor: { id: { 'text': str, 'autor': adresa_client } }
mesaje = {}
contor_id = 0

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((HOST, PORT))

print("=" * 50)
print(f"  SERVER UDP pornit pe {HOST}:{PORT}")
print("  Asteptam mesaje de la clienti...")
print("=" * 50)

while True:
    try:
        date_brute, adresa_client = server_socket.recvfrom(BUFFER_SIZE)
        mesaj_primit = date_brute.decode('utf-8').strip()

        parti = mesaj_primit.split(' ', 1)
        comanda = parti[0].upper()
        argumente = parti[1] if len(parti) > 1 else ''

        print(f"\n[PRIMIT] De la {adresa_client}: '{mesaj_primit}'")

        if comanda == 'CONNECT':
            if adresa_client in clienti_conectati:
                raspuns = "EROARE: Esti deja conectat la server."
            else:
                clienti_conectati[adresa_client] = True
                nr_clienti = len(clienti_conectati)
                raspuns = f"OK: Conectat cu succes. Clienti activi: {nr_clienti}"
                print(f"[SERVER] Client nou conectat: {adresa_client}")

        elif comanda == 'DISCONNECT':
            if adresa_client in clienti_conectati:
                del clienti_conectati[adresa_client]
                raspuns = "OK: Deconectat cu succes. La revedere!"
                print(f"[SERVER] Client deconectat: {adresa_client}")
            else:
                raspuns = "EROARE: Nu esti conectat la server."

        elif comanda == 'PUBLISH':
            # Verificare conexiune
            if adresa_client not in clienti_conectati:
                raspuns = "EROARE: Nu esti conectat la server."
            # Verificare argument
            elif not argumente.strip():
                raspuns = "EROARE: Mesajul nu poate fi gol."
            else:
                contor_id += 1
                mesaje[contor_id] = {
                    'text': argumente.strip(),
                    'autor': adresa_client
                }
                raspuns = f"OK: Mesaj publicat cu ID={contor_id}"
                print(f"[SERVER] Mesaj nou ID={contor_id} de la {adresa_client}")

        elif comanda == 'DELETE':
            # Verificare conexiune
            if adresa_client not in clienti_conectati:
                raspuns = "EROARE: Nu esti conectat la server."
            else:
                # Verificare ca argumentul este un numar intreg valid
                try:
                    id_de_sters = int(argumente.strip())
                except ValueError:
                    raspuns = "EROARE: ID-ul trebuie sa fie un numar intreg valid."
                else:
                    if id_de_sters not in mesaje:
                        raspuns = f"EROARE: Nu exista niciun mesaj cu ID={id_de_sters}."
                    elif mesaje[id_de_sters]['autor'] != adresa_client:
                        raspuns = f"EROARE: Doar autorul poate sterge mesajul cu ID={id_de_sters}."
                    else:
                        del mesaje[id_de_sters]
                        raspuns = f"OK: Mesajul cu ID={id_de_sters} a fost sters cu succes."
                        print(f"[SERVER] Mesaj ID={id_de_sters} sters de {adresa_client}")

        elif comanda == 'LIST':
            # Verificare conexiune
            if adresa_client not in clienti_conectati:
                raspuns = "EROARE: Nu esti conectat la server."
            elif not mesaje:
                raspuns = "OK: Nu exista niciun mesaj publicat."
            else:
                linii = [f"OK: Lista mesajelor ({len(mesaje)} mesaj(e)):"]
                for msg_id, msg_data in mesaje.items():
                    linii.append(f"  [ID={msg_id}] {msg_data['text']}")
                raspuns = "\n".join(linii)

        else:
            raspuns = f"EROARE: Comanda '{comanda}' este invalida. Comenzi valide: CONNECT, DISCONNECT, PUBLISH, DELETE, LIST"

        server_socket.sendto(raspuns.encode('utf-8'), adresa_client)
        print(f"[TRIMIS]  Catre {adresa_client}: '{raspuns}'")

    except KeyboardInterrupt:
        print("\n[SERVER] Oprire server...")
        break
    except Exception as e:
        print(f"[EROARE] {e}")

server_socket.close()
print("[SERVER] Socket inchis.")
