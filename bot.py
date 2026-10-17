import hashlib, json, time, os, sys, secrets, asyncio, re
import websockets

# ==================== CONFIGURACIÓN ====================
# La meta de 1,000,000 sats (en milisats)
GOAL_AMOUNT_MSATS = 1000000000 
TITLE = "Direct Relief for Cuba: Food, Medicine & Dignity"
DESCRIPTION = """The economic crisis in Cuba has pushed vulnerable families, especially children and the elderly, to the brink. Famine, a lack of basic medicines, and deteriorating housing are our daily reality.

Why Bitcoin and Nostr? Traditional aid is often blocked or delayed. We use NIP-75 Zap Goals to create a direct, peer-to-peer channel. No banks, no middlemen, no censorship.

Every sat raised will be strictly allocated to:
1. Food & Nutrition for families facing famine.
2. Medicine & Health for local clinics.
3. Dignified Housing materials.

Because this is a Zap Goal, funds go directly to my Lightning wallet. Your support is a lifeline. Let's prove that decentralized solidarity works."""

# Aquí pondrás las URLs de tus fotos/videos después de subirlos a GitHub
MEDIA_URLS = [
    # "https://raw.githubusercontent.com/alfrexo95/FondosAngor/main/media/foto1.jpg",
    # "https://raw.githubusercontent.com/alfrexo95/FondosAngor/main/media/video1.mp4"
]

RELAYS = [
    "wss://relay.primal.net",
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.snort.social",
]
# =======================================================

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

async def main():
    nsec = os.environ.get("NOSTR_NSEC", "").strip()
    if not nsec:
        print("❌ Falta el secreto NOSTR_NSEC en GitHub Actions")
        return
    sk = nsec_to_hex(nsec)
    
    # 1. Crear y publicar el Zap Goal (Kind 9041)
    goal_tags = [
        ["relays"] + RELAYS,
        ["amount", str(GOAL_AMOUNT_MSATS)],
        ["summary", TITLE]
    ]
    goal_ev = make_event(sk, DESCRIPTION, kind=9041, tags=goal_tags)
    
    print("🎯 Publicando el Zap Goal (Kind 9041)...")
    await asyncio.gather(*[send(r, goal_ev) for r in RELAYS])
    
    # 2. Crear y publicar la nota promocional (Kind 1) con fotos/videos
    promo_text = f"🚨 URGENT: {TITLE}\n\n{DESCRIPTION}\n\n"
    
    if MEDIA_URLS:
        promo_text += "📸 Evidence & Media:\n" + "\n".join(MEDIA_URLS) + "\n\n"
        
    promo_text += f"⚡ Goal: {GOAL_AMOUNT_MSATS // 1000:,} sats\nLightning: olivinepug15@primal.net\n\n#Cuba #Bitcoin #Nostr #Zaps #Solidarity"
    
    # Etiquetar el goal para que el cliente lo vincule
    promo_tags = [["t", "cuba"], ["t", "bitcoin"], ["t", "nostr"], ["t", "zaps"]]
    
    promo_ev = make_event(sk, promo_text, kind=1, tags=promo_tags)
    print("📢 Publicando nota promocional (Kind 1) con multimedia...")
    await asyncio.gather(*[send(r, promo_ev) for r in RELAYS])
    
    print("✅ Proceso completado.")

if __name__ == "__main__":
    asyncio.run(main())
