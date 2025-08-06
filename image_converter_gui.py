"""
image_converter_gui_threaded.py
Image Batch Converter using CustomTkinter + Pillow + ThreadPoolExecutor for parallel conversion.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, UnidentifiedImageError

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}

class ImageConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Image Batch Converter (Threaded)")
        self.geometry("760x420")
        self.resizable(False, False)

        self.input_folder = ""
        self.output_folder = ""
        self.output_format = ctk.StringVar(value="jpg")
        self.overwrite = ctk.BooleanVar(value=False)
        self.recursive = ctk.BooleanVar(value=False)
        self.num_workers = ctk.IntVar(value=6)

        self._lock = threading.Lock()
        self._total_files = 0
        self._processed = 0
        self._converted = 0
        self._skipped = 0
        self._errors = 0

        self._create_widgets()

    def _create_widgets(self):
        pad = 12
        title = ctk.CTkLabel(self, text="Image Batch Converter (Parallel)", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(pady=(12, 6))

        frame = ctk.CTkFrame(self)
        frame.pack(padx=pad, pady=(8, 12), fill="x")

        in_row = ctk.CTkFrame(frame)
        in_row.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(in_row, text="Input folder:", width=110, anchor="w").pack(side="left", padx=(0,8))
        self.in_path_entry = ctk.CTkEntry(in_row, placeholder_text="No folder selected")
        self.in_path_entry.pack(side="left", expand=True, fill="x", padx=(0,8))
        ctk.CTkButton(in_row, text="Browse", width=90, command=self.select_input_folder).pack(side="left")

        out_row = ctk.CTkFrame(frame)
        out_row.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(out_row, text="Output folder:", width=110, anchor="w").pack(side="left", padx=(0,8))
        self.out_path_entry = ctk.CTkEntry(out_row, placeholder_text="(leave empty = same as input)")
        self.out_path_entry.pack(side="left", expand=True, fill="x", padx=(0,8))
        ctk.CTkButton(out_row, text="Browse", width=90, command=self.select_output_folder).pack(side="left")

        opts = ctk.CTkFrame(frame)
        opts.pack(fill="x", padx=10, pady=8)

        left_opts = ctk.CTkFrame(opts)
        left_opts.pack(side="left", padx=(0,16))
        ctk.CTkLabel(left_opts, text="Output format:", anchor="w").pack(anchor="w")
        ctk.CTkRadioButton(left_opts, text="JPG", variable=self.output_format, value="jpg").pack(anchor="w", pady=2)
        ctk.CTkRadioButton(left_opts, text="PNG", variable=self.output_format, value="png").pack(anchor="w", pady=2)

        mid_opts = ctk.CTkFrame(opts)
        mid_opts.pack(side="left", padx=(12,16))
        ctk.CTkLabel(mid_opts, text="Threads (workers):", anchor="w").pack(anchor="w")
        self.workers_spin = ctk.CTkSlider(mid_opts, from_=1, to=12, number_of_steps=11, command=self._on_workers_change)
        self.workers_spin.set(self.num_workers.get())
        self.workers_spin.pack(fill="x", pady=6)
        self.workers_label = ctk.CTkLabel(mid_opts, text=f"{self.num_workers.get()} workers")
        self.workers_label.pack(anchor="w")

        right_opts = ctk.CTkFrame(opts)
        right_opts.pack(side="left")
        ctk.CTkCheckBox(right_opts, text="Overwrite existing files", variable=self.overwrite).pack(anchor="w", pady=4)
        ctk.CTkCheckBox(right_opts, text="Recursive (include subfolders)", variable=self.recursive).pack(anchor="w", pady=4)

        action = ctk.CTkFrame(self)
        action.pack(fill="x", padx=pad, pady=(6,12))

        self.convert_btn = ctk.CTkButton(action, text="Start Conversion", command=self.start_conversion, height=44)
        self.convert_btn.pack(side="left", padx=(20,10))

        self.progress = ctk.CTkProgressBar(action, width=520)
        self.progress.pack(side="left", padx=(6,20), fill="x", expand=True)

        status_frame = ctk.CTkFrame(self)
        status_frame.pack(fill="both", padx=pad, pady=(0,12), expand=True)
        self.status_label = ctk.CTkLabel(status_frame, text="Ready", anchor="w")
        self.status_label.pack(fill="x", padx=12, pady=(8,4))
        self.log_text = ctk.CTkTextbox(status_frame, width=720, height=140, state="normal")
        self.log_text.pack(padx=12, pady=(0,12), fill="both", expand=True)
        self.log_text.insert("0.0", "Logs will appear here...\n")
        self.log_text.configure(state="disabled")

    def _on_workers_change(self, value):
        n = int(round(value))
        self.num_workers.set(n)
        self.workers_label.configure(text=f"{n} workers")

    def select_input_folder(self):
        folder = filedialog.askdirectory(title="Select input folder")
        if folder:
            self.input_folder = folder
            self.in_path_entry.delete(0, "end")
            self.in_path_entry.insert(0, folder)

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_folder = folder
            self.out_path_entry.delete(0, "end")
            self.out_path_entry.insert(0, folder)

    def start_conversion(self):
        in_path = self.in_path_entry.get().strip()
        out_path = self.out_path_entry.get().strip()
        if not in_path:
            messagebox.showwarning("No input folder", "Please select an input folder.")
            return
        if out_path:
            self.output_folder = out_path
        else:
            self.output_folder = ""

        with self._lock:
            self._total_files = 0
            self._processed = 0
            self._converted = 0
            self._skipped = 0
            self._errors = 0

        self.convert_btn.configure(state="disabled")
        self.workers_spin.configure(state="disabled")
        self.progress.set(0)
        self._log("Counting files...")

        bg = threading.Thread(target=self._prepare_and_run, args=(in_path,), daemon=True)
        bg.start()

    def _prepare_and_run(self, in_path):

        files = []
        if self.recursive.get():
            for root, dirs, filenames in os.walk(in_path):
                for fn in filenames:
                    if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTS:
                        files.append(os.path.join(root, fn))
        else:
            for fn in os.listdir(in_path):
                p = os.path.join(in_path, fn)
                if os.path.isfile(p) and os.path.splitext(fn)[1].lower() in SUPPORTED_EXTS:
                    files.append(p)

        total = len(files)
        if total == 0:
            self._done("No supported images found.")
            return

        with self._lock:
            self._total_files = total

        self._log(f"Found {total} images. Using {self.num_workers.get()} workers. Starting...")

        max_workers = max(1, int(self.num_workers.get()))
        futures = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for fpath in files:
                futures.append(executor.submit(self._process_single_image, fpath, in_path))

            for future in as_completed(futures):

                with self._lock:
                    self._processed += 1
                    processed = self._processed
                    converted = self._converted
                    skipped = self._skipped
                    errors = self._errors
                    total_now = self._total_files

                frac = processed / total_now
                self.after(0, lambda f=frac: self.progress.set(f))
                self._update_status(f"Processed {processed}/{total_now} — Converted: {converted} — Skipped: {skipped} — Errors: {errors}")

        summary = f"Done. Converted: {self._converted} / {self._total_files}. Skipped: {self._skipped}. Errors: {self._errors}."
        self._done(summary)

    def _process_single_image(self, file_path, input_root):
        """
        Convert one image file to desired format. Runs in worker threads.
        """
        out_fmt = self.output_format.get().lower()  
        try:

            base_name = os.path.splitext(os.path.basename(file_path))[0]
            new_name = base_name + "." + out_fmt

            if self.output_folder:

                if self.recursive.get():
                    rel = os.path.relpath(os.path.dirname(file_path), input_root)
                    target_dir = os.path.join(self.output_folder, rel)
                else:
                    target_dir = self.output_folder
            else:
                target_dir = os.path.dirname(file_path)

            os.makedirs(target_dir, exist_ok=True)
            new_path = os.path.join(target_dir, new_name)

            if os.path.exists(new_path) and not self.overwrite.get():
                with self._lock:
                    self._skipped += 1
                self._log(f"Skipped (exists): {new_path}")
                return

            with Image.open(file_path) as img:

                src_format = img.format.lower() if img.format else ""
                if src_format == out_fmt and not self.overwrite.get():
                    with self._lock:
                        self._skipped += 1
                    self._log(f"Skipped (already {out_fmt}): {file_path}")
                    return

                if out_fmt == "jpg":

                    if img.mode != "RGB":
                        try:
                            img = img.convert("RGB")
                        except Exception:

                            img = img.convert("RGB")
                    save_kwargs = {"format": "JPEG", "quality": 100, "optimize": False}
                    img.save(new_path, **save_kwargs)
                else:  

                    save_kwargs = {"format": "PNG"}
                    img.save(new_path, **save_kwargs)

            with self._lock:
                self._converted += 1
            self._log(f"Converted: {file_path} -> {new_path}")

        except UnidentifiedImageError:
            with self._lock:
                self._errors += 1
            self._log(f"Skipped (not an image or unreadable): {file_path}")
        except Exception as e:
            with self._lock:
                self._errors += 1
            self._log(f"Error converting {file_path}: {e}")

    def _update_status(self, text):

        self.after(0, lambda: self.status_label.configure(text=text))

    def _log(self, text):

        self.after(0, lambda: self._append_log(text))

    def _append_log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    def _done(self, text):

        self.after(0, lambda: self.convert_btn.configure(state="normal"))
        self.after(0, lambda: self.workers_spin.configure(state="normal"))
        self.after(0, lambda: self.status_label.configure(text=text))

        def show_popup():
            popup = ctk.CTkToplevel(self)
            popup.title("Conversion Finished")
            popup.geometry("360x130")
            popup.resizable(False, False)

            self_x = self.winfo_x()
            self_y = self.winfo_y()
            popup.geometry(f"+{self_x + 200}+{self_y + 150}")

            label = ctk.CTkLabel(
                popup,
                text=text,
                wraplength=300,
                font=ctk.CTkFont(size=14),
                justify="center"
            )
            label.pack(pady=(20, 10), padx=20)

            close_btn = ctk.CTkButton(
                popup,
                text="OK",
                command=popup.destroy,
                width=80
            )
            close_btn.pack(pady=(10, 20))

            popup.transient(self)  
            popup.grab_set()       

        self.after(0, show_popup)

if __name__ == "__main__":
    app = ImageConverterApp()
    app.mainloop()