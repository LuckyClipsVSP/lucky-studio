import os, json, requests
import cloudinary, cloudinary.uploader

# Configurações
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # Sua chave AIza...
CLOUDINARY_URL = "cloudinary://chave_seu_cloudinary_aqui" # Use a string de conexão

def analisar_video_com_ia(link):
    """O Gemini 'assiste' o vídeo via link e retorna os momentos virais."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    Analise este vídeo: {link}. 
    Seja um editor de Shorts experiente. 
    1. Identifique 3 momentos de alta retenção (picos de energia/humor).
    2. Para cada momento, forneça: start_time, end_time, título viral e uma legenda curta.
    Responda apenas em JSON: [{{ "start": 10, "end": 40, "title": "...", "legenda": "..." }}]
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload).json()
    # Extrai o JSON da resposta da IA
    texto_ia = response['candidates'][0]['content']['parts'][0]['text']
    return json.loads(texto_ia[texto_ia.find("["):texto_ia.rfind("]")+1])

def processar_edição_na_nuvem(corte, video_original_url):
    """O Cloudinary baixa, corta e edita na nuvem DELES (sem travar seu servidor)."""
    transf = [
        {"start_offset": corte['start'], "duration": 30, "width": 1080, "height": 1920, "crop": "fill", "gravity": "face"},
        {"overlay": {"font_family": "Arial", "font_size": 50, "text": corte['title']}, "color": "white", "gravity": "north"},
        {"overlay": {"font_family": "Arial", "font_size": 40, "text": corte['legenda']}, "color": "yellow", "gravity": "south"}
    ]
    
    # O Cloudinary faz o trabalho pesado sozinho
    resultado = cloudinary.uploader.upload_large(video_original_url, resource_type="video", transformation=transf)
    return resultado['secure_url']
