"""
Core Rendering and Generation Engine for ID Card Generator.
Handles Pillow high-DPI rendering, smart font fitting, background removal,
and A4 PDF 3x3 print layout generation.
"""
import os
import io
import math
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests

from models import TemplateConfig, LayerConfig

logger = logging.getLogger("generator_engine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class BackgroundRemovalService:
    """Handles remove.bg API calls with disk caching and error resilience."""
    
    def __init__(self, api_key: str = "", cache_dir: str = ".cache/rembg"):
        self.api_key = api_key
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def set_api_key(self, api_key: str):
        self.api_key = api_key.strip()

    def _get_cache_path(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            return os.path.join(self.cache_dir, f"{file_hash}.png")
        except Exception:
            safe_name = hashlib.md5(image_path.encode("utf-8")).hexdigest()
            return os.path.join(self.cache_dir, f"{safe_name}.png")

    def remove_background(self, image_path: str) -> Optional[Image.Image]:
        """
        Removes background from an image file using remove.bg API.
        Uses cached result if available.
        Returns PIL.Image.Image or None if failed.
        """
        if not os.path.exists(image_path):
            logger.warning(f"File foto tidak ditemukan: {image_path}")
            return None

        cache_path = self._get_cache_path(image_path)
        if os.path.exists(cache_path):
            try:
                logger.info(f"Menggunakan foto hasil cache background removal: {cache_path}")
                return Image.open(cache_path).convert("RGBA")
            except Exception as e:
                logger.warning(f"Gagal membaca cache foto: {e}")

        if not self.api_key:
            logger.info("API Key remove.bg kosong. Menggunakan foto asli tanpa pemotongan background.")
            return None

        try:
            logger.info(f"Mengirim permintaan background removal ke remove.bg untuk {image_path}...")
            with open(image_path, "rb") as img_file:
                response = requests.post(
                    "https://api.remove.bg/v1.0/removebg",
                    files={"image_file": img_file},
                    data={"size": "auto"},
                    headers={"X-Api-Key": self.api_key},
                    timeout=30
                )
            
            if response.status_code == 200:
                result_img = Image.open(io.BytesIO(response.content)).convert("RGBA")
                result_img.save(cache_path, "PNG")
                logger.info(f"Background berhasil dihapus dan disimpan ke cache: {cache_path}")
                return result_img
            else:
                logger.error(f"Remove.bg API Error ({response.status_code}): {response.text}")
                return None
        except Exception as e:
            logger.error(f"Gagal memanggil remove.bg API: {e}")
            return None


class FontManager:
    """Resolves and loads TrueType/OpenType fonts with fallback strategies."""
    
    SYSTEM_FALLBACKS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf",
        "/usr/share/fonts/opentype/urw-base35/NimbusSans-Regular.otf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf"
    ]

    _cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

    @classmethod
    def get_font(cls, font_path: str, size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
        cache_key = (font_path, size, bold, italic)
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        # 1. Try explicit user path
        if font_path and os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, size)
                cls._cache[cache_key] = font
                return font
            except Exception as e:
                logger.warning(f"Gagal memuat font kustom '{font_path}': {e}")

        # 2. Try matching system fonts
        for candidate in cls.SYSTEM_FALLBACKS:
            if bold and "bold" not in candidate.lower():
                continue
            if os.path.exists(candidate):
                try:
                    font = ImageFont.truetype(candidate, size)
                    cls._cache[cache_key] = font
                    return font
                except Exception:
                    continue

        # 3. Final fallback: DejaVuSans or default
        for candidate in cls.SYSTEM_FALLBACKS:
            if os.path.exists(candidate):
                try:
                    font = ImageFont.truetype(candidate, size)
                    cls._cache[cache_key] = font
                    return font
                except Exception:
                    pass

        font = ImageFont.load_default()
        return font


class CardRenderer:
    """Renders high-quality ID cards using Pillow with pixel-perfect layer composition."""
    
    def __init__(self, bg_remover: Optional[BackgroundRemovalService] = None):
        self.bg_remover = bg_remover or BackgroundRemovalService()

    def render(self, template: TemplateConfig, data: Dict[str, Any], enable_bg_removal: bool = False) -> Image.Image:
        """
        Renders a single ID Card at template native resolution (e.g. 300 DPI).
        Returns RGBA Pillow Image.
        """
        # 1. Base card image
        card_w, card_h = template.width, template.height
        if template.template_image_path and os.path.exists(template.template_image_path):
            try:
                base_img = Image.open(template.template_image_path).convert("RGBA")
                if base_img.size != (card_w, card_h):
                    base_img = base_img.resize((card_w, card_h), Image.Resampling.LANCZOS)
            except Exception as e:
                logger.warning(f"Gagal memuat gambar template '{template.template_image_path}': {e}. Menggunakan kanvas putih.")
                base_img = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 255))
        else:
            base_img = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 255))

        # Composite layers in order
        for layer in template.layers:
            if layer.type == "photo":
                self._render_photo_layer(base_img, layer, data, enable_bg_removal)
            elif layer.type == "text":
                self._render_text_layer(base_img, layer, data)

        return base_img

    def _render_photo_layer(self, base_img: Image.Image, layer: LayerConfig, data: Dict[str, Any], enable_bg_removal: bool):
        photo_val = data.get(layer.key) or layer.placeholder_path
        photo_img = None

        if photo_val and isinstance(photo_val, str) and os.path.exists(photo_val):
            # Try background removal if requested for this layer and enabled globally
            if layer.remove_bg and enable_bg_removal:
                photo_img = self.bg_remover.remove_background(photo_val)
            if photo_img is None:
                try:
                    photo_img = Image.open(photo_val).convert("RGBA")
                except Exception as e:
                    logger.error(f"Gagal membuka foto '{photo_val}': {e}")
        elif layer.placeholder_path and os.path.exists(layer.placeholder_path):
            try:
                photo_img = Image.open(layer.placeholder_path).convert("RGBA")
            except Exception:
                pass

        target_w, target_h = max(10, layer.width), max(10, layer.height)

        if photo_img is None:
            # Draw placeholder grey box with camera icon or text
            placeholder = Image.new("RGBA", (target_w, target_h), (230, 235, 242, 255))
            p_draw = ImageDraw.Draw(placeholder)
            p_draw.rectangle([(0, 0), (target_w - 1, target_h - 1)], outline=(180, 190, 205, 255), width=2)
            p_draw.text((target_w // 2, target_h // 2), "FOTO", fill=(120, 130, 145, 255), anchor="mm")
            photo_processed = placeholder
        else:
            photo_processed = self._fit_image(photo_img, target_w, target_h, layer.fit_mode)

        # Apply rounded corner mask
        if layer.corner_radius > 0:
            photo_processed = self._apply_corner_radius(photo_processed, layer.corner_radius)

        # Draw border if requested
        if layer.border_width > 0:
            photo_processed = self._draw_border(photo_processed, layer.border_width, layer.border_color, layer.corner_radius)

        # Paste onto card with alpha compositing
        base_img.alpha_composite(photo_processed, dest=(layer.x, layer.y))

    def _fit_image(self, img: Image.Image, target_w: int, target_h: int, fit_mode: str) -> Image.Image:
        img_w, img_h = img.size
        if fit_mode == "contain":
            # Scale down to fit inside box without cropping
            ratio = min(target_w / img_w, target_h / img_h)
            new_w, new_h = max(1, int(img_w * ratio)), max(1, int(img_h * ratio))
            scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            offset_x = (target_w - new_w) // 2
            offset_y = (target_h - new_h) // 2
            canvas.alpha_composite(scaled, dest=(offset_x, offset_y))
            return canvas
        elif fit_mode == "crop" or fit_mode == "cover":
            # Cover box completely, center crop
            ratio = max(target_w / img_w, target_h / img_h)
            new_w, new_h = max(1, int(img_w * ratio)), max(1, int(img_h * ratio))
            scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            return scaled.crop((left, top, left + target_w, top + target_h))
        else:
            # Stretch
            return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    def _apply_corner_radius(self, img: Image.Image, radius: int) -> Image.Image:
        w, h = img.size
        # 4x supersampling mask for ultra-smooth anti-aliased corners
        scale = 4
        mask = Image.new("L", (w * scale, h * scale), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), (w * scale, h * scale)], radius=radius * scale, fill=255)
        mask = mask.resize((w, h), Image.Resampling.LANCZOS)
        
        output = img.copy()
        current_alpha = img.getchannel("A")
        final_alpha = Image.composite(current_alpha, Image.new("L", (w, h), 0), mask)
        output.putalpha(final_alpha)
        return output

    def _draw_border(self, img: Image.Image, border_w: int, border_color: str, radius: int) -> Image.Image:
        w, h = img.size
        scale = 4
        border_canvas = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(border_canvas)
        
        inset = (border_w * scale) / 2.0
        draw.rounded_rectangle(
            [(inset, inset), (w * scale - inset, h * scale - inset)],
            radius=max(0, radius * scale),
            outline=border_color,
            width=int(border_w * scale)
        )
        border_canvas = border_canvas.resize((w, h), Image.Resampling.LANCZOS)
        
        output = img.copy()
        output.alpha_composite(border_canvas)
        return output

    def _render_text_layer(self, base_img: Image.Image, layer: LayerConfig, data: Dict[str, Any]):
        raw_text = str(data.get(layer.key, layer.default_text))
        if layer.uppercase:
            raw_text = raw_text.upper()
        if not raw_text:
            return

        target_w = max(10, layer.width)
        target_h = max(10, layer.height)
        font_size = layer.font_size
        min_size = layer.min_font_size if layer.auto_fit else font_size

        font = FontManager.get_font(layer.font_path, font_size, bold=layer.bold, italic=layer.italic)
        
        # Temp draw for bbox measurements
        temp_img = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(temp_img)

        # Smart Font Fitting: Reduce font size down to min_font_size if it overflows target_w
        if layer.auto_fit:
            while font_size > min_size:
                bbox = draw.textbbox((0, 0), raw_text, font=font)
                text_w = bbox[2] - bbox[0]
                if text_w <= target_w:
                    break
                font_size -= 1
                font = FontManager.get_font(layer.font_path, font_size, bold=layer.bold, italic=layer.italic)

        bbox = draw.textbbox((0, 0), raw_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Horizontal alignment within bounding box
        if layer.alignment == "center":
            pos_x = layer.x + (target_w - text_w) / 2.0 - bbox[0]
        elif layer.alignment == "right":
            pos_x = layer.x + target_w - text_w - bbox[0]
        else:  # left
            pos_x = layer.x - bbox[0]

        # Vertical centering within bounding box
        pos_y = layer.y + (target_h - text_h) / 2.0 - bbox[1]

        # Render text onto card
        card_draw = ImageDraw.Draw(base_img)
        card_draw.text((pos_x, pos_y), raw_text, fill=layer.font_color, font=font)


def export_single_card(
    template: TemplateConfig,
    data: Dict[str, Any],
    output_path: str,
    enable_bg_removal: bool = False,
    bg_remover: Optional[BackgroundRemovalService] = None,
    dpi: int = 300
) -> str:
    """Exports a single ID card to disk (PNG/JPEG) with high resolution DPI metadata."""
    renderer = CardRenderer(bg_remover)
    img = renderer.render(template, data, enable_bg_removal=enable_bg_removal)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    ext = os.path.splitext(output_path)[1].lower()
    if ext in [".jpg", ".jpeg"]:
        # JPEG doesn't support alpha, composite on white
        rgb_img = Image.new("RGB", img.size, (255, 255, 255))
        rgb_img.paste(img, mask=img.split()[3])
        rgb_img.save(output_path, "JPEG", quality=95, dpi=(dpi, dpi))
    else:
        img.save(output_path, "PNG", dpi=(dpi, dpi))
    return output_path


def build_a4_pdf_grid(
    card_images: List[Image.Image],
    output_pdf_path: str,
    dpi: int = 300,
    show_cut_marks: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> str:
    """
    Assembles a list of card images into an A4 3x3 Grid PDF ready for commercial printing.
    Standard A4: 210mm x 297mm (2480 x 3508 pixels @ 300 DPI).
    Computes exact symmetric margins and cutting guides.
    """
    # A4 Dimensions in pixels at 300 DPI
    A4_WIDTH = int(210.0 / 25.4 * dpi)   # 2480 px
    A4_HEIGHT = int(297.0 / 25.4 * dpi)  # 3508 px

    cols = 3
    rows = 3
    cards_per_page = cols * rows

    if not card_images:
        raise ValueError("Daftar gambar kartu kosong.")

    # Base card dimensions from the first card
    sample_w, sample_h = card_images[0].size

    # Check orientation: if card is landscape or exceeds space, calculate optimal scale
    # Allow small gap of 3mm = ~35 px between cards
    gap_x = int(3.0 / 25.4 * dpi)
    gap_y = int(3.0 / 25.4 * dpi)

    max_grid_w = A4_WIDTH - int(10.0 / 25.4 * dpi)  # at least 5mm margin on sides
    max_grid_h = A4_HEIGHT - int(10.0 / 25.4 * dpi)

    scale = min(
        (max_grid_w - (cols - 1) * gap_x) / (cols * sample_w),
        (max_grid_h - (rows - 1) * gap_y) / (rows * sample_h),
        1.0
    )

    card_w = int(sample_w * scale)
    card_h = int(sample_h * scale)

    # Symmetric margins calculation
    grid_total_w = cols * card_w + (cols - 1) * gap_x
    grid_total_h = rows * card_h + (rows - 1) * gap_y
    margin_x = (A4_WIDTH - grid_total_w) // 2
    margin_y = (A4_HEIGHT - grid_total_h) // 2

    pages: List[Image.Image] = []
    total_cards = len(card_images)
    total_pages = math.ceil(total_cards / cards_per_page)

    for page_idx in range(total_pages):
        page_img = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(page_img)

        # Page header info (small print metadata outside cut area)
        try:
            meta_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        except Exception:
            meta_font = ImageFont.load_default()
        
        draw.text(
            (margin_x, margin_y - 45),
            f"ID CARD BATCH PRINT (A4 300 DPI) — Halaman {page_idx + 1} dari {total_pages}",
            fill=(140, 150, 160),
            font=meta_font
        )

        start_card = page_idx * cards_per_page
        end_card = min(start_card + cards_per_page, total_cards)

        for idx in range(start_card, end_card):
            grid_idx = idx - start_card
            col = grid_idx % cols
            row = grid_idx // cols

            pos_x = margin_x + col * (card_w + gap_x)
            pos_y = margin_y + row * (card_h + gap_y)

            card_img = card_images[idx]
            if card_img.size != (card_w, card_h):
                card_img = card_img.resize((card_w, card_h), Image.Resampling.LANCZOS)

            # Paste card
            if card_img.mode == "RGBA":
                page_img.paste(card_img, (pos_x, pos_y), mask=card_img.split()[3])
            else:
                page_img.paste(card_img, (pos_x, pos_y))

            # Draw precision cut marks (L-shapes at corners)
            if show_cut_marks:
                mark_len = 16
                mark_color = (180, 180, 180)
                # Top-Left
                draw.line([(pos_x - 5, pos_y), (pos_x - 5 - mark_len, pos_y)], fill=mark_color, width=2)
                draw.line([(pos_x, pos_y - 5), (pos_x, pos_y - 5 - mark_len)], fill=mark_color, width=2)
                # Top-Right
                draw.line([(pos_x + card_w + 5, pos_y), (pos_x + card_w + 5 + mark_len, pos_y)], fill=mark_color, width=2)
                draw.line([(pos_x + card_w, pos_y - 5), (pos_x + card_w, pos_y - 5 - mark_len)], fill=mark_color, width=2)
                # Bottom-Left
                draw.line([(pos_x - 5, pos_y + card_h), (pos_x - 5 - mark_len, pos_y + card_h)], fill=mark_color, width=2)
                draw.line([(pos_x, pos_y + card_h + 5), (pos_x, pos_y + card_h + 5 + mark_len)], fill=mark_color, width=2)
                # Bottom-Right
                draw.line([(pos_x + card_w + 5, pos_y + card_h), (pos_x + card_w + 5 + mark_len, pos_y + card_h)], fill=mark_color, width=2)
                draw.line([(pos_x + card_w, pos_y + card_h + 5), (pos_x + card_w, pos_y + card_h + 5 + mark_len)], fill=mark_color, width=2)

        pages.append(page_img)
        if progress_callback:
            progress_callback(page_idx + 1, total_pages, f"Membuat halaman PDF {page_idx + 1} dari {total_pages}...")

    # Save multi-page PDF
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)
    if pages:
        first_page = pages[0]
        other_pages = pages[1:] if len(pages) > 1 else []
        first_page.save(output_pdf_path, "PDF", resolution=float(dpi), save_all=True, append_images=other_pages)
        logger.info(f"PDF Berhasil dibuat: {output_pdf_path} ({len(pages)} halaman)")
    return output_pdf_path
