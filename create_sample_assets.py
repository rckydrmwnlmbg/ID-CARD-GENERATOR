"""
Script to create sample template image and portrait photo for ID Card Generator.
"""
from PIL import Image, ImageDraw, ImageFont
import os

def create_sample_template():
    # Portrait ID Card CR80 standard at 300 DPI: 638 x 1011 px
    width, height = 638, 1011
    img = Image.new("RGBA", (width, height), (248, 249, 252, 255))
    draw = ImageDraw.Draw(img)

    # Top header gradient / block
    for y in range(0, 220):
        # Gradient from deep navy #0f2027 to electric blue #203a43
        ratio = y / 220.0
        r = int(15 + (32 - 15) * ratio)
        g = int(32 + (58 - 32) * ratio)
        b = int(45 + (85 - 45) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Accent stripe
    draw.rectangle([(0, 215), (width, 225)], fill=(245, 166, 35, 255)) # Gold / Amber accent

    # Draw company header text
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except Exception:
        font_large = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((width // 2, 80), "NUSANTARA TECH", fill=(255, 255, 255, 255), anchor="mm", font=font_large)
    draw.text((width // 2, 130), "INNOVATION & DIGITAL SOLUTIONS", fill=(200, 220, 245, 255), anchor="mm", font=font_sub)

    # Photo frame placeholder guide background (soft card)
    photo_box = [169, 270, 469, 630] # 300 x 360 px
    draw.rectangle(
        [photo_box[0] - 6, photo_box[1] - 6, photo_box[2] + 6, photo_box[3] + 6],
        fill=(220, 225, 235, 255),
    )
    draw.rectangle(photo_box, fill=(255, 255, 255, 255))

    # Bottom footer decor
    for y in range(height - 100, height):
        ratio = (y - (height - 100)) / 100.0
        r = int(24 + (15 - 24) * ratio)
        g = int(44 + (32 - 44) * ratio)
        b = int(60 + (45 - 60) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    draw.rectangle([(0, height - 105), (width, height - 98)], fill=(245, 166, 35, 255))

    draw.text((width // 2, height - 50), "WWW.NUSANTARATECH.CO.ID  •  OFFICIAL ID", fill=(220, 230, 245, 255), anchor="mm", font=font_sub)

    template_path = os.path.join("sample_data", "sample_template.png")
    img.save(template_path, "PNG", dpi=(300, 300))
    print(f"Created template: {template_path}")


def create_sample_photo():
    # Create a nice sample avatar photo: 400 x 480 px
    width, height = 400, 480
    img = Image.new("RGBA", (width, height), (230, 240, 250, 255))
    draw = ImageDraw.Draw(img)

    # Background gradient
    for y in range(height):
        r = int(210 + (235 - 210) * (y / height))
        g = int(225 + (245 - 225) * (y / height))
        b = int(245 + (255 - 245) * (y / height))
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Shoulders / torso
    draw.ellipse([80, 260, 320, 520], fill=(41, 128, 185, 255))
    # Neck
    draw.rectangle([170, 220, 230, 280], fill=(235, 188, 145, 255))
    # Head / face
    draw.ellipse([140, 100, 260, 250], fill=(245, 205, 165, 255))
    # Hair
    draw.chord([135, 80, 265, 200], start=180, end=360, fill=(44, 30, 20, 255))
    draw.ellipse([135, 80, 265, 140], fill=(44, 30, 20, 255))
    # Eyes
    draw.ellipse([165, 165, 180, 180], fill=(40, 40, 40, 255))
    draw.ellipse([220, 165, 235, 180], fill=(40, 40, 40, 255))
    # Smile
    draw.arc([180, 190, 220, 220], start=20, end=160, fill=(180, 70, 70, 255), width=3)

    photo_path = os.path.join("sample_data", "sample_photo.png")
    img.save(photo_path, "PNG")
    print(f"Created sample photo: {photo_path}")


def create_sample_csv():
    csv_content = """Nama,NIK,Divisi,Foto
Budi Pratama,NT-2024-001,Senior Software Engineer,sample_data/sample_photo.png
Siti Rahmawati,NT-2024-002,Lead Product Designer,sample_data/sample_photo.png
Ahmad Fauzi,NT-2024-003,DevOps & Cloud Specialist,sample_data/sample_photo.png
Dewi Anggraini,NT-2024-004,Head of HR & Talent Acquisition,sample_data/sample_photo.png
Rizky Ramadhan,NT-2024-005,Data Scientist & AI Researcher,sample_data/sample_photo.png
Nadia Putri,NT-2024-006,Quality Assurance Lead,sample_data/sample_photo.png
Andi Wijaya,NT-2024-007,Frontend Architect,sample_data/sample_photo.png
Maya Lestari,NT-2024-008,Finance & Operations Manager,sample_data/sample_photo.png
Doni Prasetyo,NT-2024-009,Cybersecurity Specialist,sample_data/sample_photo.png
"""
    csv_path = os.path.join("sample_data", "sample_batch.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(csv_content)
    print(f"Created sample csv: {csv_path}")

if __name__ == "__main__":
    create_sample_template()
    create_sample_photo()
    create_sample_csv()
