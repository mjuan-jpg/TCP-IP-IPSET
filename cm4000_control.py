#!/usr/bin/env python3
"""
CM4000 Remote Control Client
Connects to the CM4000 simulator's control port to inject faults and monitor status remotely.
"""

import socket
import threading
import sys
import argparse
import time
import random

def receive_data(sock):
    """Continuously receive data from the control server and print it."""
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            # Print without extra newlines since the server formats it
            sys.stdout.write(data.decode('utf-8'))
            sys.stdout.flush()
    except Exception:
        pass
    finally:
        print("\n⏻  Connection closed by server.")
        import os
        os._exit(0)

def run_pdf(sock, freq, total_time):
    print(f"\n🚀 Iniciando Perfil de Fallas Automático (PDF)\n   Frecuencia: cada {freq}s | Duración Total: {total_time}s\n")
    start_time = time.time()
    
    event_types = ['sag', 'swell', 'overload', 'harmonic', 'phase_loss', 'low_pf']
    phases = ['a', 'b', 'c', 'all']

    while (time.time() - start_time) < total_time:
        num_faults = random.randint(1, 3)
        for _ in range(num_faults):
            ev = random.choice(event_types)
            ph = random.choice(phases)
            dur = random.randint(5, 30)
            
            if ev == 'sag':
                val = random.randint(10, 80)
                cmd = f"sag {ph} {val} {dur}"
            elif ev == 'swell':
                val = random.randint(10, 40)
                cmd = f"swell {ph} {val} {dur}"
            elif ev == 'overload':
                val = round(random.uniform(1.2, 3.0), 1)
                cmd = f"overload {ph} {val} {dur}"
            elif ev == 'harmonic':
                val = random.randint(10, 40)
                cmd = f"harmonic {ph} {val} {dur}"
            elif ev == 'phase_loss':
                cmd = f"phase_loss {ph} {dur}"
            elif ev == 'low_pf':
                val = round(random.uniform(0.3, 0.7), 2)
                cmd = f"low_pf {val} {dur}"
            
            # Send the command to the server
            sock.sendall((cmd + "\n").encode('utf-8'))
            time.sleep(0.3)
            
        # Esperamos el tiempo de frecuencia o hasta que se acabe el tiempo total
        time_to_wait = freq
        while time_to_wait > 0:
            step = min(1.0, time_to_wait)
            time.sleep(step)
            time_to_wait -= step
            if (time.time() - start_time) >= total_time:
                break
        
    print("\n✅ Perfil de Fallas (PDF) Finalizado. El sistema retornará a la normalidad al expirar las últimas fallas.")
    print("CM4000> ", end="", flush=True)

def main():
    parser = argparse.ArgumentParser(description="CM4000 Remote Control Interface")
    parser.add_argument("--host", default="localhost", help="Control server host")
    parser.add_argument("--port", type=int, default=5021, help="Control server port")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((args.host, args.port))
    except Exception as e:
        print(f"❌ Cannot connect to {args.host}:{args.port} - {e}")
        return

    # Start a background thread to listen to server responses
    t = threading.Thread(target=receive_data, args=(sock,), daemon=True)
    t.start()

    # The main thread blocks on stdin waiting for user commands
    try:
        while True:
            cmd = sys.stdin.readline()
            if not cmd:
                break
            
            cmd_lower = cmd.strip().lower()
            
            # Intercept PDF command locally
            if cmd_lower == 'pdf':
                try:
                    freq = float(input("➤ Ingrese la frecuencia de inyección de fallas (segundos): "))
                    total = float(input("➤ Ingrese el tiempo total de la prueba (segundos): "))
                    # Run in a background thread so the client CLI remains responsive
                    threading.Thread(target=run_pdf, args=(sock, freq, total), daemon=True).start()
                except ValueError:
                    print("❌ Error: Debe ingresar valores numéricos.")
                    print("CM4000> ", end="", flush=True)
                continue

            sock.sendall(cmd.encode('utf-8'))
            
            # If the user types quit, exit, or shutdown, we break the local loop
            if cmd_lower in ('quit', 'exit', 'shutdown'):
                break
    except KeyboardInterrupt:
        print("\n⏻  Exiting control client.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
