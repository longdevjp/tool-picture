import os
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog
import os
import threading
import requests
from tkinter import *
from tkinter import filedialog
from tkinter.ttk import Progressbar
from urllib.parse import quote
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
import yt_dlp
import subprocess
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed


def is_video_url(url):
    return url.startswith("http") and not ("youtube.com" in url or "youtu.be" in url)


# ====================== TẢI ẢNH (NHANH GẤP NHIỀU LẦN) ======================
def fetch_and_save_image(img_url, count, output_dir, keyword, mode):
    try:
        img_data = requests.get(img_url, timeout=5).content
        img = Image.open(BytesIO(img_data))
        w, h = img.size

        # Lọc theo chế độ
        if (mode == 1 and w < 1280) or (mode == 2 and w < 1920):
            return False

        save_path = os.path.join(output_dir, f"{keyword.replace(' ', '_')}_{count}.jpg")
        img.save(save_path)
        return True
    except:
        return False


def download_images(keyword, output_dir, num_images, progress_callback, mode=0):
    headers = {"User-Agent": "Mozilla/5.0"}
    count = 0
    page = 0
    seen_urls = set()
    futures = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        while count < num_images:
            first = page * 35 + 1
            search_url = f"https://www.bing.com/images/search?q={quote(keyword)}&first={first}&form=HDRSC2"

            try:
                response = requests.get(search_url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, "html.parser")
                images = soup.find_all("a", {"class": "iusc"})

                if not images:
                    break

                for img_tag in images:
                    if count >= num_images:
                        break
                    try:
                        import json
                        m = json.loads(img_tag.get("m", "{}"))
                        img_url = m.get("murl")

                        if img_url and img_url not in seen_urls:
                            seen_urls.add(img_url)
                            count += 1
                            futures.append(executor.submit(fetch_and_save_image, img_url, count, output_dir, keyword, mode))
                    except:
                        continue
            except Exception as e:
                print(f"❌ Lỗi trang {page + 1}: {e}")
                break
            page += 1

        done = 0
        for f in as_completed(futures):
            if f.result():
                done += 1
                progress_callback(done, num_images)

    return done


# ====================== CẮT VIDEO CHÍNH XÁC THEO GIÂY ======================
def split_video_into_segments(video_path, output_dir, segment_duration=6):
    try:
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        segments_dir = os.path.join(output_dir, f"{video_name}_segments")
        os.makedirs(segments_dir, exist_ok=True)
        output_pattern = os.path.join(segments_dir, f"{video_name}_segment_%03d.mp4")

        # Dùng re-encode để cắt chính xác tuyệt đối
        cmd = [
            'ffmpeg', '-i', video_path,
            '-c:v', 'libx264', '-c:a', 'aac', '-b:a', '128k',
            '-f', 'segment',
            '-segment_time', str(segment_duration),
            '-reset_timestamps', '1',
            output_pattern,
            '-y'
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        segment_files = glob.glob(os.path.join(segments_dir, f"{video_name}_segment_*.mp4"))
        return len(segment_files), segments_dir

    except subprocess.CalledProcessError as e:
        print(f"Lỗi khi cắt video: {e}")
        return 0, None
    except Exception as e:
        print(f"Lỗi: {e}")
        return 0, None


# ====================== TẢI VIDEO ======================
def download_video(url, output_dir, progress_callback, result_callback, segment_duration):
    ydl_opts = {
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'progress_hooks': [progress_callback],
        'quiet': True,
        'no_warnings': True,
    }

    if 'youtube.com' in url or 'youtu.be' in url:
        result_callback("❌ Không hỗ trợ YouTube!", "red")
        return

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'video')
            ydl.download([url])

        video_files = []
        for ext in ['*.mp4', '*.avi', '*.mkv', '*.mov', '*.flv', '*.webm']:
            video_files.extend(glob.glob(os.path.join(output_dir, ext)))

        if video_files:
            latest_video = max(video_files, key=os.path.getctime)
            result_callback(f"✅ Video đã tải xong. Đang cắt thành các đoạn {segment_duration} giây...", "blue")
            segment_count, segments_dir = split_video_into_segments(latest_video, output_dir, segment_duration)

            if segment_count > 0:
                result_callback(f"✅ Hoàn thành! Đã cắt thành {segment_count} đoạn {segment_duration} giây\nLưu tại: {segments_dir}", "green")
            else:
                result_callback("✅ Video đã tải xong nhưng không thể cắt thành đoạn", "orange")
        else:
            result_callback("✅ Video đã tải xong", "green")

    except Exception as e:
        result_callback(f"❌ Lỗi tải video: {str(e)}", "red")


# ====================== CẬP NHẬT TIẾN TRÌNH ======================
def update_progress(count, total):
    progress_var.set(int((count / total) * 100))
    root.update_idletasks()


def video_progress_hook(d):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '').replace('%', '').strip()
        try:
            progress_var.set(float(percent))
            root.update_idletasks()
        except:
            pass


# ====================== BẮT ĐẦU TẢI ======================
def start_download():
    keyword = keyword_entry.get().strip()
    video_link = video_entry.get().strip()
    output_dir = output_folder_entry.get().strip()

    try:
        num_images = int(num_images_spinbox.get())
    except:
        result_label.config(text="❌ Số ảnh phải là số!", fg="red")
        return

    try:
        segment_duration = int(segment_duration_spinbox.get())
    except:
        result_label.config(text="❌ Thời lượng cắt video phải là số!", fg="red")
        return

    if not keyword and not video_link:
        result_label.config(text="❌ Vui lòng nhập từ khóa hoặc link!", fg="red")
        return
    if not output_dir:
        result_label.config(text="❌ Vui lòng chọn thư mục!", fg="red")
        return

    # Xác định chế độ lọc ảnh
    mode = 0
    if quality_hd_var.get():
        mode = 1
    if quality_fullhd_var.get():
        mode = 2

    os.makedirs(output_dir, exist_ok=True)
    result_label.config(text="🔄 Đang xử lý...", fg="blue")
    progress_var.set(0)

    def callback(msg, color):
        result_label.config(text=msg, fg=color)
        progress_var.set(100)

    def task():
        if keyword:
            result_label.config(text="🖼️ Đang tải ảnh...", fg="blue")
            downloaded = download_images(keyword, output_dir, num_images, update_progress, mode)
            if downloaded >= num_images:
                result_label.config(text=f"✅ Đã tải {downloaded} ảnh", fg="green")
            elif downloaded == 0:
                result_label.config(text="⚠️ Không tải được ảnh nào!", fg="orange")
            else:
                result_label.config(text=f"⚠️ Chỉ tải được {downloaded}/{num_images} ảnh.", fg="orange")

        if is_video_url(video_link):
            result_label.config(text=f"🎞️ Đang tải video:\n{video_link}", fg="blue")
            download_video(video_link, output_dir, video_progress_hook, callback, segment_duration)

    threading.Thread(target=task).start()


# ====================== CHỌN THƯ MỤC ======================
def browse_folder():
    folder = filedialog.askdirectory()
    if folder:
        output_folder_entry.delete(0, "end")
        output_folder_entry.insert(0, folder)


# ======================== CỬA SỔ CHÍNH ========================
root = ttk.Window(themename="cyborg")  # bạn có thể thử: flatly, minty, darkly...
root.title("📥 Download Tool - Image & Video Splitter")
root.geometry("600x690")
# root.resizable(False, False)

# ======================== TIÊU ĐỀ ========================
title_label = ttk.Label(
    root,
    text="📥 Image Downloader + Video Splitter",
    font=("Segoe UI", 14, "bold")
)
title_label.pack(pady=12)

frame_main = ttk.Frame(root, padding=15)
frame_main.pack(fill="both", expand=True)

# ======================== INPUT FIELD ========================
ttk.Label(frame_main, text="🖼️ Image Keyword:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
keyword_entry = ttk.Entry(frame_main, width=50)
keyword_entry.pack(pady=5)

ttk.Label(frame_main, text="🎞️ Video Link (TikTok, FB...):", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10,0))
video_entry = ttk.Entry(frame_main, width=50)
video_entry.pack(pady=5)

ttk.Label(frame_main, text="📷 Number of Images:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10,0))
num_images_spinbox = ttk.Spinbox(frame_main, from_=1, to=500, width=10)
num_images_spinbox.insert(0, "50")
num_images_spinbox.pack(pady=5)

ttk.Label(frame_main, text="⏱ Video Split Duration (seconds):", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10,0))
segment_duration_spinbox = ttk.Spinbox(frame_main, from_=1, to=60, width=10)
segment_duration_spinbox.insert(0, "6")
segment_duration_spinbox.pack(pady=5)

# ======================== CHỌN FOLDER ========================
ttk.Label(frame_main, text="📂 Save Folder:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10,0))
folder_frame = ttk.Frame(frame_main)
folder_frame.pack(fill="x")

output_folder_entry = ttk.Entry(folder_frame, width=45)
output_folder_entry.pack(side="left", padx=5)

def browse_folder():
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        output_folder_entry.delete(0, "end")
        output_folder_entry.insert(0, folder_selected)

ttk.Button(folder_frame, text="Browse", bootstyle=SECONDARY, command=browse_folder).pack(side="left")

# ======================== TÙY CHỌN CHẤT LƯỢNG ẢNH ========================
ttk.Label(frame_main, text="🔍 Image Quality Filter:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12,0))

quality_all_var = ttk.IntVar(value=1)
quality_hd_var = ttk.IntVar()
quality_fullhd_var = ttk.IntVar()

ttk.Checkbutton(frame_main, text="All Sizes", variable=quality_all_var).pack(anchor="w", padx=20)
ttk.Checkbutton(frame_main, text="HD ≥ 1280px", variable=quality_hd_var).pack(anchor="w", padx=20)
ttk.Checkbutton(frame_main, text="Full HD ≥ 1920px", variable=quality_fullhd_var).pack(anchor="w", padx=20)

# ======================== NÚT BẮT ĐẦU ========================
def start_download():
    keyword = keyword_entry.get().strip()
    video_link = video_entry.get().strip()
    folder = output_folder_entry.get().strip()
    num_images = num_images_spinbox.get()
    duration = segment_duration_spinbox.get()
    
    if not folder:
        result_label.config(text="⚠️ Please select a save folder first!")
        return
    
    result_label.config(
        text=f"✅ Ready!\n\nKeyword: {keyword}\nVideo: {video_link}\nImages: {num_images}\nSplit every {duration}s\nSave to: {folder}"
    )

start_button = ttk.Button(
    root,
    text="🚀 START DOWNLOAD",
    bootstyle=SUCCESS + OUTLINE,
    command=start_download
)
start_button.pack(pady=12, ipadx=10, ipady=5)

# ======================== THANH TIẾN TRÌNH ========================
progress_var = ttk.DoubleVar()
progress = ttk.Progressbar(root, variable=progress_var, maximum=100, bootstyle=INFO)
progress.pack(pady=8, fill="x", padx=20)

# ======================== KẾT QUẢ ========================
result_label = ttk.Label(root, text="", wraplength=550, justify="center", font=("Segoe UI", 10))
result_label.pack(pady=8)

ttk.Label(
    root,
    text="📝 Supports TikTok, Facebook, Twitter, etc.\n(YouTube not supported)",
    font=("Arial", 9),
    foreground="#c0c0c0"
).pack(pady=5)

# ======================== CHẠY APP ========================
root.mainloop()