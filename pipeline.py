import os, sys, json, time, requests, subprocess, threading
from concurrent.futures import ThreadPoolExecutor
import cloudinary, cloudinary.uploader, cloudinary.utils

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")
clips_lock = threading.Lock()

# Configuração Cloudinary
cloudinary.config(cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"), api_key=os.environ.get("CLOUDINARY_API_KEY"), api_secret=os.environ.get("CLOUDINARY_API_SECRET"))

def log(msg):
    with open(STATUS_FILE, "w", encoding="utf-8") as f: f.write(f"{msg}|{int(time.time())}")

def renderizar(dados):
    i, corte, video_url = dados
    temp_file = f"/tmp/corte_{i}.mp4"
    # Proxy de download que NÃO usa yt-dlp (bypassa bloqueios)
    proxy_url = f"https://api.cobalt.tools/api/json"
    try:
        resp = requests.post(proxy_url, json={"url": video_url, "vQuality": "720"}, headers={"Accept": "application/json"}).json()
        direct_url = resp["url"]
        # Recorte via FFmpeg (mais rápido e ignorado pelo YouTube)
        h, m, s = corte['start'] // 3600, (corte['start'] % 3600) // 60, corte['start'] % 60
        subprocess.run(["ffmpeg", "-y", "-ss", f"{h:02d}:{m:02d}:{s:02d}", "-i", direct_url, "-t", "30", "-c", "copy", temp_file], check=True)
        
        upload = cloudinary.uploader.upload_large(temp_file, resource_type="video")
        url, _ = cloudinary.utils.cloudinary_url(upload['public_id'], resource_type="video", format="mp4", transformation=[
            {"width": 1080, "height": 1920, "crop": "fill", "gravity": "face"},
            {"overlay": {"font_family": "Arial", "font_size": 42, "text": corte['title'].upper()}, "color": "#00D4FF", "gravity": "north", "y": 140}
        ])
        with clips_lock:
            with open(CLIPS_FILE, "r+", encoding="utf-8") as f:
                c = json.load(f); c[i].update({"url": url, "status": "pronto"}); f.seek(0); json.dump(c, f, indent=2)
    except Exception as e:
        print(f"Erro: {e}")

def run_wrapper(link):
    log("1/4. Analisando..."); clips = [{"start": 30, "duration": 30, "title": "Corte 1", "status": "renderizando"}, {"start": 90, "duration": 30, "title": "Corte 2", "status": "renderizando"}]
    with open(CLIPS_FILE, "w") as f: json.dump(clips, f)
    log("3/4. Renderizando...")
    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(renderizar, [(i, c, link) for i, c in enumerate(clips)]))
    log("4/4. Concluído!")
