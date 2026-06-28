import json
import os
import queue
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from PIL import Image, ImageEnhance, ImageDraw, ImageFont, ImageTk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class ImageComposer:
    def __init__(self, base_dir: Path, config_path: Path):
        self.base_dir = base_dir
        self.config = self._load_config(config_path)
        self.excel_file = self.base_dir / self.config["paths"]["excel_file"]
        self.cover_dir = self.base_dir / self.config["paths"]["cover_dir"]
        self.materials_dir = self.base_dir / self.config["paths"].get("materials_dir", "materials")
        self.output_dir = self.base_dir / self.config["paths"]["output_dir"]
        self.output_dir.mkdir(exist_ok=True)
        self.background_image = self.base_dir / self.config["canvas"]["background_image"]
        self.logo_image = self.base_dir / self.config["paths"]["logo_image"]
        self.watermark_image = self.base_dir / self.config["paths"]["watermark_image"]
        self.version_map = self.config["version_map"]
        self.cover_fixed_width = self.config["cover"]["fixed_width"]
        self.cover_bottom_left = tuple(self.config["cover"]["bottom_left"])
        self.reflection_opacity_top = self.config["reflection"]["opacity_top"]
        self.title_settings = self.config["text"]["title"]
        self.subtitle_settings = self.config["text"]["subtitle"]
        self.color_saturation = self.config["color_adjust"]["saturation"]
        self.color_brightness = self.config["color_adjust"]["brightness"]
        self.output_format = self.config["output"]["format"]
        self.output_quality = self.config["output"]["quality"]
        self.log_lines = []

    def _load_config(self, config_path: Path) -> dict:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _log(self, isbn: str, status: str) -> None:
        self.log_lines.append(isbn)
        self.log_lines.append(status)
        self.log_lines.append("——————————")

    def _resolve_font(self, font_name: str) -> Optional[Path]:
        candidate = self.base_dir / font_name
        if candidate.exists():
            return candidate
        system_font = Path("C:/Windows/Fonts") / font_name
        if system_font.exists():
            return system_font
        return None

    def _load_font(self, font_name: str, size: int) -> ImageFont.FreeTypeFont:
        font_path = self._resolve_font(font_name)
        if font_path and font_path.exists():
            return ImageFont.truetype(str(font_path), size)
        fallback_path = self._resolve_font(self.title_settings["fallback_font"])
        if fallback_path and fallback_path.exists():
            return ImageFont.truetype(str(fallback_path), size)
        return ImageFont.load_default()

    def _read_excel(self, excel_path: Path) -> pd.DataFrame:
        if not excel_path.exists():
            raise FileNotFoundError(f"Excel file not found: {excel_path}")
        df = pd.read_excel(excel_path, engine="openpyxl", dtype=str)
        return df.fillna("")

    def _fit_cover(self, cover_image: Image.Image) -> Image.Image:
        width = self.cover_fixed_width
        w, h = cover_image.size
        ratio = width / w
        return cover_image.resize((width, int(h * ratio)), Image.LANCZOS)

    def _create_reflection(self, cover_image: Image.Image) -> Image.Image:
        reflection = cover_image.transpose(Image.FLIP_TOP_BOTTOM)
        width, height = reflection.size
        mask = Image.new("L", (width, height))
        for y in range(height):
            alpha = int(self.reflection_opacity_top * 255 * (1 - y / max(height - 1, 1)))
            for x in range(width):
                mask.putpixel((x, y), alpha)
        reflection.putalpha(mask)
        return reflection

    def _draw_vertical_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        bottom_y: int,
        font: ImageFont.FreeTypeFont,
        max_height: int,
        settings: dict,
    ) -> int:
        if not text:
            return 0
        chars = list(text)
        font_name = settings["font_name"]
        default_size = settings.get("font_size", font.size)
        min_size = settings.get("min_font_size", default_size)
        max_size = settings.get("max_font_size", default_size)
        size_map = settings.get("size_map")
        if size_map is not None:
            count = len(chars)
            for entry in size_map:
                if entry["min_chars"] <= count <= entry["max_chars"]:
                    default_size = entry["size"]
                    break
        size = max(min(default_size, max_size), min_size)
        current_font = self._load_font(font_name, size)
        tracking_va = settings.get("tracking_va", 0)
        spacing_base = settings.get("spacing_base", 1.0)
        spacing_ratio = spacing_base
        max_height = settings.get("max_height", 380)
        max_columns = min(settings.get("max_columns", len(chars)), len(chars))
        column_gap_ratio = settings.get("column_gap_ratio", 1.0)
        bold = settings.get("font_weight", "Regular") == "Bold"

        def _get_char_size(font, char):
            """获取单个字符的实际宽高，兼容中文"""
            bbox = font.getbbox(char)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            return w, h, bbox[1]

        def _get_cell_size(font, size_ratio):
            """用'口'字获取标准字格大小，中文字符都以此为基准"""
            bbox = font.getbbox("口")
            cell_h = bbox[3] - bbox[1]
            cell_w = bbox[2] - bbox[0]
            return int(cell_h * size_ratio), cell_w

        # --- 自动缩小字号直到能放下 ---
        while True:
            cell_h, cell_w = _get_cell_size(current_font, spacing_ratio)
            cell_h = max(1, cell_h)
            chars_per_column = (len(chars) + max_columns - 1) // max_columns
            if cell_h * chars_per_column <= max_height or size <= min_size:
                break
            size = max(min_size, size - 2)
            current_font = self._load_font(font_name, size)
            if size == min_size:
                break

        cell_h, cell_w = _get_cell_size(current_font, spacing_ratio)
        cell_h = max(1, cell_h)
        column_gap = max(1, int(cell_w * column_gap_ratio))

        # --- 找最优列数 ---
        best_columns = 1
        best_balance = None
        best_layout = None
        for columns in range(1, max_columns + 1):
            chars_per_column = (len(chars) + columns - 1) // columns
            height = cell_h * chars_per_column
            if height > max_height:
                continue
            counts = [
                len(chars[i * chars_per_column: min(len(chars), (i + 1) * chars_per_column)])
                for i in range(columns)
            ]
            balance = max(counts) - min(counts)
            if best_balance is None or balance < best_balance or (
                balance == best_balance and columns > best_columns
            ):
                best_balance = balance
                best_columns = columns
                best_layout = (cell_h, columns, column_gap)
        if best_layout is None:
            best_columns = max_columns
            best_layout = (cell_h, best_columns, column_gap)

        cell_h, columns, column_gap = best_layout
        chars_per_column = (len(chars) + columns - 1) // columns

        for col_idx in range(columns):
            start = col_idx * chars_per_column
            end = min(len(chars), start + chars_per_column)
            column_chars = chars[start:end]
            # 从 bottom_y 往上推算起始 y
            total_h = cell_h * len(column_chars)
            y = bottom_y - total_h
            current_x = x - col_idx * column_gap

            for char in column_chars:
                # 每个字符居中对齐在 cell_w 内
                char_bbox = current_font.getbbox(char)
                char_w = char_bbox[2] - char_bbox[0]
                char_h = char_bbox[3] - char_bbox[1]
                top_offset = char_bbox[1]

                x_offset = (cell_w - char_w) // 2
                y_offset = (cell_h - char_h) // 2

                draw.text(
                    (current_x + x_offset, y + y_offset - top_offset),
                    char,
                    font=current_font,
                    fill="#000000",
                    stroke_width=1 if bold else 0,
                    stroke_fill="#000000" if bold else None,
                )
                y += cell_h

        return current_font.size

    def _apply_color_adjustment(self, image: Image.Image) -> Image.Image:
        if image.mode != "RGB":
            image = image.convert("RGB")
        image = ImageEnhance.Color(image).enhance(self.color_saturation)
        image = ImageEnhance.Brightness(image).enhance(self.color_brightness)
        return image

    def _safe_open_image(self, path: Path, mode: str = "RGBA") -> Optional[Image.Image]:
        if not path.exists():
            return None
        return Image.open(path).convert(mode)

    def _generate_single(self, row: dict, output_quality: int) -> tuple[str, str, Optional[Image.Image]]:
        isbn = str(row.get("ISBN", "")).strip()
        title = str(row.get("主标题", "")).strip()
        subtitle = str(row.get("副标题", "")).strip()
        version = str(row.get("文版", "")).strip()
        if not isbn:
            return "(No ISBN)", "Skipped: ISBN missing", None
        cover_path = self.cover_dir / f"{isbn}.jpg"
        if not cover_path.exists():
            return isbn, "Cover不存在", None
        try:
            canvas = Image.new("RGBA", (self.config["canvas"]["width"], self.config["canvas"]["height"]))
            background = self._safe_open_image(self.background_image)
            if background is not None:
                background = background.resize(canvas.size, Image.LANCZOS)
                canvas.paste(background, (0, 0), background)
            cover = self._safe_open_image(cover_path)
            if cover is None:
                return isbn, "Cover打开失败", None
            cover = self._fit_cover(cover)
            cover_x, cover_bottom_y = self.cover_bottom_left
            cover_y = cover_bottom_y - cover.height
            
            # 添加阴影效果
            shadow_settings = self.config.get("shadow_settings", {})
            if shadow_settings.get("enabled", True):
                shadow_path = self.materials_dir / self.config["paths"].get("shadow", "投影.png")
                shadow = self._safe_open_image(shadow_path)
                if shadow:
                    # 计算阴影缩放比例
                    N = cover.height
                    base_height = shadow_settings.get("base_height", 530)
                    scale = N / base_height
                    shadow_width = int(shadow.width * scale)
                    shadow_height = int(shadow.height * scale)
                    shadow_resized = shadow.resize((shadow_width, shadow_height), Image.LANCZOS)
                    # 调试：打印缩放比例和尺寸
                    print(f"Scale: {scale}, Original shadow size: {shadow.size}, Resized: {shadow_resized.size}")
                    # 调试：打印缩放比例和尺寸
                    print(f"Scale: {scale}, Original shadow size: {shadow.size}, Resized: {shadow_resized.size}")
                    # 阴影位置：底部Y=720，根据对齐方式计算X位置
                    shadow_bottom_y = shadow_settings.get("shadow_bottom_y", 720)
                    shadow_y = shadow_bottom_y - shadow_height
                    alignment = shadow_settings.get("alignment", "center")
                    if alignment == "center":
                        shadow_x = (self.config["canvas"]["width"] - shadow_width) // 2
                    elif alignment == "left":
                        shadow_x = 0
                    else:  # right
                        shadow_x = self.config["canvas"]["width"] - shadow_width
                    canvas.paste(shadow_resized, (shadow_x, shadow_y), shadow_resized)
            
            canvas.paste(cover, (cover_x, cover_y), cover)
            reflection = self._create_reflection(cover)
            reflection_y = cover_bottom_y
            canvas.paste(reflection, (cover_x, reflection_y), reflection)
            draw = ImageDraw.Draw(canvas)
            title_font = self._load_font(self.title_settings["font_name"], self.title_settings["font_size"])
            subtitle_font = self._load_font(self.title_settings["font_name"], self.subtitle_settings["font_size"])
            if title:
                self._draw_vertical_text(
                    draw,
                    title,
                    self.title_settings["x"],
                    self.title_settings["bottom_y"],
                    title_font,
                    self.title_settings["max_height"],
                    self.title_settings,
                )
            if subtitle:
                self._draw_vertical_text(
                    draw,
                    subtitle,
                    self.subtitle_settings["x"],
                    self.subtitle_settings["bottom_y"],
                    subtitle_font,
                    self.subtitle_settings["max_height"],
                    self.subtitle_settings,
                )
            logo = self._safe_open_image(self.logo_image)
            if logo is not None:
                canvas.paste(logo, (0, 0), logo)
            watermark = self._safe_open_image(self.watermark_image)
            if watermark is not None:
                canvas.paste(watermark, (0, 0), watermark)
            version_overlay = None
            if version and version in self.version_map:
                version_path = self.materials_dir / self.version_map[version]
                version_overlay = self._safe_open_image(version_path)
            if version_overlay is not None:
                canvas.paste(version_overlay, (0, 0), version_overlay)
            result = self._apply_color_adjustment(canvas)
            output_path = self.output_dir / f"{isbn}.jpg"
            result.save(output_path, format=self.output_format, quality=output_quality, optimize=True)
            return isbn, "Success", result
        except Exception as exc:
            return isbn, f"Error: {exc}", None

    def generate_all(
        self,
        excel_path: Path,
        output_quality: int,
        on_update: Optional[Callable[[int, int, int, str, str, Optional[Image.Image]], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> tuple[int, int]:
        df = self._read_excel(excel_path)
        total = len(df)
        success_count = 0
        failure_count = 0
        self.log_lines = []
        for index, row in df.iterrows():
            if stop_event and stop_event.is_set():
                break
            isbn, status, preview = self._generate_single(row, output_quality)
            if status == "Success":
                success_count += 1
            else:
                failure_count += 1
            self._log(isbn, status)
            if on_update:
                on_update(index + 1, total, success_count, isbn, status, preview)
        log_path = self.output_dir / "log.txt"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.log_lines))
        return success_count, failure_count


class CoverGeneratorApp(tk.Tk):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.title("电商主图批量生成器")
        self.base_dir = base_dir
        self.config_path = base_dir / "config.json"
        self.composer = ImageComposer(base_dir, self.config_path)
        self.stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.queue: queue.Queue = queue.Queue()
        self.preview_photo: Optional[ImageTk.PhotoImage] = None
        self._build_ui()
        self.after(100, self._process_queue)

    def _build_ui(self) -> None:
        left_frame = ttk.Frame(self, padding=12)
        left_frame.grid(row=0, column=0, sticky="nsew")
        center_frame = ttk.Frame(self, padding=12)
        center_frame.grid(row=0, column=1, sticky="nsew")
        right_frame = ttk.Frame(self, padding=12)
        right_frame.grid(row=0, column=2, sticky="nsew")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        ttk.Label(left_frame, text="Excel 文件:").grid(row=0, column=0, sticky="w")
        self.excel_var = tk.StringVar(value=str(self.composer.excel_file))
        self.excel_entry = ttk.Entry(left_frame, textvariable=self.excel_var, width=40)
        self.excel_entry.grid(row=1, column=0, sticky="ew")
        ttk.Button(left_frame, text="浏览", command=self._browse_excel).grid(row=1, column=1, padx=4)

        ttk.Label(left_frame, text="Cover 目录:").grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.cover_var = tk.StringVar(value=str(self.composer.cover_dir))
        self.cover_entry = ttk.Entry(left_frame, textvariable=self.cover_var, width=40)
        self.cover_entry.grid(row=3, column=0, sticky="ew")
        ttk.Button(left_frame, text="浏览", command=self._browse_cover_dir).grid(row=3, column=1, padx=4)

        ttk.Label(left_frame, text="素材目录:").grid(row=4, column=0, sticky="w", pady=(12, 0))
        self.materials_var = tk.StringVar(value=str(self.composer.materials_dir))
        self.materials_entry = ttk.Entry(left_frame, textvariable=self.materials_var, width=40)
        self.materials_entry.grid(row=5, column=0, sticky="ew")
        ttk.Button(left_frame, text="浏览", command=self._browse_materials_dir).grid(row=5, column=1, padx=4)

        ttk.Label(left_frame, text="输出目录:").grid(row=6, column=0, sticky="w", pady=(12, 0))
        self.output_var = tk.StringVar(value=str(self.composer.output_dir))
        self.output_entry = ttk.Entry(left_frame, textvariable=self.output_var, width=40)
        self.output_entry.grid(row=7, column=0, sticky="ew")
        ttk.Button(left_frame, text="浏览", command=self._browse_output_dir).grid(row=7, column=1, padx=4)

        ttk.Label(center_frame, text="生成控制", font=(None, 12, "bold")).grid(row=0, column=0, pady=(0, 8), sticky="w")
        self.start_button = ttk.Button(center_frame, text="开始生成", command=self.start_generation)
        self.start_button.grid(row=1, column=0, sticky="ew")
        self.stop_button = ttk.Button(center_frame, text="停止", command=self.stop_generation, state="disabled")
        self.stop_button.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        quality_frame = ttk.Frame(center_frame)
        quality_frame.grid(row=3, column=0, pady=(12, 0), sticky="ew")
        ttk.Label(quality_frame, text="JPG 质量: ").grid(row=0, column=0, sticky="w")
        self.quality_var = tk.IntVar(value=self.composer.output_quality)
        self.quality_slider = ttk.Scale(quality_frame, from_=10, to=100, variable=self.quality_var, orient="horizontal")
        self.quality_slider.grid(row=0, column=1, sticky="ew", padx=8)
        quality_frame.columnconfigure(1, weight=1)

        preview_label = ttk.Label(center_frame, text="当前预览:")
        preview_label.grid(row=4, column=0, sticky="w", pady=(12, 0))
        self.preview_canvas = ttk.Label(center_frame, relief="sunken", width=32)
        self.preview_canvas.grid(row=5, column=0, sticky="nsew", pady=(4, 0))
        center_frame.rowconfigure(5, weight=1)

        ttk.Label(right_frame, text="日志", font=(None, 12, "bold")).grid(row=0, column=0, sticky="w")
        self.log_text = tk.Text(right_frame, width=40, height=20, state="disabled")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        right_frame.rowconfigure(1, weight=1)

        stats_frame = ttk.Frame(right_frame)
        stats_frame.grid(row=2, column=0, pady=(8, 0), sticky="ew")
        self.status_var = tk.StringVar(value="准备就绪")
        self.stats_var = tk.StringVar(value="成功: 0 失败: 0")
        ttk.Label(stats_frame, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Label(stats_frame, textvariable=self.stats_var).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=0)

    def _browse_excel(self) -> None:
        path = filedialog.askopenfilename(title="选择 Excel 文件", filetypes=[("Excel 文件", "*.xlsx;*.xls")])
        if path:
            self.excel_var.set(path)

    def _browse_cover_dir(self) -> None:
        path = filedialog.askdirectory(title="选择 Cover 目录")
        if path:
            self.cover_var.set(path)

    def _browse_materials_dir(self) -> None:
        path = filedialog.askdirectory(title="选择素材目录")
        if path:
            self.materials_var.set(path)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_var.set(path)

    def start_generation(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        self.stop_event.clear()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("生成中...")
        self.stats_var.set("成功: 0 失败: 0")
        self.preview_canvas.config(image="")

        excel_path = Path(self.excel_var.get())
        self.composer.cover_dir = Path(self.cover_var.get())
        self.composer.materials_dir = Path(self.materials_var.get())
        self.composer.output_dir = Path(self.output_var.get())
        self.composer.output_dir.mkdir(parents=True, exist_ok=True)
        quality = int(self.quality_var.get())

        self.worker_thread = threading.Thread(
            target=self._run_generation,
            args=(excel_path, quality),
            daemon=True,
        )
        self.worker_thread.start()

    def stop_generation(self) -> None:
        self.stop_event.set()
        self.status_var.set("停止中...")
        self.stop_button.config(state="disabled")

    def _run_generation(self, excel_path: Path, quality: int) -> None:
        try:
            success, failure = self.composer.generate_all(
                excel_path=excel_path,
                output_quality=quality,
                on_update=self._queue_update,
                stop_event=self.stop_event,
            )
            if self.stop_event.is_set():
                self.queue.put(("finished", success, failure, True))
            else:
                self.queue.put(("finished", success, failure, False))
        except Exception as exc:
            self.queue.put(("error", str(exc)))

    def _queue_update(
        self,
        current: int,
        total: int,
        success_count: int,
        isbn: str,
        status: str,
        preview: Optional[Image.Image],
    ) -> None:
        self.queue.put(("update", current, total, success_count, status, preview))

    def _process_queue(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                if item[0] == "update":
                    _, current, total, success_count, status, preview = item
                    self._handle_progress(current, total, success_count, status, preview)
                elif item[0] == "finished":
                    _, success, failure, stopped = item
                    self._handle_finished(success, failure, stopped)
                elif item[0] == "error":
                    _, error_msg = item
                    self._handle_error(error_msg)
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    def _handle_progress(
        self,
        current: int,
        total: int,
        success_count: int,
        status: str,
        preview: Optional[Image.Image],
    ) -> None:
        percent = (current / total) * 100 if total else 0
        self.progress_var.set(percent)
        self.status_var.set(f"处理: {current}/{total} {status}")
        self.stats_var.set(f"成功: {success_count} 失败: {current - success_count}")
        if preview is not None:
            thumb = preview.copy()
            thumb.thumbnail((220, 220), Image.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(thumb)
            self.preview_canvas.config(image=self.preview_photo)
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"{status}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _handle_finished(self, success: int, failure: int, stopped: bool) -> None:
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        if stopped:
            self.status_var.set(f"已停止。成功: {success} 失败: {failure}")
            messagebox.showinfo("已停止", f"已停止生成。\n成功：{success} 张\n失败：{failure} 张")
        else:
            self.status_var.set("完成")
            messagebox.showinfo("完成", f"完成！\n成功：{success} 张\n失败：{failure} 张")

    def _handle_error(self, message: str) -> None:
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.status_var.set("错误")
        messagebox.showerror("错误", message)

    def on_close(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self.stop_event.set()
            self.worker_thread.join(timeout=2)
        self.destroy()


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    app = CoverGeneratorApp(base_dir)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()