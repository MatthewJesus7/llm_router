# ver providers
python main.py list

# imagem síncrona (DALL-E)
python main.py generate "a cat playing piano" -p OpenAI-Images-dall-e-3 -o cat.png

# áudio síncrono (TTS)
python main.py generate "olá mundo" -p OpenAI-TTS-tts-1 -o oi.mp3

# vídeo assíncrono (polling)
python main.py generate "waves on a beach" -p Replicate-stable-video-diffusion -o out.mp4 -t 300

# fallback automático (primeiro provider disponível)
python main.py generate "sunset over mountains"