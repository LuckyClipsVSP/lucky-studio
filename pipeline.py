import os, sys, json, time, requests, threading
import cloudinary, cloudinary.uploader

def processar_video_tarefa(link):
    # 1. Baixa usando o Cobalt (API pública que o YouTube não bloqueia)
    try:
        r = requests.post("https://api.cobalt.tools/api/json", 
            json={"url": link, "vQuality": "720"}, 
            headers={"Accept": "application/json", "Content-Type": "application/json"})
        video_url = r.json().get("url")
        if not video_url: return
        
        # 2. Upload direto pro Cloudinary (o Cloudinary baixa o vídeo da URL pra você)
        upload = cloudinary.uploader.upload_large(video_url, resource_type="video")
        print("Upload concluído com sucesso!")
        
    except Exception as e:
        print(f"Erro no processamento: {e}")

def run_background(link):
    # Isso roda em uma "thread" separada, não trava o site!
    thread = threading.Thread(target=processar_video_tarefa, args=(link,))
    thread.start()
