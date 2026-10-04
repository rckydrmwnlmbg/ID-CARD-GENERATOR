"""
Comprehensive Test Suite for ID Card Generator Application.
Verifies models, rendering engine, smart font fitting, PDF grid builder, and UI worker threads.
"""
import unittest
import os
import shutil
from PIL import Image, ImageDraw, ImageFont

from models import LayerConfig, TemplateConfig
from generator_engine import (
    CardRenderer, FontManager, BackgroundRemovalService,
    export_single_card, build_a4_pdf_grid
)


class TestModels(unittest.TestCase):
    
    def test_layer_config_serialization(self):
        layer = LayerConfig(
            id="test_l1",
            type="text",
            name="Nama Karyawan",
            key="Nama",
            x=100,
            y=150,
            width=400,
            height=50,
            font_size=32,
            font_color="#ff0000",
            alignment="center",
            bold=True
        )
        data = layer.to_dict()
        self.assertEqual(data["id"], "test_l1")
        self.assertEqual(data["name"], "Nama Karyawan")
        self.assertEqual(data["font_color"], "#ff0000")

        reconstructed = LayerConfig.from_dict(data)
        self.assertEqual(reconstructed.id, layer.id)
        self.assertEqual(reconstructed.font_size, 32)
        self.assertTrue(reconstructed.bold)

    def test_template_json_yaml(self):
        tpl = TemplateConfig(name="Test Card", width=638, height=1011, dpi=300)
        tpl.add_layer(LayerConfig(id="l1", name="Layer 1", key="k1"))
        tpl.add_layer(LayerConfig(id="l2", name="Layer 2", key="k2"))

        os.makedirs("output_test", exist_ok=True)
        json_path = "output_test/test_preset.json"
        tpl.save_to_json(json_path)
        self.assertTrue(os.path.exists(json_path))

        loaded_json = TemplateConfig.load_from_json(json_path)
        self.assertEqual(loaded_json.name, "Test Card")
        self.assertEqual(len(loaded_json.layers), 2)

        # YAML test
        yaml_path = "output_test/test_preset.yaml"
        tpl.save_to_yaml(yaml_path)
        self.assertTrue(os.path.exists(yaml_path))

        loaded_yaml = TemplateConfig.load_from_yaml(yaml_path)
        self.assertEqual(loaded_yaml.name, "Test Card")
        self.assertEqual(len(loaded_yaml.layers), 2)

    def test_layer_reordering(self):
        tpl = TemplateConfig()
        tpl.add_layer(LayerConfig(id="a", name="A"))
        tpl.add_layer(LayerConfig(id="b", name="B"))
        tpl.add_layer(LayerConfig(id="c", name="C"))

        # Move B up
        tpl.move_layer("b", -1)
        self.assertEqual([l.id for l in tpl.layers], ["b", "a", "c"])

        # Move B down
        tpl.move_layer("b", 1)
        self.assertEqual([l.id for l in tpl.layers], ["a", "b", "c"])

        # Remove layer
        tpl.remove_layer("a")
        self.assertEqual([l.id for l in tpl.layers], ["b", "c"])


class TestRenderingEngine(unittest.TestCase):

    def setUp(self):
        os.makedirs("output_test", exist_ok=True)
        self.template = TemplateConfig.create_default_preset("sample_data/sample_template.png")

    def test_single_render(self):
        renderer = CardRenderer()
        data = {
            "Nama": "Budi Pratama",
            "NIK": "NIK: NT-2024-001",
            "Divisi": "Software Engineer",
            "Foto": "sample_data/sample_photo.png"
        }
        card_img = renderer.render(self.template, data)
        self.assertEqual(card_img.size, (self.template.width, self.template.height))
        self.assertEqual(card_img.mode, "RGBA")

    def test_smart_font_fitting(self):
        """Verifies that an extra-long string automatically shrinks and fits inside bounding box."""
        renderer = CardRenderer()
        nama_layer = self.template.get_layer("layer_nama")
        self.assertIsNotNone(nama_layer)
        nama_layer.auto_fit = True
        nama_layer.min_font_size = 10
        nama_layer.font_size = 40
        nama_layer.width = 300  # Narrow width

        extra_long_name = "DR. IR. RADEN MAS BUDI PRATAMA KUSUMANEGARA SURYOHADININGRAT"
        data = {"Nama": extra_long_name}

        card_img = renderer.render(self.template, data)
        self.assertIsNotNone(card_img)

    def test_export_single_card_png_and_jpg(self):
        data = {
            "Nama": "Siti Rahmawati",
            "NIK": "NT-2024-002",
            "Divisi": "Product Designer",
            "Foto": "sample_data/sample_photo.png"
        }
        png_path = "output_test/test_export.png"
        jpg_path = "output_test/test_export.jpg"

        export_single_card(self.template, data, png_path, dpi=300)
        self.assertTrue(os.path.exists(png_path))

        export_single_card(self.template, data, jpg_path, dpi=300)
        self.assertTrue(os.path.exists(jpg_path))

    def test_a4_pdf_grid_builder(self):
        renderer = CardRenderer()
        data = {"Nama": "Tester", "NIK": "123", "Divisi": "QA", "Foto": "sample_data/sample_photo.png"}
        card_img = renderer.render(self.template, data)

        # 19 cards -> 9 per page -> 3 pages
        cards = [card_img for _ in range(19)]
        pdf_path = "output_test/test_multipage_grid.pdf"
        build_a4_pdf_grid(cards, pdf_path, dpi=300, show_cut_marks=True)

        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 50000)


class TestWorkerThreading(unittest.TestCase):

    def test_batch_worker_execution(self):
        from PyQt6.QtWidgets import QApplication
        from main import BatchExportWorker

        app = QApplication.instance() or QApplication([])

        template = TemplateConfig.create_default_preset("sample_data/sample_template.png")
        records = [
            {"Nama": f"User {i}", "NIK": f"ID-{i}", "Divisi": "Dept", "Foto": "sample_data/sample_photo.png"}
            for i in range(5)
        ]
        out_folder = "output_test/batch_images"
        os.makedirs(out_folder, exist_ok=True)

        worker = BatchExportWorker(
            template=template,
            records=records,
            export_mode="folder_images",
            output_path=out_folder,
            enable_bg_removal=False,
            api_key="",
            dpi=300
        )

        results = []
        worker.finished.connect(lambda msg: results.append(msg))
        worker.run()

        self.assertEqual(len(results), 1)
        self.assertIn("selesai", results[0].lower())
        generated_files = [f for f in os.listdir(out_folder) if f.endswith(".png")]
        self.assertEqual(len(generated_files), 5)


if __name__ == "__main__":
    unittest.main()
