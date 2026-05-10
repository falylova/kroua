from flask import Flask, jsonify, request
import re
import json

app = Flask(__name__)

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0   # pour éviter le cache pendant les tests
latest_data = {}

def clean_received_json(raw: str) -> str:
    if not raw or len(raw.strip()) < 10:
        return ""

    s = raw.strip()

    # 1. Supprimer tout ce qui est avant le premier '{' 
    start = s.find('{')
    if start != -1:
        s = s[start:]

    # 2. Supprimer tout ce qui est après le dernier '}'
    end = s.rfind('}')
    if end != -1:
        s = s[:end+1]

    # 3. Nettoyage agressif des caractères corrompus
    s = re.sub(r'[\x00-\x1F\x7F-\x9F⸮�]', '', s)        # caractères de contrôle + ⸮
    s = re.sub(r'[^ -~]', '', s)                         # garder seulement ASCII imprimable

    # 4. Corrections spécifiques observées dans tes logs
    s = s.replace('2lm', 'lm')
    s = s.replace('dist2:', '"dist":')
    s = s.replace('"dROIT"', '"DROIT"')
    s = s.replace('dROIT', 'DROIT')
    s = s.replace('"IT","stab"', '"pos":"DROIT","stab"')

    # 5. Ajouter des guillemets autour des clés si elles n'en ont pas
    s = re.sub(r'(?<!["\w])(\b\w+\b)\s*:', r'"\1":', s)

    # 6. Nettoyer les virgules en trop
    s = re.sub(r',\s*}', '}', s)
    s = re.sub(r'{\s*,', '{', s)

    # 7. Dernier nettoyage (espace en trop)
    s = re.sub(r'\s+', ' ', s).strip()

    return s
@app.route('/api/esp', methods=['POST'])
def esp():
    global latest_data

    raw = request.get_data(as_text=True)   # Récupère le body brut en string
    print("RECU BRUT:", repr(raw))         # Très utile pour debug

    cleaned = clean_received_json(raw)

    if not cleaned:
        print("→ JSON irrécupérable après nettoyage")
        return jsonify({"status": "error", "reason": "invalid json"}), 400

    try:
        d = json.loads(cleaned)
        print("JSON nettoyé et valide:", d)
    except json.JSONDecodeError as e:
        print("ERREUR JSON même après nettoyage:", e)
        return jsonify({"status": "error", "reason": "json decode failed"}), 400

    # === Le reste de ton code ===
    latest_data = {
        "dist": d.get("dist", 0),
        "t_dht": d.get("temp", 0),
        "hum": d.get("hum", 0),
        "lm": d.get("lm", 0),
        "ldr": d.get("ldr", 0),
        "ir": d.get("ir", 0),
        "pos": d.get("pos", "DROIT"),
        "mvt": d.get("stab", "STABLE"),   # attention : tu utilises "stab" côté ESP
    }

    latest_data["dist_pct"] = dist_to_pct(latest_data["dist"])
    latest_data["hum_interp"] = interpret_hum(latest_data["hum"])
    latest_data["ldr_interp"] = interpret_ldr(latest_data["ldr"])
    latest_data["fire_pct"] = estimation_incendie(
        latest_data["t_dht"], latest_data["lm"],
        latest_data["ir"], latest_data["ldr"]
    )

    return jsonify({"status": "ok"})
# ─────────────────────────────────────────────────────────────
#  Logique capteurs (identique au .ino)
# ─────────────────────────────────────────────────────────────
def interpret_ldr(v):
    if v <= 100: return "Noir"
    if v <= 250: return "Tres sombre"
    if v <= 400: return "Sombre"
    if v <= 550: return "Normal"
    if v <= 700: return "Moyen"
    if v <= 850: return "Lumineux"
    if v <= 950: return "Tres lumineux"
    return "Extreme"

def interpret_hum(h):
    if h < 30: return "Tres sec"
    if h < 50: return "Sec"
    if h < 70: return "moyenne"
    if h < 85: return "Humide"
    return "Tres humide"

def dist_to_pct(d):
    if d < 4:   return 100
    if d >= 16: return 0
    return max(0, min(100, round((16 - d) / 12 * 100)))

def estimation_incendie(t_dht, lm, ir, ldr):
    score = 0
    if t_dht > 50:   score += 40
    elif t_dht > 35: score += 20
    elif t_dht > 28: score += 10
    if lm > 50:      score += 20
    elif lm > 35:    score += 10
    if ir > 70:      score += 20
    elif ir > 40:    score += 10
    if ldr > 900:    score += 20
    elif ldr > 700:  score += 10
    return max(0, min(100, score))

# ─────────────────────────────────────────────────────────────
#  Route API
# ─────────────────────────────────────────────────────────────
@app.route('/api/data')
def api_data():
    return jsonify(latest_data)
# ─────────────────────────────────────────────────────────────
#  Page HTML (tout embarqué)
# ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Koua — Madagascar Nosy Maintso</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=Playfair+Display:wght@500;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{
  --g0:#f2f8ed;--g1:#d4ebc8;--g2:#7ec66b;--g3:#4a8c3f;
  --g4:#3b6d11;--g5:#27500a;
  --text:#1a2e0f;--muted:#4a6040;--faint:#8aaa7a;
  --white:#fff;--rad:18px;--rad-sm:10px;
}
body{
  font-family:'DM Sans',sans-serif;
  background:var(--g0);
  min-height:100vh;
  display:flex;
  color:var(--text);
  overflow:hidden;
}

/* ── BG DÉCO ── */
body::before,body::after{
  content:'';position:fixed;border-radius:50%;pointer-events:none;z-index:0;
}
body::before{
  width:380px;height:380px;top:-100px;right:-80px;
  background:radial-gradient(circle,rgba(126,198,107,.22),transparent 70%);
}
body::after{
  width:260px;height:260px;bottom:-70px;left:160px;
  background:radial-gradient(circle,rgba(74,140,63,.13),transparent 70%);
}

/* ── SIDEBAR ── */
.sidebar{
  width:220px;min-width:220px;height:100vh;
  background:linear-gradient(180deg,#1a3318 0%,#0f2410 100%);
  display:flex;flex-direction:column;align-items:center;
  padding:2rem 0 1.5rem;
  position:relative;z-index:2;
  box-shadow:4px 0 20px rgba(0,0,0,.15);
}
/* feuilles déco sidebar */
.sidebar::before{
  content:'';position:absolute;bottom:0;right:0;
  width:100px;height:160px;
  background:radial-gradient(ellipse at bottom right,rgba(74,140,63,.18),transparent 70%);
  pointer-events:none;
}
.brand{display:flex;flex-direction:column;align-items:center;gap:10px;margin-bottom:2.5rem;}
.brand-logo{
  width:58px;height:58px;border-radius:50%;overflow:hidden;
  border:2px solid rgba(126,198,107,.35);
  box-shadow:0 0 20px rgba(74,140,63,.3);
}
/* ── LOGO PHOTO ── */.brand-logo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  filter: brightness(1.05);   /* légèrement plus lumineux */
}
.brand-name{
  font-family:'Playfair Display',serif;
  font-size:1.2rem;font-weight:700;color:#c8e6c2;
  letter-spacing:.04em;
}
.brand-sub{font-size:11px;color:rgba(200,230,194,.45);letter-spacing:.08em;text-align:center;line-height:1.4;}

.nav{width:100%;flex:1;}
.nav-btn{
  display:flex;align-items:center;gap:10px;
  width:100%;padding:.75rem 1.4rem;
  background:none;border:none;cursor:pointer;
  font-family:'DM Sans',sans-serif;font-size:13px;font-weight:400;
  color:rgba(200,230,194,.55);
  border-left:2.5px solid transparent;
  transition:all .18s;text-align:left;
}
.nav-btn .icon{font-size:16px;width:20px;text-align:center;}
.nav-btn:hover{color:rgba(200,230,194,.85);background:rgba(126,198,107,.06);}
.nav-btn.active{
  color:#c8e6c2;font-weight:500;
  border-left-color:#7ec66b;
  background:rgba(126,198,107,.1);
}
.nav-btn.sos{color:rgba(252,146,146,.6);}
.nav-btn.sos.active{color:#f09595;border-left-color:#e24b4a;background:rgba(226,75,74,.08);}

.sidebar-footer{
  font-size:11px;color:rgba(200,230,194,.2);text-align:center;padding:0 1rem;
}

/* ── MAIN ── */
.main{
  flex:1;display:flex;flex-direction:column;
  height:100vh;overflow:hidden;position:relative;z-index:1;
}

.topbar{
  padding:1.2rem 2rem;
  background:rgba(242,248,237,.85);
  backdrop-filter:blur(8px);
  border-bottom:1px solid var(--g1);
  display:flex;align-items:flex-start;justify-content:space-between;
  flex-shrink:0;
}
.topbar-title{
  font-family:'Playfair Display',serif;
  font-size:1.5rem;font-weight:700;color:var(--text);line-height:1.1;
}
.topbar-sub{font-size:12px;color:var(--muted);margin-top:3px;}
.live-badge{
  display:flex;align-items:center;gap:6px;
  background:rgba(74,140,63,.1);border:1px solid rgba(74,140,63,.2);
  border-radius:20px;padding:4px 12px;
  font-size:12px;color:var(--g4);font-weight:500;
}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--g3);animation:pulse 1.5s infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.3)}}

.content{flex:1;overflow-y:auto;padding:2rem;}
.content::-webkit-scrollbar{width:4px;}
.content::-webkit-scrollbar-thumb{background:var(--g1);border-radius:4px;}

/* ── PANELS ── */
.panel{display:none;}
.panel.active{display:block;}

/* ── CARDS ── */
.card{
  background:rgba(255,255,255,.82);
  border:1px solid var(--g1);border-radius:var(--rad);
  padding:1.75rem;
  backdrop-filter:blur(4px);
  box-shadow:0 2px 12px rgba(59,109,17,.06);
}
.card+.card{margin-top:1rem;}
.card-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;}
.card.full{grid-column:1/-1;}
.card.mini{padding:1.1rem 1.25rem;}

.big-num{
  font-size:60px;font-weight:400;color:var(--text);
  line-height:1;margin-bottom:4px;letter-spacing:-.02em;
}
.big-label{font-size:13px;color:var(--muted);margin-bottom:1.5rem;}

.mini-lbl{
  font-size:10px;text-transform:uppercase;letter-spacing:.1em;
  color:var(--faint);margin-bottom:5px;
}
.mini-val{font-size:24px;font-weight:500;color:var(--text);}
.mini-int{font-size:12px;color:var(--muted);margin-top:2px;}

/* BAR */
.bar-wrap{height:8px;background:var(--g1);border-radius:4px;overflow:hidden;margin-bottom:1.25rem;}
.bar-wrap.sm{height:5px;margin-top:8px;margin-bottom:0;}
.bar-fill{height:100%;border-radius:4px;background:var(--g3);transition:width .5s ease;}
.bar-fill.warn{background:#ba7517;}
.bar-fill.danger{background:#e24b4a;}

/* BADGE */
.badge{
  display:inline-flex;align-items:center;
  padding:4px 14px;border-radius:20px;
  font-size:12px;font-weight:500;
  background:rgba(74,140,63,.1);color:var(--g4);
  margin-bottom:1.25rem;
}
.badge.warn{background:#faeeda;color:#633806;}
.badge.danger{background:#fcebeb;color:#791f1f;}

/* PILL */
.pill{
  display:inline-block;padding:3px 10px;border-radius:20px;
  font-size:11px;font-weight:500;margin-top:6px;
  background:rgba(74,140,63,.1);color:var(--g4);
}
.pill.warn{background:#faeeda;color:#633806;}
.pill.danger{background:#fcebeb;color:#791f1f;}

/* SEP */
.sep{height:1px;background:var(--g1);margin:1.25rem 0;}

/* COUNTDOWN */
.cd-box{
  background:var(--g0);border:1px solid var(--g1);
  border-radius:var(--rad-sm);padding:1rem 1.25rem;
  display:flex;align-items:center;justify-content:space-between;
}
.cd-lbl{font-size:11px;color:var(--faint);}
.cd-time{font-size:26px;font-weight:500;color:var(--text);font-variant-numeric:tabular-nums;}
.sub-info{font-size:12px;color:var(--faint);margin-top:10px;}
.desc-text{font-size:13px;color:var(--muted);line-height:1.65;}

/* FIRE RING */
.fire-wrap{display:flex;align-items:center;gap:1.5rem;}
.fire-ring{position:relative;flex-shrink:0;}
.fire-inner{
  position:absolute;inset:0;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  font-size:18px;font-weight:500;color:var(--text);
}
.fire-sub{font-size:10px;color:var(--faint);}
</style>
</head>
<body>

<!-- ══ SIDEBAR ══════════════════════════════════════ -->
<aside class="sidebar">
<div class="brand">
  <div class="brand-logo">
    <img src="/static/image.jpg">
  </div>

  <div class="brand-name">Koua</div>
  <div class="brand-sub">
    Groupe Independant<br>
    Madagasikara ho Nosy Maintso indray
  </div>
</div>

  <nav class="nav">
    <button class="nav-btn active" data-panel="graine">
      <span class="icon">🌱</span> Niveau graine
    </button>
    <button class="nav-btn" data-panel="ir">
      <span class="icon">🌡️</span> IR &amp; Temp.
    </button>
    <button class="nav-btn" data-panel="hum">
      <span class="icon">💧</span> Humidité
    </button>
    <button class="nav-btn" data-panel="stabili">
      <span class="icon">📍</span> Stabilité
    </button>
    <button class="nav-btn" data-panel="ldr">
      <span class="icon">☀️</span> Luminosité
    </button>
    <button class="nav-btn sos" data-panel="sos">
      <span class="icon">🔥</span> SOS Incendie
    </button>
  </nav>

  <div class="sidebar-footer">Arduino · Serial 9600</div>
</aside>

<!-- ══ MAIN ══════════════════════════════════════════ -->
<div class="main">
  <div class="topbar">
    <div>
      <div class="topbar-title" id="panel-title">Niveau de graine</div>
      <div class="topbar-sub">Madagascar — Nosy Maintso · Groupe Koua</div>
    </div>
    <div class="live-badge"><span class="live-dot"></span> Live</div>
  </div>

  <div class="content">

    <!-- GRAINE (BTN_ON) -->
    <div id="panel-graine" class="panel active">
      <div class="card">
        <div class="big-num" id="g-pct">—</div>
        <div class="big-label">Niveau de graine (distance → %)</div>
        <div class="bar-wrap"><div class="bar-fill" id="g-bar" style="width:0%"></div></div>
        <span class="badge" id="g-badge">—</span>
        <div class="sep"></div>
        <div class="cd-box">
          <div>
            <div class="cd-lbl">Prochain lancement de graine</div>
            <div class="cd-time" id="g-timer">05:00</div>
          </div>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="9" stroke="#3b6d11" stroke-width="1.5"/>
            <path d="M12 7v5l3 3" stroke="#3b6d11" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="sub-info">Distance capteur : <span id="g-dist">—</span> cm</div>
      </div>
    </div>

    <!-- IR & TEMP (BTN_OFF) -->
    <div id="panel-ir" class="panel">
      <div class="card-grid">
        <div class="card mini">
          <div class="mini-lbl">Capteur IR</div>
          <div class="mini-val" id="ir-val">—</div>
          <div class="mini-int" id="ir-int">—</div>
        </div>
        <div class="card mini">
          <div class="mini-lbl">Température DHT</div>
          <div class="mini-val" id="t-val">—</div>
          <div class="mini-int" id="t-int">—</div>
        </div>
        <div class="card mini full">
          <div class="mini-lbl">LM35 — Sonde sol</div>
          <div class="mini-val" id="lm-val">—</div>
          <div class="bar-wrap sm"><div class="bar-fill" id="lm-bar" style="width:0%"></div></div>
        </div>
      </div>
    </div>

    <!-- HUMIDITE (MODE1) -->
    <div id="panel-hum" class="panel">
      <div class="card">
        <div class="big-num" id="h-val">—</div>
        <div class="big-label">Humidité relative (%)</div>
        <div class="bar-wrap"><div class="bar-fill" id="h-bar" style="width:0%"></div></div>
        <span class="badge" id="h-badge">—</span>
        <div class="sep"></div>
        <p class="desc-text" id="h-desc">—</p>
      </div>
    </div>

    <!-- STABILITE (MODE2) -->
    <div id="panel-stabili" class="panel">
      <div class="card-grid">
        <div class="card mini">
          <div class="mini-lbl">Mouvement (MVT)</div>
          <div class="mini-val" id="mvt-val">—</div>
          <span class="pill" id="mvt-pill">—</span>
        </div>
        <div class="card mini">
          <div class="mini-lbl">Position (POS)</div>
          <div class="mini-val" id="pos-val">—</div>
          <span class="pill" id="pos-pill">—</span>
        </div>
        <div class="card mini full">
          <p class="desc-text" id="stab-desc">—</p>
        </div>
      </div>
    </div>

    <!-- LDR (MODE3) -->
    <div id="panel-ldr" class="panel">
      <div class="card">
        <div class="big-num" id="ldr-val">—</div>
        <div class="big-label">Luminosité LDR (0 – 1023)</div>
        <div class="bar-wrap"><div class="bar-fill" id="ldr-bar" style="width:0%"></div></div>
        <span class="badge" id="ldr-badge">—</span>
        <div class="sep"></div>
        <p class="desc-text" id="ldr-desc">—</p>
      </div>
    </div>

    <!-- SOS INCENDIE -->
    <div id="panel-sos" class="panel">
      <div class="card">
        <div class="fire-wrap">
          <div class="fire-ring">
            <svg viewBox="0 0 90 90" width="100" height="100">
              <circle cx="45" cy="45" r="36" fill="none" stroke="#d4ebc8" stroke-width="8"/>
              <circle id="fire-arc" cx="45" cy="45" r="36" fill="none" stroke="#3b6d11"
                stroke-width="8" stroke-dasharray="226" stroke-dashoffset="185"
                stroke-linecap="round" transform="rotate(-90 45 45)"/>
            </svg>
            <div class="fire-inner">
              <span id="fire-pct">—</span>
              <span class="fire-sub">risque</span>
            </div>
          </div>
          <div>
            <span class="badge" id="fire-badge">—</span>
            <p class="desc-text" id="fire-desc" style="margin-top:6px">—</p>
          </div>
        </div>
        <div class="sep"></div>
        <div class="card-grid">
          <div class="card mini"><div class="mini-lbl">Temp. DHT</div><div class="mini-val" id="fs-temp">—</div></div>
          <div class="card mini"><div class="mini-lbl">LM35</div><div class="mini-val" id="fs-lm">—</div></div>
          <div class="card mini"><div class="mini-lbl">Capteur IR</div><div class="mini-val" id="fs-ir">—</div></div>
          <div class="card mini"><div class="mini-lbl">LDR</div><div class="mini-val" id="fs-ldr">—</div></div>
        </div>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<script>
// ── Navigation ───────────────────────────────────────────────
const TITLES = {
  graine:'Niveau de graine', ir:'IR & Température',
  hum:'Humidité', stabili:'Stabilité',
  ldr:'Luminosité LDR', sos:'SOS Incendie'
};
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.panel).classList.add('active');
    document.getElementById('panel-title').textContent = TITLES[btn.dataset.panel];
  });
});

// ── Compte à rebours ─────────────────────────────────────────
let cd = 300;
function startTimer() {
  clearInterval(window._ti);
  cd = 300;
  window._ti = setInterval(() => {
    cd = Math.max(0, cd - 1);
    const m = String(Math.floor(cd/60)).padStart(2,'0');
    const s = String(cd%60).padStart(2,'0');
    document.getElementById('g-timer').textContent = m+':'+s;
    if (cd === 0) { document.getElementById('g-timer').textContent='Lancement !'; setTimeout(startTimer,2000); }
  }, 1000);
}
startTimer();

// ── Helpers ──────────────────────────────────────────────────
const $ = id => document.getElementById(id);
function setBadge(id, txt, cls='') {
  $(id).textContent = txt;
  $(id).className = 'badge' + (cls ? ' '+cls : '');
}
function setPill(id, txt, cls='') {
  $(id).textContent = txt;
  $(id).className = 'pill' + (cls ? ' '+cls : '');
}
function setBar(id, pct, cls='') {
  $(id).style.width = pct + '%';
  $(id).className = 'bar-fill' + (cls ? ' '+cls : '');
}

function graineBadge(p) {
  if (p>=100) return ['Trop plein !','danger'];
  if (p>=80)  return ['Niveau haut',''];
  if (p>=40)  return ['Bon niveau',''];
  if (p>=15)  return ['Niveau bas','warn'];
  return ['Presque vide !','danger'];
}
function humDesc(h) {
  if (h<30) return "Air très sec. Risque de déshydratation des plantes.";
  if (h<50) return "Humidité basse. Surveiller l'arrosage.";
  if (h<70) return "Humidité optimale pour la forêt. Pas d'action requise.";
  if (h<85) return "Humidité élevée. Conditions favorables à la végétation.";
  return "Humidité très élevée. Risque de moisissures.";
}

// ── Fetch & update ───────────────────────────────────────────
async function fetchData() {
  try {
    const d = await fetch('/api/data').then(r=>r.json());

    // Graine
    $('g-pct').textContent = d.dist_pct+'%';
    $('g-dist').textContent = d.dist;
    const [gb_txt, gb_cls] = graineBadge(d.dist_pct);
    setBar('g-bar', d.dist_pct, d.dist_pct>=40?'':d.dist_pct>=15?'warn':'danger');
    setBadge('g-badge', gb_txt, gb_cls);

    // IR & Temp
    $('ir-val').textContent = d.ir+'%';
    $('ir-int').textContent = d.ir>70?'Réflexion forte':d.ir>40?'Réflexion moyenne':'Réflexion basse';
    $('t-val').textContent  = d.t_dht+'°C';
    $('t-int').textContent  = d.t_dht>35?'Chaud':d.t_dht>28?'Tiède':'Normal';
    $('lm-val').textContent = d.lm+'°C';
    $('lm-bar').style.width = Math.round(d.lm/60*100)+'%';

    // Humidité
    $('h-val').textContent = d.hum+'%';
    setBar('h-bar', d.hum);
    setBadge('h-badge', d.hum_interp, d.hum<30||d.hum>=85?'warn':'');
    $('h-desc').textContent = humDesc(d.hum);

    // Stabilité
    $('mvt-val').textContent = d.mvt;
    setPill('mvt-pill', d.mvt==='SECOUE'?'Secousse !':"Pas de secousse", d.mvt==='SECOUE'?'danger':'');
    $('pos-val').textContent = d.pos;
    const pos_cls = d.pos==='DROIT'?'':d.pos==='INCLINE'?'warn':'danger';
    const pos_txt = d.pos==='DROIT'?'Orientation correcte':d.pos==='INCLINE'?'Incliné':'Retourné !';
    setPill('pos-pill', pos_txt, pos_cls);
    $('stab-desc').textContent = d.mvt==='SECOUE'?'Attention : secousse détectée !':
      d.pos!=='DROIT'?'Position anormale — vérifiez le dispositif.':
      'Le dispositif est stable et en position correcte.';

    // LDR
    $('ldr-val').textContent = d.ldr;
    setBar('ldr-bar', Math.round(d.ldr/1023*100), d.ldr>850?'warn':'');
    setBadge('ldr-badge', d.ldr_interp, d.ldr>850?'warn':'');
    $('ldr-desc').textContent = d.ldr>850?'Lumière très intense — possible flamme à proximité.':
      d.ldr<250?'Environnement très sombre.':"Niveau de lumière normal pour une forêt en journée.";

    // SOS
    const fp = d.fire_pct;
    const arc = $('fire-arc');
    arc.setAttribute('stroke-dashoffset', String(Math.round(226-(fp/100)*226)));
    arc.setAttribute('stroke', fp>=70?'#e24b4a':fp>=40?'#ba7517':'#3b6d11');
    $('fire-pct').textContent = fp+'%';
    setBadge('fire-badge', fp>=70?'Risque élevé !':fp>=40?'Risque modéré':'Faible risque',
             fp>=70?'danger':fp>=40?'warn':'');
    $('fire-desc').textContent = fp>=70?'ALERTE — Conditions suspectes. Vérifiez immédiatement.':
      fp>=40?'Attention — Surveillance accrue recommandée.':
      'Conditions normales. Forêt humide, faible risque.';
    $('fs-temp').textContent = d.t_dht+'°C';
    $('fs-lm').textContent   = d.lm+'°C';
    $('fs-ir').textContent   = d.ir+'%';
    $('fs-ldr').textContent  = d.ldr;

  } catch(e) { console.error('API error:', e); }
}

fetchData();
setInterval(fetchData, 2500);
</script>
</body>
</html>"""

@app.route('/')
def index():
    return HTML

if __name__ == '__main__':
    print("=" * 50)
    print("  Koua — Madagascar Nosy Maintso")
    print("  Ouvrir : http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)