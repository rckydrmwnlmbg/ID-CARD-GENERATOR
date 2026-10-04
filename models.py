"""
Data models and configuration for ID Card Generator.
Defines LayerConfig and TemplateConfig with JSON/YAML serialization.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import json
import os
import sys
import uuid

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    if not relative_path:
        return ""
    if os.path.isabs(relative_path) and os.path.exists(relative_path):
        return relative_path

    # 1. Check in PyInstaller bundle directory
    if hasattr(sys, "_MEIPASS"):
        meipass_path = os.path.join(getattr(sys, "_MEIPASS"), relative_path)
        if os.path.exists(meipass_path):
            return meipass_path

    # 2. Check relative to current working directory
    if os.path.exists(relative_path):
        return os.path.abspath(relative_path)

    # 3. Check relative to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, relative_path)
    if os.path.exists(script_path):
        return script_path

    return relative_path


@dataclass
class LayerConfig:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "text"  # "text" or "photo"
    name: str = "Teks Baru"
    key: str = "teks"  # Data dictionary key
    x: int = 50
    y: int = 50
    width: int = 300
    height: int = 50

    # Text specific settings
    font_path: str = ""  # Custom .ttf / .otf file path
    font_size: int = 24
    font_color: str = "#000000"
    alignment: str = "center"  # "left", "center", "right"
    bold: bool = False
    italic: bool = False
    uppercase: bool = False
    auto_fit: bool = True
    min_font_size: int = 12
    default_text: str = "Sample Text"

    # Photo specific settings
    fit_mode: str = "cover"  # "cover", "contain", "crop"
    corner_radius: int = 12
    border_width: int = 2
    border_color: str = "#203a43"
    remove_bg: bool = False
    placeholder_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayerConfig":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class TemplateConfig:
    name: str = "Kartu ID Standar"
    template_image_path: str = ""
    width: int = 638   # 54mm @ 300 DPI
    height: int = 1011  # 85.6mm @ 300 DPI
    dpi: int = 300
    layers: List[LayerConfig] = field(default_factory=list)

    def add_layer(self, layer: LayerConfig):
        self.layers.append(layer)

    def remove_layer(self, layer_id: str) -> bool:
        initial_len = len(self.layers)
        self.layers = [l for l in self.layers if l.id != layer_id]
        return len(self.layers) < initial_len

    def get_layer(self, layer_id: str) -> Optional[LayerConfig]:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        return None

    def move_layer(self, layer_id: str, direction: int) -> bool:
        """direction: -1 for move down/backward, 1 for move up/forward"""
        for i, l in enumerate(self.layers):
            if l.id == layer_id:
                target_idx = i + direction
                if 0 <= target_idx < len(self.layers):
                    self.layers[i], self.layers[target_idx] = self.layers[target_idx], self.layers[i]
                    return True
                break
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "template_image_path": self.template_image_path,
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
            "layers": [l.to_dict() for l in self.layers]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateConfig":
        layers_data = data.get("layers", [])
        layers = [LayerConfig.from_dict(ld) for ld in layers_data]
        return cls(
            name=data.get("name", "Template ID Card"),
            template_image_path=data.get("template_image_path", ""),
            width=int(data.get("width", 638)),
            height=int(data.get("height", 1011)),
            dpi=int(data.get("dpi", 300)),
            layers=layers
        )

    def save_to_json(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_json(cls, filepath: str) -> "TemplateConfig":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = cls.from_dict(data)
        if cfg.template_image_path:
            cfg.template_image_path = resource_path(cfg.template_image_path)
        for l in cfg.layers:
            if l.placeholder_path:
                l.placeholder_path = resource_path(l.placeholder_path)
            if l.font_path:
                l.font_path = resource_path(l.font_path)
        return cfg

    def save_to_yaml(self, filepath: str):
        if not YAML_AVAILABLE:
            raise RuntimeError("PyYAML tidak terinstal.")
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, sort_keys=False, allow_unicode=True)

    @classmethod
    def load_from_yaml(cls, filepath: str) -> "TemplateConfig":
        if not YAML_AVAILABLE:
            raise RuntimeError("PyYAML tidak terinstal.")
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cfg = cls.from_dict(data)
        if cfg.template_image_path:
            cfg.template_image_path = resource_path(cfg.template_image_path)
        for l in cfg.layers:
            if l.placeholder_path:
                l.placeholder_path = resource_path(l.placeholder_path)
            if l.font_path:
                l.font_path = resource_path(l.font_path)
        return cfg

    @classmethod
    def create_default_preset(cls, template_img_path: str = "") -> "TemplateConfig":
        """Builds a default CR80 layout with Photo, Nama, NIK, and Divisi layers."""
        actual_template_path = resource_path(template_img_path or "sample_data/sample_template.png")
        cfg = cls(
            name="Preset Nusantara Tech Default",
            template_image_path=actual_template_path,
            width=638,
            height=1011,
            dpi=300
        )
        # 1. Photo Frame Layer
        cfg.add_layer(LayerConfig(
            id="layer_photo",
            type="photo",
            name="Foto Karyawan",
            key="Foto",
            x=169,
            y=270,
            width=300,
            height=360,
            fit_mode="cover",
            corner_radius=16,
            border_width=4,
            border_color="#0f2027",
            remove_bg=False,
            placeholder_path=resource_path("sample_data/sample_photo.png")
        ))
        # 2. Nama Lengkap Layer
        cfg.add_layer(LayerConfig(
            id="layer_nama",
            type="text",
            name="Nama Lengkap",
            key="Nama",
            x=40,
            y=670,
            width=558,
            height=55,
            font_size=36,
            font_color="#0f2027",
            alignment="center",
            bold=True,
            auto_fit=True,
            min_font_size=18,
            default_text="BUDI PRATAMA",
            uppercase=True
        ))
        # 3. NIK / ID Layer
        cfg.add_layer(LayerConfig(
            id="layer_nik",
            type="text",
            name="Nomor Induk (NIK)",
            key="NIK",
            x=40,
            y=740,
            width=558,
            height=40,
            font_size=24,
            font_color="#7f8c8d",
            alignment="center",
            bold=False,
            auto_fit=True,
            min_font_size=14,
            default_text="NIK: NT-2024-001"
        ))
        # 4. Divisi / Jabatan Layer
        cfg.add_layer(LayerConfig(
            id="layer_divisi",
            type="text",
            name="Divisi / Jabatan",
            key="Divisi",
            x=40,
            y=795,
            width=558,
            height=48,
            font_size=26,
            font_color="#203a43",
            alignment="center",
            bold=True,
            auto_fit=True,
            min_font_size=14,
            default_text="Senior Software Engineer"
        ))
        return cfg
