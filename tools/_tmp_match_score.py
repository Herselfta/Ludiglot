import json
from rapidfuzz import process, fuzz

rest_text = (
    "Perform up to 4 consecutive attacks, dealing Aero DMG. Basic Attack Stage 4 inflicts 1 stack of Aero Erosion upon the target hit. - When the first three stages of Ciaccona's Basic Attack are interrupted by dodging, press Basic Attack in time to resume the attack cycle and cast the corresponding Basic Attack stage. - After Basic Attack Stage 4, Ciaccona starts a Solo Concert. If Ciaccona's Basic Attack Stage 4 or Solo Concert ends early (proactively or being interrupted), an Ensemble Sylph is generated."
)
rest_key = "".join(ch for ch in rest_text.lower() if ch.isalnum())

db = json.load(open("game_text_db.json", encoding="utf-8"))
rest_key_len = len(rest_key)
min_len = int(rest_key_len * 0.5)
max_len = int(rest_key_len * 1.5)

cands = [k for k in db.keys() if min_len <= len(k) <= max_len]
print("len rest_key", rest_key_len, "cands", len(cands))

hits = process.extract(rest_key, cands, scorer=fuzz.token_set_ratio, limit=5)
for k, score, _ in hits:
    print(score, k[:100])
