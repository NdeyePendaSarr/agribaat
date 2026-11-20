"""Démo automatique : joue le scénario de GUIDE_DEMO.md tout seul dans Chrome.

Deux usages :
1. Vidéo de secours avec le son : lancer l'app (python app.py), puis
       python demo_auto.py
   Une fenêtre Chrome s'ouvre et déroule la démo. Pendant ce temps, enregistrer
   l'écran avec la Xbox Game Bar de Windows (Win + Alt + R pour démarrer et arrêter ;
   la vidéo arrive dans Vidéos\\Captures) ou avec OBS / l'enregistreur d'Ubuntu.
   Ou, sans outil externe : python demo_auto.py --filmer : Chrome filme lui-même
   l'onglet, son compris, et écrit outputs/demo_agribaat.webm (lisible dans Chrome,
   le Lecteur multimédia de Windows ou VLC).
2. Démo de secours hors ligne, sans rien enregistrer :
       python demo_auto.py --headless
   produit outputs/demo_secours.html : les écrans de la démo et les vraies réponses
   vocales, qui s'enchaînent tout seuls dans n'importe quel navigateur (sans internet).

Le script ne fait que cliquer dans l'app comme le ferait un présentateur.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from websockets.sync.client import connect

import config

APP_URL = "http://127.0.0.1:7860/?__theme=light"
PORT = 9333
OUT = config.APP_DIR / "outputs" / "demo_secours.html"
VIDEO = config.APP_DIR / "outputs" / "demo_agribaat.webm"

# (titre affiché, action, argument)
SCENARIO = [
    ("AgriBaat — assistant agricole vocal en wolof, pulaar et sereer", "home", None),
    ("1. Question en français : le prix du mil à Kaolack", "example", "Prix du mil à Kaolack"),
    ("2. La même question posée en wolof", "example", "njëg dugub ci Kaolack"),
    ("3. Conseil de variété (Catalogue CEDEAO)", "example", "Variété de mil à cycle court"),
    ("4. Pluie à Mbour (bulletin ANACIM)", "example", "Pluie à Mbour"),
    ("5. Quand récolter l'arachide ? (recommandation ANACIM)", "example",
     "Quand récolter l'arachide ?"),
    ("6. En pulaar : le prix du mil à Kaolack", "example", "coggu gawri e Kawlak"),
    ("7. En sereer, à l'écrit : la pluie à Mbour", "sereer", "ndoɓ no Mbour"),
    ("8. Météo en direct : prévisions à 7 jours et conseil dans la langue", "tab",
     "Météo en direct"),
    ("9. Climat : quoi cultiver dans chaque région pour un fort rendement", "tab",
     "Climat & cultures"),
    ("10. Prix des marchés : prix moyen, marché le moins cher et le plus cher", "tab",
     "Prix des marchés"),
    ("11. Production : évolution nationale et par région", "tab", "Production"),
    ("12. Conseils : variétés et pluies ANACIM", "tab", "Conseils"),
    ("13. À propos : sources officielles, aucun chiffre inventé", "tab", "À propos"),
]


# Langue à sélectionner en haut pour chaque question type (français par défaut).
EXAMPLE_LANG = {"njëg dugub ci Kaolack": "Wolof", "coggu gawri e Kawlak": "Pulaar"}


def find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        shutil.which("google-chrome") or "", shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    sys.exit("Chrome introuvable : indiquez son chemin dans la variable CHROME.")


class Browser:
    """Pilotage minimal de Chrome par le protocole DevTools."""

    def __init__(self, headless: bool, film: bool = False) -> None:
        self.profile = tempfile.mkdtemp(prefix="agribaat_demo_")
        args = [find_chrome(), f"--remote-debugging-port={PORT}",
                f"--user-data-dir={self.profile}", "--no-first-run",
                "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required",
                "--window-size=1366,900", "--window-position=0,0", "--hide-crash-restore-bubble",
                "--disable-features=Translate", "--lang=fr", "--test-type",
                # Fenêtre cachée ou réduite : Chrome continue de dessiner la page, sinon
                # captures d'écran et vidéo se bloquent.
                "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling"]
        if headless:
            args += ["--headless=new", "--mute-audio"]
        else:  # fenêtre « application » : sans barre d'adresse ni onglets
            args += ["--start-maximized", "--app=about:blank"]
        if film:  # filme l'onglet lui-même (image + son), sans boîte de dialogue
            args += ["--auto-accept-this-tab-capture",
                     "--auto-select-tab-capture-source-by-title=AgriBaat"]
        self.proc = subprocess.Popen(args + ([] if not headless else ["about:blank"]),
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(60):
            try:
                pages = httpx.get(f"http://127.0.0.1:{PORT}/json", timeout=1).json()
                ws_url = next(p["webSocketDebuggerUrl"] for p in pages if p["type"] == "page")
                break
            except Exception:  # noqa: BLE001 — Chrome pas encore prêt
                time.sleep(0.5)
        if ws_url is None:
            sys.exit("Chrome n'a pas démarré le mode pilotage.")
        self.ws = connect(ws_url, max_size=None, ping_interval=None)  # Chrome chargé : pas de coupure
        self.n = 0
        if headless:
            self.call("Emulation.setDeviceMetricsOverride",
                      width=1366, height=900, deviceScaleFactor=1, mobile=False)

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            try:
                msg = json.loads(self.ws.recv(timeout=180))
            except TimeoutError:
                sys.exit(f"Chrome ne répond plus depuis 3 minutes ({method}). Ne pas "
                         "réduire ni fermer la fenêtre Chrome pendant la démo, puis relancer.")
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method} : {msg['error']}")
                return msg.get("result", {})

    def js(self, code: str):
        res = self.call("Runtime.evaluate", expression=code, awaitPromise=True,
                        returnByValue=True)
        return res.get("result", {}).get("value")

    def js_gesture(self, code: str):
        """Comme js(), mais compte comme un clic de l'utilisateur (requis pour filmer)."""
        res = self.call("Runtime.evaluate", expression=code, awaitPromise=True,
                        returnByValue=True, userGesture=True)
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"].get("exception", {}).get(
                "description", "erreur JavaScript"))
        return res.get("result", {}).get("value")

    def screenshot(self) -> bytes:
        return base64.b64decode(self.call("Page.captureScreenshot", format="png")["data"])

    def close(self) -> None:
        try:
            self.ws.close()
        finally:
            self.proc.terminate()
            shutil.rmtree(self.profile, ignore_errors=True)


CAPTION_JS = """(t => {
  let c = document.getElementById('demo-caption');
  if (!c) {
    c = document.createElement('div'); c.id = 'demo-caption';
    c.style.cssText = 'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);'
      + 'z-index:99999;background:#14532d;color:#fff;font:600 20px Inter,sans-serif;'
      + 'padding:12px 22px;border-radius:14px;box-shadow:0 6px 24px rgba(0,0,0,.25);'
      + 'max-width:90vw;text-align:center';
    document.body.appendChild(c);
  }
  c.textContent = t;
})(__T__)"""

CLICK_BY_TEXT_JS = """((sel, text) => {
  const el = [...document.querySelectorAll(sel)].find(e => e.innerText.includes(text));
  if (!el) return false;
  el.scrollIntoView({block: 'center'}); el.click(); return true;
})(%s, %s)"""


def wait_for(br: Browser, code: str, timeout: float = 120) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if br.js(code):
            return True
        time.sleep(0.3)
    return False


# Signature de la carte réponse : question posée (data-q) + texte. Deux questions qui
# donnent la même réponse (français puis wolof) ont quand même deux signatures.
ANSWER_SIG = "(a => a ? (a.dataset.q || '') + '|' + a.innerText : '')(document.querySelector('.answer'))"


def answer_text(br: Browser) -> str:
    return br.js(ANSWER_SIG) or ""


def audio_link(br: Browser) -> str | None:
    return br.js("(document.querySelector('#answer-audio a[download]') || {}).href || null")


START_REC_JS = """(async () => {
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: {frameRate: 20, width: 1280, height: 720}, audio: true,
    preferCurrentTab: true, selfBrowserSurface: 'include', systemAudio: 'include'});
  // VP8 d'abord : VP9 sature un PC à 2 cœurs, au point de bloquer la page filmée.
  const type = ['video/webm;codecs=vp8,opus', 'video/webm;codecs=vp9,opus', 'video/webm']
    .find(t => MediaRecorder.isTypeSupported(t));
  window.__chunks = [];
  const rec = new MediaRecorder(stream, {mimeType: type, videoBitsPerSecond: 2500000});
  rec.ondataavailable = e => { if (e.data.size) window.__chunks.push(e.data); };
  rec.start(1000);
  window.__rec = rec; window.__stream = stream;
  return type + ' / pistes son : ' + stream.getAudioTracks().length;
})()"""

STOP_REC_JS = """new Promise(done => {
  window.__rec.onstop = () => {
    window.__stream.getTracks().forEach(t => t.stop());
    window.__blob = new Blob(window.__chunks, {type: 'video/webm'});
    done(window.__blob.size);
  };
  window.__rec.stop();
})"""

SLICE_JS = """new Promise(done => {
  const r = new FileReader();
  r.onload = () => done(r.result.split(',')[1]);
  r.readAsDataURL(window.__blob.slice(%d, %d));
})"""


def save_video(br: Browser) -> None:
    size = br.js(STOP_REC_JS)
    step = 4 * 1024 * 1024
    with VIDEO.open("wb") as f:
        for start in range(0, size, step):
            f.write(base64.b64decode(br.js(SLICE_JS % (start, min(size, start + step)))))
    print(f"Vidéo : {VIDEO} ({size / 1e6:.1f} Mo)")


def run(headless: bool, film: bool = False) -> None:
    br = Browser(headless, film)
    slides = []
    try:
        br.call("Page.enable")
        br.call("Page.navigate", url=APP_URL)
        if not wait_for(br, "!!document.querySelector('.ex-card')", 60):
            sys.exit(f"L'app ne répond pas sur {APP_URL} : lancez d'abord python app.py")
        time.sleep(2)
        if film:
            VIDEO.parent.mkdir(parents=True, exist_ok=True)
            print("● Enregistrement :", br.js_gesture(START_REC_JS))
            time.sleep(1)
        for title, action, arg in SCENARIO:
            print("▶", title)
            br.js(CAPTION_JS.replace("__T__", json.dumps(title)))
            before = answer_text(br)
            audio = None
            if action == "home":
                br.js("window.scrollTo(0, 0)")
                time.sleep(3)
            elif action in ("example", "sereer"):
                br.js(CLICK_BY_TEXT_JS % (json.dumps("button[role=tab]"),
                                          json.dumps("Assistant")))
                time.sleep(0.5)
                if action == "sereer":
                    br.js(CLICK_BY_TEXT_JS % (json.dumps("#lang-toggle label"),
                                              json.dumps("Sereer")))
                    time.sleep(1)
                    br.js("""(t => {
                      const box = document.querySelector('textarea[placeholder^="Ex."]');
                      box.scrollIntoView({block: 'center'});
                      const set = Object.getOwnPropertyDescriptor(
                        HTMLTextAreaElement.prototype, 'value').set;
                      set.call(box, t); box.dispatchEvent(new Event('input', {bubbles: true}));
                    })(%s)""" % json.dumps(arg))
                    time.sleep(1.5)
                    br.js(CLICK_BY_TEXT_JS % (json.dumps("button"), json.dumps("Envoyer")))
                else:
                    lang = EXAMPLE_LANG.get(arg, "Français")
                    br.js(CLICK_BY_TEXT_JS % (json.dumps("#lang-toggle label"), json.dumps(lang)))
                    # Les questions types changent avec la langue : attendre que la carte
                    # voulue soit affichée avant de cliquer.
                    wait_for(br, "[...document.querySelectorAll('button.ex-card')].some("
                                 f"b => b.innerText.includes({json.dumps(arg)}))", 30)
                    time.sleep(0.5)
                    br.js(CLICK_BY_TEXT_JS % (json.dumps("button.ex-card"), json.dumps(arg)))
                wait_for(br, f"(s => s.includes('Français :') && s !== {json.dumps(before)})"
                             f"({ANSWER_SIG})")
                br.js("document.querySelector('.answer').scrollIntoView({block: 'start'});"
                      "window.scrollBy(0, -90)")
                time.sleep(1.5)
                if action == "example":  # réponse vocale (fichier fourni par l'app)
                    # Réponse identique à la précédente (même fichier audio) : l'app ne
                    # la relance pas d'elle-même, on appuie sur lecture.
                    br.js("(b => { if (b && b.getAttribute('aria-label') !== 'Pause') b.click(); })"
                          "(document.querySelector('#answer-audio .play-pause-button'))")
                    link = audio_link(br)
                    if link:
                        audio = httpx.get(link, timeout=30).content
            elif action == "tab":
                br.js(CLICK_BY_TEXT_JS % (json.dumps("button[role=tab]"), json.dumps(arg)))
                time.sleep(4)
                br.js("window.scrollTo(0, 0)")
                time.sleep(1)
            shot = br.screenshot()
            duration = _duration(audio) if audio else 0
            slides.append({"title": title, "png": shot, "audio": audio})
            # Laisse le temps d'écouter la réponse (fenêtre visible) ou de lire l'écran.
            time.sleep((duration + 2) if not headless and audio else (1 if headless else 5))
        br.js(CLICK_BY_TEXT_JS % (json.dumps("#lang-toggle label"), json.dumps("Wolof")))
        br.js(CAPTION_JS.replace(
            "__T__", json.dumps("AgriBaat — équipe SMART AGRO · PAS Challenge 2026")))
        if not headless:
            time.sleep(4)
        if film:
            save_video(br)
    finally:
        br.close()
    build_html(slides)


def _duration(wav: bytes) -> float:
    import soundfile as sf

    try:
        info = sf.info(io.BytesIO(wav))
        return info.frames / info.samplerate
    except Exception:  # noqa: BLE001
        return 0


def build_html(slides: list[dict]) -> None:
    from PIL import Image

    items = []
    for s in slides:
        buf = io.BytesIO()
        Image.open(io.BytesIO(s["png"])).convert("RGB").save(buf, "JPEG", quality=82)
        items.append({"title": s["title"],
                      "img": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
                      "audio": ("data:audio/wav;base64," + base64.b64encode(s["audio"]).decode())
                      if s["audio"] else None})
    html = PLAYER.replace("__SLIDES__", json.dumps(items))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Démo de secours : {OUT} ({OUT.stat().st_size // 1024} Ko, {len(items)} écrans)")


PLAYER = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgriBaat — démo</title><style>
body{margin:0;background:#0f1a12;color:#fff;font:16px Inter,system-ui,sans-serif;
display:flex;flex-direction:column;align-items:center;min-height:100vh}
#cap{font-weight:700;font-size:20px;padding:14px 18px;text-align:center}
#img{max-width:100vw;max-height:calc(100vh - 130px);border-radius:10px;
box-shadow:0 8px 30px rgba(0,0,0,.5)}
#bar{display:flex;gap:10px;align-items:center;padding:12px}
button{background:#16a34a;color:#fff;border:0;border-radius:10px;padding:10px 18px;
font:600 15px inherit;cursor:pointer}button.sec{background:#334155}
#n{opacity:.7;min-width:60px;text-align:center}
</style></head><body>
<div id="cap">AgriBaat — démo de secours</div><img id="img" alt="">
<div id="bar"><button class="sec" id="prev">◀</button><button id="play">▶ Lancer la démo</button>
<span id="n"></span><button class="sec" id="next">▶</button></div>
<audio id="aud"></audio>
<script>
const S = __SLIDES__; let i = 0, auto = false, timer = null;
const img = document.getElementById('img'), cap = document.getElementById('cap'),
  aud = document.getElementById('aud'), n = document.getElementById('n');
function show(k) {
  clearTimeout(timer); aud.pause(); i = Math.max(0, Math.min(S.length - 1, k));
  img.src = S[i].img; cap.textContent = S[i].title; n.textContent = (i + 1) + ' / ' + S.length;
  if (!auto) return;
  if (S[i].audio) { aud.src = S[i].audio; aud.play();
    aud.onended = () => { timer = setTimeout(() => step(), 1500); }; }
  else timer = setTimeout(() => step(), 5000);
}
function step() { if (i < S.length - 1) show(i + 1); else { auto = false; play.textContent = '↻ Rejouer'; } }
const play = document.getElementById('play');
play.onclick = () => { auto = true; play.textContent = '⏸ En cours'; show(play.textContent && i === S.length - 1 ? 0 : i); };
document.getElementById('prev').onclick = () => show(i - 1);
document.getElementById('next').onclick = () => show(i + 1);
document.addEventListener('keydown', e => { if (e.key === 'ArrowRight') show(i + 1);
  if (e.key === 'ArrowLeft') show(i - 1); if (e.key === ' ') play.click(); });
show(0);
</script></body></html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true",
                        help="sans fenêtre : produit seulement outputs/demo_secours.html")
    parser.add_argument("--filmer", action="store_true",
                        help="filme la démo (son compris) dans outputs/demo_agribaat.webm")
    args = parser.parse_args()
    if args.headless and args.filmer:
        sys.exit("--filmer a besoin d'une fenêtre visible (le son est coupé en --headless).")
    run(args.headless, args.filmer)
