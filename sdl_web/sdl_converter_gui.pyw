import os
import tkinter as tk
from tkinter import messagebox, ttk
import zstandard as zstd
import threading

class SdlConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SDL ↔ TXT Pro Converter")
        self.root.geometry("700x600")
        self.root.configure(bg="#f5f5f5")

        # State
        self.is_running = False
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Header
        header = tk.Frame(root, bg="#00796B", height=70)
        header.pack(fill="x")
        tk.Label(header, text="SDL ↔ TXT Advanced Converter", bg="#00796B", fg="white", 
                 font=('Segoe UI', 16, 'bold'), pady=20).pack()

        # Main Container
        main_frame = tk.Frame(root, bg="#f5f5f5", padx=30, pady=20)
        main_frame.pack(fill="both", expand=True)

        # Mode Selection
        mode_frame = tk.LabelFrame(main_frame, text=" 1. Select Mode ", bg="#f5f5f5", font=('Segoe UI', 10, 'bold'), padx=15, pady=15)
        mode_frame.pack(fill="x", pady=(0, 15))
        
        self.mode_var = tk.StringVar(value="sdl_to_txt")
        tk.Radiobutton(mode_frame, text="SDL ➔ TXT (Extract)", variable=self.mode_var, 
                       value="sdl_to_txt", bg="#f5f5f5", font=('Segoe UI', 10)).pack(side="left", padx=(0, 30))
        tk.Radiobutton(mode_frame, text="TXT ➔ SDL (Compress)", variable=self.mode_var, 
                       value="txt_to_sdl", bg="#f5f5f5", font=('Segoe UI', 10)).pack(side="left")

        # Options
        opt_frame = tk.LabelFrame(main_frame, text=" 2. Options ", bg="#f5f5f5", font=('Segoe UI', 10, 'bold'), padx=15, pady=15)
        opt_frame.pack(fill="x", pady=(0, 15))
        
        # Compression Row
        comp_row = tk.Frame(opt_frame, bg="#f5f5f5")
        comp_row.pack(fill="x", pady=5)
        tk.Label(comp_row, text="Compression Level (1-22):", bg="#f5f5f5", font=('Segoe UI', 10)).pack(side="left")
        self.level_var = tk.IntVar(value=7)
        self.slider = tk.Scale(comp_row, from_=1, to_=22, orient="horizontal", 
                               variable=self.level_var, bg="#f5f5f5", length=250, relief="flat", highlightthickness=0)
        self.slider.pack(side="left", padx=20)
        
        # Cleanup Row
        self.cleanup_var = tk.BooleanVar(value=True)
        self.cleanup_cb = tk.Checkbutton(opt_frame, text="Auto-delete original files after successful conversion", 
                                       variable=self.cleanup_var, bg="#f5f5f5", font=('Segoe UI', 10))
        self.cleanup_cb.pack(anchor="w", pady=(10, 0))

        # Progress Section
        prog_frame = tk.Frame(main_frame, bg="#f5f5f5")
        prog_frame.pack(fill="x", pady=10)
        
        self.status_var = tk.StringVar(value="Ready to begin...")
        tk.Label(prog_frame, textvariable=self.status_var, fg="#333", font=('Segoe UI', 10, 'bold')).pack(anchor="w")
        
        self.progress = ttk.Progressbar(prog_frame, orient="horizontal", length=100, mode="determinate")
        self.progress.pack(fill="x", pady=5)

        # Log Area
        log_frame = tk.LabelFrame(main_frame, text=" Activity Log ", bg="#f5f5f5", font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        log_frame.pack(fill="both", expand=True, pady=10)
        
        self.log_text = tk.Text(log_frame, height=8, font=('Consolas', 10), bg="white", relief="flat", padx=10, pady=10)
        self.log_text.pack(fill="both", expand=True)
        # Scrollbar for log
        scrollbar = tk.Scrollbar(self.log_text)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.log_text.yview)

        # Start Button
        self.start_btn = tk.Button(main_frame, text="🚀 START PROCESSING", command=self.start_process,
                                   bg="#00796B", fg="white", font=('Segoe UI', 12, 'bold'), 
                                   relief="flat", pady=15, cursor="hand2")
        self.start_btn.pack(fill="x", pady=10)

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def start_process(self):
        if self.is_running: return
        self.is_running = True
        self.start_btn.config(state="disabled", text="PROCESSING...", bg="#B2DFDB")
        self.log(f"--- Starting: {self.mode_var.get().replace('_', ' ').upper()} ---")
        
        thread = threading.Thread(target=self.run_conversion_cycle, daemon=True)
        thread.start()

    def run_conversion_cycle(self):
        try:
            mode = self.mode_var.get()
            level = self.level_var.get()
            cleanup = self.cleanup_var.get()
            
            items = os.listdir(self.base_dir)
            folders = [d for d in items if os.path.isdir(os.path.join(self.base_dir, d))]
            
            if not folders:
                self.log("⚠️ No subfolders found in current directory.")
                self.finish()
                return

            total_folders = len(folders)
            processed_count = 0
            
            for i, folder in enumerate(folders):
                folder_path = os.path.join(self.base_dir, folder)
                self.status_var.set(f"Processing ({i+1}/{total_folders}): {folder}")
                self.progress["value"] = (i / total_folders) * 100
                self.root.update_idletasks() # Refresh UI
                
                try:
                    if mode == "sdl_to_txt":
                        sdl_files = [f for f in os.listdir(folder_path) if f.endswith('.sdl')]
                        for sdl_file in sdl_files:
                            file_path = os.path.join(folder_path, sdl_file)
                            with open(file_path, 'rb') as f:
                                if f.read(4) != b'SDL\x03': continue
                                data = f.read()
                                dctx = zstd.ZstdDecompressor()
                                text = dctx.decompress(data).decode('utf-8')
                                
                                out_path = os.path.join(folder_path, folder + ".txt")
                                with open(out_path, 'w', encoding='utf-8') as out_f:
                                    out_f.write(text)
                            
                            if cleanup: os.remove(file_path)
                            self.log(f"✅ Extracted & Cleaned: {folder}")
                            processed_count += 1
                    
                    else: # txt_to_sdl
                        txt_files = [f for f in sorted(os.listdir(folder_path)) 
                                    if f.endswith('.txt') and f.lower() != 'metadata.txt']
                        
                        if txt_files:
                            text_parts = []
                            paths_to_delete = []
                            for txt_file in txt_files:
                                fpath = os.path.join(folder_path, txt_file)
                                with open(fpath, 'r', encoding='utf-8') as f:
                                    text_parts.append(f.read())
                                paths_to_delete.append(fpath)
                            
                            if text_parts:
                                combined = '\n'.join(text_parts)
                                sdl_data = bytearray(b'SDL\x03')
                                cctx = zstd.ZstdCompressor(level=level)
                                sdl_data.extend(cctx.compress(combined.encode('utf-8')))
                                
                                out_path = os.path.join(folder_path, folder + ".sdl")
                                with open(out_path, 'wb') as out_f:
                                    out_f.write(sdl_data)
                                
                                if cleanup:
                                    for p in paths_to_delete: 
                                        try: os.remove(p)
                                        except: pass
                                
                                self.log(f"✅ Compressed: {folder}")
                                processed_count += 1
                                
                except Exception as e:
                    self.log(f"❌ Error in {folder}: {str(e)}")

            self.progress["value"] = 100
            self.status_var.set(f"Completed! {processed_count} items handled.")
            self.log(f"\n--- Process Finished ({processed_count} successes) ---")
            messagebox.showinfo("Success", f"Task complete!\nProcessed {processed_count} items.")
            
        except Exception as e:
            self.log(f"FATAL ERROR: {str(e)}")
        finally:
            self.finish()

    def finish(self):
        self.is_running = False
        self.start_btn.config(state="normal", text="🚀 START PROCESSING", bg="#00796B")

if __name__ == "__main__":
    root = tk.Tk()
    app = SdlConverterApp(root)
    root.mainloop()
