import os, json, time, requests, subprocess, threading
from concurrent.futures import ThreadPoolExecutor
import cloudinary, cloudinary.uploader, cloudinary.utils

CLIPS_FILE = "clips_prontos.json"

def processar_video(i, start, duration, video_url):
    temp_file = f"/tmp/final_{i}.mp4"
    # Chamada única ao serviço Cobalt (Proxy de alta confiança)
    # Se o Cobalt não conseguir, nenhum downloader gratuito consegue no Render
    try:
        req = requests.post("https://api.cobalt.tools/api/json", json={
            "url": video_url, "vQuality": "720", "isAudioOnly": False
        }, headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=60).json()
        
        url_direta = req.get("url")
        if not url_direta: return None

        # Recorte via FFmpeg (Rápido e sem bloqueios de JS)
        timestamp = f"{start//3600:02d}:{(start%3600)//60:02d}:{start%60:02d}"
        subprocess.run(["ffmpeg", "-y", "-ss", timestamp, "-i", url_direta, "-t", str(duration), "-c", "copy", temp_file], check=True)
        
        # Upload Cloudinary
        res = cloudinary.uploader.upload_large(temp_file, resource_type="video")
        url, _ = cloudinary.utils.cloudinary_url(res['public_id'], resource_type="video", format="mp4", transformation=[
            {"width": 1080, "height": 1920, "crop": "fill", "gravity": "face"}
        ])
        return url
    except Exception as e:
        print(f"Erro no corte {i}: {e}")
        return None

def run_wrapper(link):
    # Simulação da etapa de IA (substitua pelos seus prompts)
    clips = [{"start": 30, "duration": 30, "title": "Corte 1"}, {"start": 90, "duration": 30, "title": "Corte 2"}]
    
    results = []
    for i, c in enumerate(clips):
        url = processar_video(i, c['start'], c['duration'], link)
        results.append({"id": i, "title": c['title'], "url": url or "", "status": "pronto" if url else "erro"})
    
    with open(CLIPS_FILE, "w") as f: json.dump(results, f)
