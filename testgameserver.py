import socket
import threading
import time
import random
import math
from datetime import datetime
import subprocess
import json

print(f"Server IP: {subprocess.check_output('ipconfig getifaddr en0', shell=True).decode()}")

# --- 1. SHARED DATA ---
client_timers = {}
clients = {}        # {addr: data_string}
world_map = {}      # The "Source of Truth" for blocks
world_events = []   # Temporary list for MINE/PLACE/HIT actions
PORT = 5555
name_to_addr = {}
# --- 2. SETTINGS ---
WORLD_LIMIT = 70   # Size of the map
DENSITY = 0.07      # 7% of tiles have blocks
carried_players = {}

# --- 3. WORLD GENERATION ---
def generate_world():
    print("Generating world...")
    for x in range(-WORLD_LIMIT, WORLD_LIMIT):
        for y in range(-WORLD_LIMIT, WORLD_LIMIT):
            if random.random() < DENSITY:
                roll = random.random()
                if x == 0 and y == 0: continue
                if roll < 0.005: b_type = 4    # Diamond (Now 0.5%)
                elif roll < 0.05: b_type = 3   # Gold (Now 4.5% gap)
                elif roll < 0.20: b_type = 2   # Food (Now 15% gap)
                else: b_type = 1               # Dirt (Remaining 80%)
                world_map[(x, y)] = b_type
    print(world_map)

def broadcast():
    global world_events
    now = time.time()
    while True:
        if not clients: 
            time.sleep(0.1)
            continue
        now = time.time()
        for addr in list(clients.keys()):
            if now - client_timers.get(addr, 0) > 5: # 5 second timeout
                print(f"Player {addr} timed out.")
                
                p_data = clients[addr].split(",")
                p_name = p_data[4]

                to_drop = [pass_name for pass_name, carrier_addr in carried_players.items() if carrier_addr == addr]
                for name in to_drop:
                    del carried_players[name]
                
                if p_name in carried_players:
                    del carried_players[p_name]

                del clients[addr]
                if addr in client_timers: del client_timers[addr]
            
        player_str = "|".join([f"{addr}#{data}" for addr, data in clients.items()])
        
        # We send events then CLEAR them so they don't repeat (fixes health bug)
        event_str = "/".join(world_events)
        world_events = [] 
        
        packet = f"{player_str}@{event_str}".encode()
        for addr in list(clients.keys()):
            try:
                server.sendto(packet, eval(addr))
            except:
                if addr in clients: del clients[addr]
                print("Error processing a client", addr)
            time.sleep(0.01)
        time.sleep(0.05) # Prevent CPU overload

# --- 4. SERVER STARTUP ---
generate_world()
server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(('0.0.0.0', PORT))
print(f"Server started on port {PORT}...")

threading.Thread(target=broadcast, daemon=True).start()
time.sleep(0.1)

# --- 5. MAIN RECEIVE LOOP ---
try:
    last_spawn_time = time.time()
    SPAWN_INTERVAL = 30 # Seconds
    while True:
        now2 = datetime.now()
        try:
            current_time = time.time()
            if current_time - last_spawn_time > SPAWN_INTERVAL:
                # 1. Pick a random empty spot
                new_x = random.randint(-WORLD_LIMIT, WORLD_LIMIT)
                new_y = random.randint(-WORLD_LIMIT, WORLD_LIMIT)
                if not (new_x == 0 and new_y == 0):
                    if (new_x, new_y) not in world_map:
                        # 2. Roll for rarity (Diamonds 0.5%, Gold 5%, Dirt 94.5%)
                        roll = random.random()

                        if roll < 0.005:
                            new_type = 4  # Diamond (Rare)
                        elif roll < 0.05:
                            new_type = 3  # Gold (Uncommon)
                        elif roll < 0.30: 
                            new_type = 2  # Food (The Survival Essential!)
                        else:
                            new_type = 1  # Dirt (Common)

                        world_map[(new_x, new_y)] = new_type
                        world_events.append(now2.strftime("%Y-%m-%d %H:%M:%S.%f")+": "+f"PLACE:{new_x}:{new_y}:{new_type}")
                        
                        print(f"Server spawned a new {new_type} at {new_x}, {new_y}")
                        last_spawn_time = current_time
            data, addr = server.recvfrom(4096)
            msg = data.decode()
            client_timers[str(addr)] = time.time()
            if "#" in msg:
                # msg looks like: x,y,hp,energy,NAME,selected
                parts = msg.split(",")
                if len(parts) > 4:
                    player_name = parts[4]
                    name_to_addr[player_name] = addr # Store the actual addr tuple
            if msg == "ACTION:QUIT":
                if str(addr) in clients:
                    del clients[str(addr)]
            if msg.startswith("CHAT:"):
                t = msg.split(":")
                for i,v in enumerate(clients):
                    self.sock.sendto(("URGENT_CHAT:"+t[1]+":"+t[2]).encode(), clients[v])
            elif msg.startswith("ACTION:REQUEST_MAP") or msg == "REQUEST_MAP":
                print(f"Syncing world with {addr}")
                # Use .copy() to prevent the "dictionary changed size" crash on the server too!
                for coords, block_id in world_map.copy().items():
                    response = f"PLACE:{coords[0]}:{coords[1]}:{block_id}"
                    server.sendto(response.encode(), addr)
                    time.sleep(0.01)
            
            elif msg.startswith("ACTION:"):
                # Update the server's world_map so new players see changes
                parts = msg.split(":")
                action = parts[1]
                if action == "MINE":
                    world_map.pop((int(float(parts[2])), int(float(parts[3]))), None)
                elif action == "PLACE":
                    world_map[(int(parts[2]), int(parts[3]))] = int(parts[4])
                elif action == "PICKUP":
                    target_name = parts[2]
                    
                    # 1. Find the target's address based on their name
                    target_addr = None
                    for a, data in clients.items():
                        if data.split(",")[4] == target_name:
                            target_addr = a
                            break
                            
                    if target_addr:
                        carrier_data = clients[addr].split(",")
                        victim_data = clients[target_addr].split(",")
                        
                        c_strength = float(carrier_data[6])
                        v_strength = float(victim_data[6])
                        
                        if c_strength > v_strength:
                            carried_players[target_name] = str(addr)
                            world_events.append(now2.strftime("%Y-%m-%d %H:%M:%S.%f")+": "+f"PICKUP:{target_name}:{addr}")
                        else:
                            pass
                elif action == "DROP":
                    target_name = parts[2]
                    if target_name in carried_players:
                        del carried_players[target_name]
                        world_events.append(now2.strftime("%Y-%m-%d %H:%M:%S.%f")+": "+f"DROP:{target_name}")
                elif action == "LEAVE_TAXI":
                    passenger_name = parts[2]
                    if passenger_name in carried_players:
                        del carried_players[passenger_name]
                        print(f"Player {passenger_name} jumped off the taxi.")
                        world_events.append(now2.strftime("%Y-%m-%d %H:%M:%S.%f")+": "+f"DROP:{passenger_name}")
                elif action == "GIVE":
                    # parts looks like ["ACTION", "GIVE", "RecipientName", "ItemID"]
                    recipient_name = parts[2]
                    item_id = parts[3]
                    
                    if recipient_name in name_to_addr:
                        recipient_addr = name_to_addr[recipient_name]
                        # Send a priority packet to the recipient
                        server.sendto(f"URGENT_GIVE:{item_id}".encode(), recipient_addr)
                        print(f"Server relayed {item_id} from {addr} to {recipient_name}")
                elif action == "HIT":
                    parts = msg.split(":")
                    victim_name = parts[2]
                    damage = parts[3]
                    
                    # THE DIRECT RELAY:
                    if victim_name in name_to_addr:
                        victim_addr = name_to_addr[victim_name]
                        # Send a direct "PRIORITY" packet to the victim
                        server.sendto(f"URGENT_HIT:{damage}".encode(), victim_addr)
                        print(f"Directly hitting {victim_name} at {victim_addr}")
                
                # Add to events to tell other clients
                world_events.append(now2.strftime("%Y-%m-%d %H:%M:%S.%f")+": "+msg.split(":", 1)[1])
            elif msg == "REQUEST_MAP":
                # Send the whole map to a new player
                for pos, bid in world_map.items():
                    server.sendto(f"MAP_DATA:{pos[0]}:{pos[1]}:{bid}".encode(), addr)
            else:
                clients[str(addr)] = msg
            with open("log.txt", "w") as f:
                f.write(self.world_events.join(""))
        except Exception as e:
            print(f"Server Error: {e}")
except KeyboardInterrupt:
    print("\nShutting down server...")
    server.close()  # Clean up the socket