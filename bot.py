import hashlib, json, time, os, sys, secrets, asyncio, re
import websockets

DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(DIR, "media")
STATE_FILE = os.path.join(DIR, "state.json")

GOAL_AMOUNT_MSATS = 1000000000 
GOAL_SUMMARY = "Direct Relief for Cuba: Food, Medicine & Dignity"
DESCRIPTION = """The economic crisis in Cuba has pushed vulnerable families, especially children and the elderly, to the brink. Famine, a lack of basic medicines, and deteriorating housing are our daily reality.

Why Crypto and Nostr? Traditional aid is often blocked or delayed. We use NIP-75 Zap Goals and crypto to create a direct, peer-to-peer channel. No banks, no middlemen, no censorship.

Every sat raised will be strictly allocated to Food, Medicine, and Dignified Housing. Your support is a lifeline."""

RELAYS = [
    "wss://relay.primal.net",
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.snort.social",
]

p = 2**256 - 2**32 - 977
n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)

def add(P, Q):
    if P is None: return Q
    if Q is None: return P
    if P[0] == Q[0] and (P[1] + Q[1]) % p == 0: return None
    l = 3 * P[0] * P[0] * pow(2 * P[1], -1, p) % p if P == Q else (Q[1] - P[1]) * pow(Q[0] - P[0], -1, p) % p
    x = (l * l - P[0] - Q[0]) % p
    return (x, (l * (P[0] - x) - P[1]) % p)

def mul(P, k):
    R = None
    while k:
        if k & 1: R = add(R, P)
        P = add(P, P); k >>= 1
    return R

def th(tag, *b):
    t = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(t + t + b"".join(b)).digest()

def nsec_to_hex(s):
    C = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    acc = bits = 0; out = []
    for c in s[5:-6]:
        acc = (acc << 5) | C.index(c); bits += 5
        while bits >= 8:
            bits -= 8; out.append((acc >> bits) & 255)
        acc &= (1 << bits) - 1
    return bytes(out).hex()

def sign(msg, sk):
    d = int(sk, 16); P = mul(G, d)
    if P[1] % 2: d = n - d
    px = P[0].to_bytes(32, 'big')
    t = (d ^ int.from_bytes(th("BIP0340/aux", secrets.token_bytes(32)), 'big')).to_bytes(32, 'big')
    k = int.from_bytes(th("BIP0340/nonce", t, px, msg), 'big') % n
    R = mul(G, k)
    if R[1] % 2: k = n - k
    rx = R[0].to_bytes(32, 'big')
    e = int.from_bytes(th("BIP0340/challenge", rx, px, msg), 'big') % n
    return (rx + ((k + e * d) % n).to_bytes(32, 'big')).hex()

def make_event(sk, content, kind=1, tags=None):
    if tags is None: tags = []
    pub = mul(G, int(sk, 16))[0].to_bytes(32, 'big').hex()
    ts = int(time.time())
    raw = json.dumps([0, pub, ts, kind, tags, content], separators=(',', ':'), ensure_ascii=False)
    eid = hashlib.sha256(raw.encode()).digest()
    return {"id": eid.hex(), "pubkey": pub, "created_at": ts, "kind": kind, "tags": tags, "content": content, "sig": sign(eid, sk)}

async def send(url, ev):
    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            await ws.send(json.dumps(["EVENT", ev]))
            r = json.loads(await asyncio.wait_for(ws.recv(), 15))
            print(f"{url} -> {r[0]}")
            return bool(r[0] == "OK" and r[2])
    except Exception as e:
        print(f"{url} error: {e}")
        return False

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"current_index": 0, "goal_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

async def main():
    nsec = os.environ.get("NOSTR_NSEC", "").strip()
    if not nsec:
        print("❌ Falta el secreto NOSTR_NSEC")
        return
    sk = nsec_to_hex(nsec)
    state = load_state()
    
    # 1. Publicar el Zap Goal (NIP-75) una sola vez
    if not state.get("goal_id"):
        goal_tags = [
            ["relays"] + RELAYS,
            ["amount", str(GOAL_AMOUNT_MSATS)],
            ["summary", GOAL_SUMMARY]
        ]
        goal_ev = make_event(sk, DESCRIPTION, kind=9041, tags=goal_tags)
        print("🎯 Publicando Zap Goal (Kind 9041)...")
        results = await asyncio.gather(*[send(r, goal_ev) for r in RELAYS])
        if any(results):
            state["goal_id"] = goal_ev["id"]
            save_state(state)
            print("✅ Zap Goal publicado y guardado.")
    
    # 2. Detectar todos los archivos en la carpeta media
    valid_ext = ('.jpg', '.jpeg', '.png', '.gif', '.mp4', '.webm')
    files = sorted([f for f in os.listdir(MEDIA_DIR) if f.lower().endswith(valid_ext)])
    
    if not files:
        print("❌ No hay fotos ni videos en la carpeta media/")
        return
        
    # 3. Seleccionar el archivo de esta semana (bucle infinito)
    idx = state.get("current_index", 0) % len(files)
    selected_file = files[idx]
    media_url = f"https://raw.githubusercontent.com/alfrexo95/FondosAngor/main/media/{selected_file}"
    
    # 4. Armar el mensaje con las direcciones
    text = f"""🚨 Help Cuban Families Survive the Crisis 🇨🇺

The blockade makes traditional international transfers almost impossible. We rely on decentralized money to deliver food, medicine, and shelter directly to those in need.

Every sat and every fraction of a coin helps. If you want to support, here are our official addresses:

₿ BTC: bc1qt3rukpe7qp737zj5j5xpxxmcqv90cfefhg5e00
Ξ ETH: 0xA5E6eB31868A85127B1ED82b8C760193356206ED
Ł LTC: LcwAfm4xeJt5sHHVHAGN4qfiv7ruYKzqTe
⚡ Lightning: olivinepug15@primal.net

🎯 Zap Goal: 1,000,000 sats
📸 Evidence ({idx+1}/{len(files)}):
{media_url}

#Cuba #Bitcoin #Crypto #Solidarity #Zaps"""
    
    tags = [["t", "cuba"], ["t", "bitcoin"], ["t", "crypto"], ["t", "solidarity"]]
    if state.get("goal_id"):
        tags.append(["goal", state["goal_id"]])
        
    ev = make_event(sk, text, kind=1, tags=tags)
    
    print(f"📢 Publicando evidencia {idx+1}/{len(files)}: {selected_file}")
    results = await asyncio.gather(*[send(r, ev) for r in RELAYS])
    
    if any(results):
        # 5. Guardar el estado para que la próxima semana publique la siguiente
        state["current_index"] = idx + 1
        save_state(state)
        print("✅ Publicado correctamente. Próxima semana toca otro archivo.")
    else:
        print("❌ No se pudo publicar en ningún relay.")

if __name__ == "__main__":
    asyncio.run(main())
