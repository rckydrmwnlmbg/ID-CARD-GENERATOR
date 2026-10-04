"""
ID Card Generator - Unified Entry Point.
Can be executed as:
  1. Desktop Visual GUI (Default):
     python idcard.py
  2. Headless CLI Batch Exporter:
     python idcard.py --preset sample_data/sample_preset.json --csv sample_data/sample_batch.csv --output result.pdf
"""
import sys
import os
import argparse
import csv

from models import TemplateConfig
from generator_engine import CardRenderer, build_a4_pdf_grid, export_single_card, BackgroundRemovalService


def run_cli(args):
    print("=== ID Card Generator CLI Mode ===")
    if not os.path.exists(args.preset):
        print(f"Error: Preset file not found: {args.preset}")
        sys.exit(1)

    if args.preset.endswith(".yaml") or args.preset.endswith(".yml"):
        template = TemplateConfig.load_from_yaml(args.preset)
    else:
        template = TemplateConfig.load_from_json(args.preset)

    if args.template_image and os.path.exists(args.template_image):
        template.template_image_path = args.template_image

    if not os.path.exists(args.csv):
        print(f"Error: CSV data file not found: {args.csv}")
        sys.exit(1)

    records = []
    with open(args.csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    print(f"Loaded {len(records)} records from {args.csv}")
    print(f"Template: {template.name} ({template.width}x{template.height} px, {template.dpi} DPI)")

    bg_service = BackgroundRemovalService(api_key=args.api_key or "")
    renderer = CardRenderer(bg_service)
    rendered_cards = []

    for i, row in enumerate(records):
        name = row.get("Nama") or row.get("nama") or f"Record #{i+1}"
        print(f"  [{i+1}/{len(records)}] Rendering card for: {name}")
        img = renderer.render(template, row, enable_bg_removal=bool(args.api_key))
        rendered_cards.append(img)

    output_path = args.output
    if output_path.lower().endswith(".pdf"):
        print(f"Building 3x3 A4 Grid PDF: {output_path}...")
        build_a4_pdf_grid(rendered_cards, output_path, dpi=template.dpi, show_cut_marks=not args.no_cut_marks)
        print(f"Success! Output saved to: {output_path}")
    else:
        # Directory output
        os.makedirs(output_path, exist_ok=True)
        for i, (row, img) in enumerate(zip(records, rendered_cards)):
            nik = str(row.get("NIK") or row.get("nik") or i+1).replace("/", "_")
            nama = str(row.get("Nama") or row.get("nama") or i+1).replace("/", "_").replace(" ", "_")
            out_file = os.path.join(output_path, f"ID_{nik}_{nama}.png")
            img.save(out_file, "PNG", dpi=(template.dpi, template.dpi))
        print(f"Success! {len(rendered_cards)} card images saved to folder: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="ID Card Generator & Batch Studio")
    parser.add_argument("--cli", action="store_true", help="Run in headless CLI mode instead of GUI")
    parser.add_argument("--preset", default="sample_data/sample_preset.json", help="Path to template preset JSON/YAML")
    parser.add_argument("--template-image", default=None, help="Override background template image path")
    parser.add_argument("--csv", help="Path to CSV batch file")
    parser.add_argument("--output", default="id_cards_output.pdf", help="Output PDF file path or image folder path")
    parser.add_argument("--api-key", default="", help="remove.bg API Key for background removal")
    parser.add_argument("--no-cut-marks", action="store_true", help="Disable cutting guides on PDF")

    # If any CLI batch arguments are explicitly passed, run in CLI mode
    if len(sys.argv) > 1 and ("--cli" in sys.argv or "--csv" in sys.argv):
        args = parser.parse_args()
        run_cli(args)
    else:
        # Launch full PyQt6 Visual GUI
        from main import main as launch_gui
        launch_gui()


if __name__ == "__main__":
    main()
