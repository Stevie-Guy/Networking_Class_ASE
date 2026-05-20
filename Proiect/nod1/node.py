import socket
import threading
import json
import struct
import sys
import os
import time
import base64
import importlib
from concurrent.futures import ThreadPoolExecutor

class P2PNode:
    def __init__(self, host, port, known_peers):
        self.host = host
        self.port = int(port)
        self.known_peers = known_peers # list of (ip, port)
        
        self.load = 0
        self.cluster_nodes = {} # (ip, port) -> load
        self.cluster_nodes[(self.host, self.port)] = self.load
        
        self.lock = threading.Lock()
        
        self.clients = [] # list of sockets connected to us
        self.upstream_conn = None # socket connected to an upstream server
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        
        self.executor = ThreadPoolExecutor(max_workers=20)
        
        # Keep track of where a task came from to send the result back
        self.pending_tasks = {} # task_id -> (requester_addr, task_info)

    def start(self):
        # Start server thread
        threading.Thread(target=self._accept_connections, daemon=True).start()
        print(f"[NODE] Started listening on {self.host}:{self.port}")
        
        # Try to connect to cluster
        self._connect_to_cluster()
        
        # Start interactive CLI
        self._cli_loop()

    # --- Networking Helpers ---

    def _send_msg(self, sock, msg_dict):
        try:
            data = json.dumps(msg_dict).encode('utf-8')
            header = struct.pack('!I', len(data))
            sock.sendall(header + data)
        except Exception as e:
            print(f"[ERROR] Failed to send message: {e}")

    def _recv_msg(self, sock):
        try:
            header = sock.recv(4)
            if not header:
                return None
            msg_len = struct.unpack('!I', header)[0]
            
            data = b""
            while len(data) < msg_len:
                chunk = sock.recv(min(4096, msg_len - len(data)))
                if not chunk:
                    return None
                data += chunk
            return json.loads(data.decode('utf-8'))
        except BaseException:
            return None

    def _broadcast(self, msg_dict, exclude_sock=None):
        with self.lock:
            socks = list(self.clients)
            if self.upstream_conn:
                socks.append(self.upstream_conn)
                
        for s in socks:
            if s != exclude_sock:
                self._send_msg(s, msg_dict)

    # --- Server / Client Logic ---

    def _accept_connections(self):
        while True:
            try:
                client_sock, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_connection, args=(client_sock,), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Accept error: {e}")

    def _connect_to_cluster(self):
        for peer_ip, peer_port in self.known_peers:
            if peer_ip == self.host and peer_port == self.port:
                continue
            try:
                print(f"[NODE] Trying to connect to {peer_ip}:{peer_port}...")
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((peer_ip, peer_port))
                self.upstream_conn = s
                
                # Send connect message
                self._send_msg(s, {
                    "type": "CONNECT",
                    "ip": self.host,
                    "port": self.port
                })
                
                # Start listening to upstream
                threading.Thread(target=self._handle_connection, args=(s,), daemon=True).start()
                print(f"[NODE] Successfully connected to {peer_ip}:{peer_port}")
                return
            except Exception as e:
                print(f"[NODE] Could not connect to {peer_ip}:{peer_port} - {e}")
                
        print("[NODE] No known peers available. Starting as the first node in the cluster.")

    def _handle_connection(self, sock):
        peer_addr_info = None # (ip, port)
        try:
            while True:
                msg = self._recv_msg(sock)
                if not msg:
                    break
                
                msg_type = msg.get("type")
                
                if msg_type == "CONNECT":
                    peer_addr_info = (msg["ip"], msg["port"])
                    with self.lock:
                        if sock != self.upstream_conn and sock not in self.clients:
                            self.clients.append(sock)
                        self.cluster_nodes[peer_addr_info] = 0
                        
                    print(f"[CLUSTER] New node joined: {peer_addr_info[0]}:{peer_addr_info[1]}")
                    
                    # Send full cluster state to the new node
                    self._send_msg(sock, {
                        "type": "CLUSTER_STATE",
                        "state": [[ip, port, load] for (ip, port), load in self.cluster_nodes.items()]
                    })
                    
                    # Broadcast to others about this new node
                    self._broadcast({
                        "type": "NEW_NODE",
                        "ip": peer_addr_info[0],
                        "port": peer_addr_info[1],
                        "load": 0
                    }, exclude_sock=sock)
                    
                elif msg_type == "CLUSTER_STATE":
                    with self.lock:
                        for ip, port, load in msg["state"]:
                            self.cluster_nodes[(ip, port)] = load
                    print(f"[CLUSTER] Received cluster state. Known nodes: {len(self.cluster_nodes)}")
                    
                elif msg_type == "NEW_NODE":
                    node_info = (msg["ip"], msg["port"])
                    with self.lock:
                        if node_info not in self.cluster_nodes:
                            self.cluster_nodes[node_info] = msg["load"]
                            print(f"[CLUSTER] Discovered new node: {node_info[0]}:{node_info[1]}")
                    self._broadcast(msg, exclude_sock=sock) # Propagate
                    
                elif msg_type == "LOAD_UPDATE":
                    node_info = (msg["ip"], msg["port"])
                    with self.lock:
                        if node_info in self.cluster_nodes:
                            self.cluster_nodes[node_info] = msg["load"]
                    self._broadcast(msg, exclude_sock=sock)
                    
                elif msg_type == "NODE_DISCONNECT":
                    node_info = (msg["ip"], msg["port"])
                    with self.lock:
                        if node_info in self.cluster_nodes:
                            del self.cluster_nodes[node_info]
                            print(f"[CLUSTER] Node disconnected: {node_info[0]}:{node_info[1]}")
                    self._broadcast(msg, exclude_sock=sock)
                    
                elif msg_type == "EXEC_REQ":
                    # We have received a request to execute a method
                    threading.Thread(target=self._handle_exec_req, args=(msg, sock), daemon=True).start()
                    
                elif msg_type == "CLASS_REQ":
                    # Someone wants a class file from us
                    self._handle_class_req(msg, sock)
                    
                elif msg_type == "CLASS_RES":
                    # We received the class file we requested
                    self._handle_class_res(msg)
                    
                elif msg_type == "EXEC_RES":
                    # We received the result of an execution
                    print(f"\n[RESULT] Task {msg['task_id']} completed on thread {msg['thread_id']}. Result: {msg['result']}")
                    
        except Exception as e:
            # Socket closed or error
            pass
        finally:
            self._handle_disconnect(sock, peer_addr_info)

    def _handle_disconnect(self, sock, peer_addr_info):
        do_broadcast = False
        with self.lock:
            if sock in self.clients:
                self.clients.remove(sock)
            if sock == self.upstream_conn:
                self.upstream_conn = None
                print("[NODE] Upstream connection lost.")
                
            if peer_addr_info and peer_addr_info in self.cluster_nodes:
                del self.cluster_nodes[peer_addr_info]
                print(f"[CLUSTER] Node disconnected: {peer_addr_info[0]}:{peer_addr_info[1]}")
                do_broadcast = True

        if do_broadcast:
            self._broadcast({
                "type": "NODE_DISCONNECT",
                "ip": peer_addr_info[0],
                "port": peer_addr_info[1]
            })

    # --- Load Management ---
    
    def _update_my_load(self, delta):
        with self.lock:
            self.load += delta
            self.cluster_nodes[(self.host, self.port)] = self.load
            
        # Broadcast load update
        self._broadcast({
            "type": "LOAD_UPDATE",
            "ip": self.host,
            "port": self.port,
            "load": self.load
        })

    # --- Execution Logic ---

    def _handle_exec_req(self, msg, requester_sock):
        module_name = msg["module"]
        class_name = msg["class"]
        method_name = msg["method"]
        num_threads = msg["num_threads"]
        args = msg.get("args", [])
        task_id = msg["task_id"]
        
        print(f"[EXEC] Received request to run {class_name}.{method_name} on {num_threads} threads.")
        
        # Check if we have the module
        try:
            importlib.import_module(module_name)
        except ImportError:
            print(f"[EXEC] Module {module_name} not found. Requesting from source...")
            # We need to request the class from the requester
            self.pending_tasks[task_id] = {
                "msg": msg,
                "sock": requester_sock
            }
            self._send_msg(requester_sock, {
                "type": "CLASS_REQ",
                "module": module_name,
                "task_id": task_id
            })
            return

        # If we have it, run it
        self._run_task(msg, requester_sock)

    def _run_task(self, msg, requester_sock):
        module_name = msg["module"]
        class_name = msg["class"]
        method_name = msg["method"]
        num_threads = msg["num_threads"]
        args = msg.get("args", [])
        task_id = msg["task_id"]
        requester_info = msg["requester"] # (ip, port)
        
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        instance = cls()
        method = getattr(instance, method_name)
        
        def worker(t_id):
            self._update_my_load(1)
            try:
                res = method(*args)
                
                # Send result directly back to the requester via a temporary socket if it's not directly connected,
                # or just try to send it back. For simplicity, we open a new socket to the requester's server port.
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((requester_info[0], requester_info[1]))
                    self._send_msg(s, {
                        "type": "EXEC_RES",
                        "task_id": task_id,
                        "thread_id": t_id,
                        "result": res
                    })
                    s.close()
                except Exception as e:
                    print(f"[ERROR] Could not send result to {requester_info}: {e}")
                    
            except Exception as e:
                print(f"[ERROR] Task execution failed: {e}")
            finally:
                self._update_my_load(-1)

        for i in range(num_threads):
            self.executor.submit(worker, i)

    def _handle_class_req(self, msg, sock):
        module_name = msg["module"]
        file_path = f"{module_name}.py"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            self._send_msg(sock, {
                "type": "CLASS_RES",
                "module": module_name,
                "task_id": msg["task_id"],
                "content": content
            })
            print(f"[CLASS] Sent {file_path} to requester.")
        except Exception as e:
            print(f"[ERROR] Failed to read/send class {file_path}: {e}")

    def _handle_class_res(self, msg):
        module_name = msg["module"]
        content = msg["content"]
        task_id = msg["task_id"]
        
        file_path = f"{module_name}.py"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[CLASS] Received and saved {file_path}.")
            
            # Reload module if it was partially loaded
            importlib.invalidate_caches()
            
            # Now run the pending task
            if task_id in self.pending_tasks:
                task_info = self.pending_tasks.pop(task_id)
                self._run_task(task_info["msg"], task_info["sock"])
        except Exception as e:
            print(f"[ERROR] Failed to save class {file_path}: {e}")

    # --- CLI ---

    def _cli_loop(self):
        print("\n=== Cluster P2P CLI ===")
        print("Commands:")
        print("  nodes          - List known nodes and their load")
        print("  exec <mod> <cls> <met> <threads> [args...] - Run a method on least loaded node")
        print("  exit           - Quit")
        print("=======================\n")
        
        task_counter = 0
        
        while True:
            try:
                cmd = input("> ").strip().split()
                if not cmd:
                    continue
                
                if cmd[0] == "exit":
                    print("Exiting...")
                    break
                elif cmd[0] == "nodes":
                    with self.lock:
                        print("Known nodes:")
                        for (ip, port), load in self.cluster_nodes.items():
                            me = " (ME)" if ip == self.host and port == self.port else ""
                            print(f"  {ip}:{port} - Load: {load}{me}")
                elif cmd[0] == "exec":
                    if len(cmd) < 5:
                        print("Usage: exec <module> <class> <method> <threads> [arg1 arg2 ...]")
                        continue
                        
                    module_name = cmd[1]
                    class_name = cmd[2]
                    method_name = cmd[3]
                    num_threads = int(cmd[4])
                    
                    # Try to parse arguments as integers if possible
                    args = []
                    for arg in cmd[5:]:
                        try:
                            args.append(int(arg))
                        except ValueError:
                            args.append(arg)
                    
                    # Find node with minimum load
                    with self.lock:
                        if not self.cluster_nodes:
                            print("No nodes available.")
                            continue
                        def sort_key(item):
                            node_addr, load = item
                            is_me = 1 if node_addr == (self.host, self.port) else 0
                            return (load, is_me)
                        
                        min_node = min(self.cluster_nodes.items(), key=sort_key)
                        target_ip, target_port = min_node[0]
                    
                    print(f"Selected {target_ip}:{target_port} (Load: {min_node[1]}) for execution.")
                    
                    task_counter += 1
                    task_id = f"{self.host}:{self.port}-{task_counter}"
                    
                    req_msg = {
                        "type": "EXEC_REQ",
                        "task_id": task_id,
                        "module": module_name,
                        "class": class_name,
                        "method": method_name,
                        "num_threads": num_threads,
                        "args": args,
                        "requester": [self.host, self.port]
                    }
                    
                    # Send execution request to target node
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.connect((target_ip, target_port))
                        self._send_msg(s, req_msg)
                        # Don't close immediately if we might need to receive a CLASS_REQ back on this socket.
                        # Wait, the other side will send CLASS_REQ to this socket if needed.
                        # Actually, _handle_connection on the other side reads from the socket, so we need a thread here too.
                        # For simplicity, if we connect to send an EXEC_REQ, we should let the main server accept it and handle it.
                        # Oh wait, if we send on a temporary socket, the other side will try to send CLASS_REQ on it.
                        # We must listen on this temporary socket, OR the other side can just connect to our main server port.
                        # The code on the other side: "self._send_msg(requester_sock, {... 'type': 'CLASS_REQ' ...})"
                        # So it replies on the same socket! Thus, we must listen for a potential CLASS_REQ.
                        
                        def wait_for_class_req(temp_sock):
                            while True:
                                msg = self._recv_msg(temp_sock)
                                if not msg:
                                    break
                                if msg.get("type") == "CLASS_REQ":
                                    self._handle_class_req(msg, temp_sock)
                                # After sending class res, the other side closes or keeps it. We just break if it closes.
                        
                        threading.Thread(target=wait_for_class_req, args=(s,), daemon=True).start()
                        
                    except Exception as e:
                        print(f"Failed to send execution request: {e}")
                        
                else:
                    print("Unknown command.")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [known_ip:known_port,known_ip2:known_port2...]")
        sys.exit(1)
        
    port = sys.argv[1]
    known_peers = []
    
    if len(sys.argv) > 2:
        peers_str = sys.argv[2].split(",")
        for p in peers_str:
            if ":" in p:
                ip, p_port = p.split(":")
                known_peers.append((ip, int(p_port)))
                
    node = P2PNode("127.0.0.1", port, known_peers)
    node.start()
