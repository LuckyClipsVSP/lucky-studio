import os
import sys
import json
import time
import shutil
import requests
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
import cloudinary
import cloudinary.uploader
import cloudinary.utils

# -----------------------------------------------------------------------------
# CONFIGURAÇÕES E AMBIENTE NUVEM
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "status.txt")
CLIPS_FILE = os.path.join(BASE_DIR, "clips_prontos.json")

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True
    )

clips_lock = threading.Lock()

def log(msg):
    print(f"[LOG] {msg}")
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            start_time = f.read().split('|')[1]
    except Exception:
        start_time = int(time.time())
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write(f"{msg}|{start_time}")

def save_state(clips):
    with clips_lock:
        try:
            with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                json.dump(clips, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERRO SAVE_STATE]: {e}")

# -----------------------------------------------------------------------------
# EXTRAÇÃO DE MÍDIA VIA PROXY (BURLA O BLOQUEIO DE IP DO YOUTUBE)
# -----------------------------------------------------------------------------
def baixar_trecho_local(youtube_url, start_sec, duracao):
    temp_file = f"/tmp/corte_{start_sec}_{int(time.time())}.mp4"
    if os.path.exists(temp_file):
        os.remove(temp_file)

    # 1. Obter link de streaming via API do Cobalt (Sem necessidade de cookies)
    cobalt_instances = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwi.im/api/json"
    ]
    
    video_url_direto = None
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    
    for instance in cobalt_instances:
        try:
            payload = {"url": youtube_url, "vQuality": "720", "isAudioOnly": False}
            resp = requests.post(instance, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                video_url_direto = data.get("url")
                if video_url_direto:
                    print(f"[PROXY SUCESSO] Link obtido com sucesso!")
                    break
        except Exception as e:
            print(f"[PROXY AVISO {instance}]: {e}")

    # 2. Se obtiver o link direto, recorta com o FFmpeg instantaneamente
    if video_url_direto:
        h, m, s = start_sec // 3600, (start_sec % 3600) // 60, start_sec % 60
        timestamp = f"{h:02d}:{m:02d}:{s:02d}"
        cmd_ffmpeg = [
            "ffmpeg", "-y", "-ss", timestamp, "-i", video_url_direto,
            "-t", str(duracao), "-c", "copy", temp_file
        ]
        try:
            subprocess.run(cmd_ffmpeg, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                return temp_file
        except Exception as e:
            print(f"[FFMPEG ERRO]: {e}")

    # 3. Fallback de contingência caso o proxy falhe
    cmd_ytdlp = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=ios,android",
        "--download-sections", f"*{start_sec}-{start_sec + duracao}",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "--no-check-certificates",
        "-o", temp_file,
        youtube_url
    ]
    try:
        subprocess.run(cmd_ytdlp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    except Exception as e:
        print(f"[YT-DLP ERRO FALLBACK]: {e}")

    return temp_file if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0 else None

# -----------------------------------------------------------------------------
# RENDERIZAÇÃO CLOUDINARY (ESTILO 9:16 + LEGENDAS)
# -----------------------------------------------------------------------------
def renderizar_cloudinary(dados):
    i, corte, video_url = dados
    try:
        duracao = int(corte.get('duration', 30))
        start = int(corte['start'])

        print(f"[Corte {i}] Recortando trecho do YouTube...")
        temp_video_path = baixar_trecho_local(video_url, start, duracao)

        if not temp_video_path:
            _marcar_erro(i, "Bloqueio do YouTube ao extrair vídeo")
            return

        print(f"[Corte {i}] Enviando para o Cloudinary...")
        upload_res = cloudinary.uploader.upload_large(
            temp_video_path,
            resource_type="video",
            folder="viral_shorts",
            overwrite=True
        )
        
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)

        public_id = upload_res.get('public_id')

        titulo_texto = corte['title'].upper().replace(",", "").replace("/", "").replace(":", "")
        legenda_texto = corte['legenda'].upper().replace(",", "").replace("/", "").replace(":", "")

        transformations = [
            {"width": 1080, "height": 1920, "crop": "fill", "gravity": "face"},
            {
                "overlay": {
                    "font_family": "Arial", 
                    "font_size": 42, 
                    "font_weight": "bold", 
                    "text": titulo_texto
                },
                "color": "#00D4FF",
                "gravity": "north",
                "y": 140
            },
            {
                "overlay": {
                    "font_family": "Arial", 
                    "font_size": 48, 
                    "font_weight": "bold", 
                    "text": legenda_texto
                },
                "color": "#FFFF00",
                "gravity": "south",
                "y": 180
            }
        ]

        video_url_final, _ = cloudinary.utils.cloudinary_url(
            public_id,
            resource_type="video",
            format="mp4",
            transformation=transformations,
            secure=True
        )

        with clips_lock:
            try:
                with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                    clips_status = json.load(f)
                clips_status[i].update({"url": video_url_final, "status": "pronto"})
                with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                    json.dump(clips_status, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[ERRO ATUALIZAÇÃO STATUS]: {e}")

    except Exception as e:
        print(f"[Corte {i}] EXCEÇÃO NO CLOUDINARY: {e}")
        _marcar_erro(i, str(e))

def _marcar_erro(index, erro_msg):
    with clips_lock:
        try:
            with open(CLIPS_FILE, "r", encoding="utf-8") as f:
                clips_status = json.load(f)
            clips_status[index].update({"status": "erro", "erro": erro_msg})
            with open(CLIPS_FILE, "w", encoding="utf-8") as f:
                json.dump(clips_status, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERRO ATUALIZAÇÃO ERRO]: {e}")

# -----------------------------------------------------------------------------
# CHAMADAS DE INTELIGÊNCIA ARTIFICIAL (GROQ)
# -----------------------------------------------------------------------------
def chamar_ia(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    key = os.environ.get("LLM_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "Responda exclusivamente em JSON puro."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content']
    except Exception:
        pass
    return None

def run():
    if len(sys.argv) < 2:
        return

    video_url = sys.argv[1]

    log("1/4. [Protocolo /Watch] Analisando contexto...")
    prompt_gemini = f"""
    Analise o vídeo do YouTube: {video_url}.
    Identifique os 3 melhores trechos de 30 segundos.
    Responda APENAS em JSON puro:
    [
      {{"start": 30, "duration": 30}},
      {{"start": 90, "duration": 30}},
      {{"start": 150, "duration": 30}}
    
