from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size, path):
    img = Image.new('RGB', (size, size), color=(73, 109, 137))
    d = ImageDraw.Draw(img)
    # Desenhar um "P" simples no centro
    # Como não tenho garantia de fontes, vou desenhar um círculo e um retângulo
    
    # Círculo branco
    margin = size // 10
    d.ellipse([margin, margin, size - margin, size - margin], outline="white", width=size//20)
    
    # Texto P (simulado com formas geométricas se necessário, ou apenas deixar o ícone genérico)
    # Vou fazer um relógio simplificado
    center = size // 2
    d.line([center, center, center, margin * 2], fill="white", width=size//30)
    d.line([center, center, size - margin * 2, center], fill="white", width=size//30)
    
    img.save(path)

if not os.path.exists("static/icons"):
    os.makedirs("static/icons")

create_icon(192, "static/icons/icon-192x192.png")
create_icon(512, "static/icons/icon-512x512.png")
print("Ícones gerados.")