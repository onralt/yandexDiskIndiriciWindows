import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import requests
import os
import threading
import re  # Windows dosya ismi temizliği için gerekli
from concurrent.futures import ThreadPoolExecutor, as_completed

class YandexDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Yandex Disk PDF İndirici (Windows Uyumlu)")
        self.root.geometry("650x550")

        # --- Değişkenler ---
        self.public_key_var = tk.StringVar(value="https://disk.yandex.az/d/1GZu02HxxW5HEQ")
        self.save_folder_var = tk.StringVar(value=os.path.join(os.getcwd(), "indirilen_pdfler"))
        self.is_running = False

        # --- Arayüz Elemanları ---

        # 1. Yandex Linki
        lbl_link = tk.Label(root, text="Yandex Disk Public Link:", font=("Segoe UI", 10, "bold"))
        lbl_link.pack(pady=(10, 0), anchor="w", padx=10)

        entry_link = tk.Entry(root, textvariable=self.public_key_var, width=80)
        entry_link.pack(pady=5, padx=10)

        # 2. Kayıt Klasörü Seçimi
        lbl_folder = tk.Label(root, text="Kaydedilecek Klasör:", font=("Segoe UI", 10, "bold"))
        lbl_folder.pack(pady=(10, 0), anchor="w", padx=10)

        frame_folder = tk.Frame(root)
        frame_folder.pack(pady=5, padx=10, fill="x")

        entry_folder = tk.Entry(frame_folder, textvariable=self.save_folder_var)
        entry_folder.pack(side="left", fill="x", expand=True)

        btn_browse = tk.Button(frame_folder, text="Seç...", command=self.select_folder)
        btn_browse.pack(side="right", padx=(5, 0))

        # 3. Başlat Butonu
        self.btn_start = tk.Button(root, text="İndirmeyi Başlat", bg="#4CAF50", fg="black",
                                   font=("Segoe UI", 11, "bold"),
                                   command=self.start_thread)
        self.btn_start.pack(pady=15, ipadx=10, ipady=5)

        # 4. İlerleme Çubuğu (Progress Bar)
        self.progress = ttk.Progressbar(root, orient="horizontal", length=600, mode="determinate")
        self.progress.pack(pady=5)

        self.lbl_status = tk.Label(root, text="Hazır", fg="gray", font=("Segoe UI", 9))
        self.lbl_status.pack(pady=2)

        # 5. Log Ekranı
        self.log_area = scrolledtext.ScrolledText(root, width=80, height=15, state='disabled', font=("Consolas", 9))
        self.log_area.pack(pady=10, padx=10)

    def clean_filename(self, filename):
        """
        Windows dosya isimlerinde yasaklı olan karakterleri (< > : " / \ | ? *)
        alt çizgi (_) ile değiştirir. Başına 'r' koyarak SyntaxWarning engellendi.
        """
        return re.sub(r'[<>:"/\\|?*]', '_', filename)

    def select_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.save_folder_var.set(folder_selected)

    def log(self, message):
        """Log ekranına yazı yazar."""
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)  # En sona kaydır
        self.log_area.config(state='disabled')

    def start_thread(self):
        """Arayüz donmasın diye işlemi ayrı thread'de başlatır."""
        if self.is_running:
            return

        self.is_running = True
        self.btn_start.config(state="disabled", text="İşleniyor...")
        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)  # Ekranı temizle
        self.log_area.config(state='disabled')

        # İşlemi başlatan thread
        threading.Thread(target=self.run_download_process, daemon=True).start()

    def run_download_process(self):
        public_key = self.public_key_var.get()
        save_folder = self.save_folder_var.get()

        list_url = "https://cloud-api.yandex.net/v1/disk/public/resources"
        download_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"

        try:
            os.makedirs(save_folder, exist_ok=True)
            self.log(f"📁 Klasör ayarlandı: {save_folder}")
            self.lbl_status.config(text="Dosya listesi çekiliyor...")

            # --- 1) DOSYALARI LİSTELE ---
            limit = 100
            offset = 0
            pdf_files = []

            while True:
                params = {
                    "public_key": public_key,
                    "limit": limit,
                    "offset": offset
                }

                self.log(f"🔍 Liste taranıyor... (Offset: {offset})")

                try:
                    response = requests.get(list_url, params=params)
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    self.log(f"❌ Ağ/API Hatası: {e}")
                    break

                data = response.json()

                if "_embedded" not in data:
                    self.log("❌ Hata: Dosya listesi alınamadı (Link hatalı olabilir).")
                    break

                items = data["_embedded"]["items"]
                if not items:
                    break

                for item in items:
                    if item["name"].lower().endswith(".pdf"):
                        pdf_files.append(item)

                offset += limit

            total_files = len(pdf_files)
            self.log(f"✅ Toplam bulunan PDF sayısı: {total_files}")

            # Thread içinden GUI güncellemesi yaparken dikkatli olunmalı,
            # ancak basit label güncellemeleri genelde sorun çıkarmaz.
            self.lbl_status.config(text=f"İndirilecek: {total_files} dosya")

            if total_files == 0:
                self.finish_process()
                return

            # Progress Bar Ayarı
            self.progress["maximum"] = total_files
            self.progress["value"] = 0

            # --- 2) & 3) İNDİRME İŞLEMİ ---
            self.lbl_status.config(text="İndirme işlemi başladı...")

            completed_count = 0
            max_threads = 8

            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = {executor.submit(self.download_single_pdf, item, public_key, download_url, save_folder): item
                           for item in pdf_files}

                for future in as_completed(futures):
                    result = future.result()
                    self.log(result)

                    # Progress bar güncelle
                    completed_count += 1
                    self.progress["value"] = completed_count
                    self.lbl_status.config(text=f"İndiriliyor: {completed_count}/{total_files}")

            self.log("🎉 Tüm işlemler tamamlandı.")
            messagebox.showinfo("Başarılı", f"Toplam {total_files} dosya indirildi.")

        except Exception as e:
            self.log(f"💥 Beklenmeyen hata: {str(e)}")
            messagebox.showerror("Hata", str(e))

        finally:
            self.finish_process()

    def download_single_pdf(self, item, public_key, base_dl_url, save_folder):
        try:
            raw_name = item["name"]
            path = item["path"]

            # --- WINDOWS UYUMLULUK DÜZELTMESİ BURADA ---
            safe_name = self.clean_filename(raw_name)

            params = {"public_key": public_key, "path": path}

            # İndirme linkini al
            dl_req = requests.get(base_dl_url, params=params)
            if dl_req.status_code != 200:
                return f"❌ Link alınamadı: {safe_name}"

            dl_json = dl_req.json()
            if "href" not in dl_json:
                return f"❌ İndirme adresi yok: {safe_name}"

            file_url = dl_json["href"]

            # Dosyayı indir
            r = requests.get(file_url, stream=True, timeout=60)  # Timeout artırıldı

            full_path = os.path.join(save_folder, safe_name)

            with open(full_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            return f"✔ İndirildi: {safe_name}"

        except Exception as e:
            return f"❌ Hata: {item.get('name', '???')} -> {e}"

    def finish_process(self):
        self.is_running = False
        self.btn_start.config(state="normal", text="İndirmeyi Başlat")
        self.lbl_status.config(text="İşlem bitti.")


if __name__ == "__main__":
    root = tk.Tk()
    app = YandexDownloaderApp(root)
    root.mainloop()