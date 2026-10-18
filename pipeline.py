import os, requests, time, json
from flask import jsonify

def processar_viral(link):
    # Usaremos a API da Vidoza ou Cobalt via requests simples
    # Isso evita usar yt-dlp dentro do seu servidor
    try:
        # 1. Solicita o vídeo ao Cobalt (sem baixar no seu servidor)
        resp = requests.post("https://api.cobalt.tools/api/json", 
            json={"url": link, "vQuality": "720"},
            headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=30)
        video_url = resp.json().get("url")
        
        if not video_url: return "Erro no Cobalt"
        
        # 2. Envia para o Cloudinary apenas a URL (o Cloudinary baixa pra você na nuvem dele)
        import cloudinary.uploader
        upload = cloudinary.uploader.upload_large(video_url, resource_type="video")
        
        return upload['secure_url']
    except Exception as e:
        return str(e)
