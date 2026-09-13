# Ball Renderer Studio V2

โปรแกรม Windows สำหรับพรีวิวและเรนเดอร์วิดีโอฟิสิกส์ลูกบอล พร้อมเสียง รูปภาพ และแพทเทิร์น JSON รองรับโหมด Circle Battle, Spikes, Open Ring, Trail Draw, Merge Ball และ Ball Drop Shatter

## เริ่มใช้งาน

1. ติดตั้ง Python 3.10 ขึ้นไปและ FFmpeg
2. วางโปรเจกต์ในพาธสั้น เช่น `C:\BallRenderer_UI` เพื่อเลี่ยงปัญหา Windows Long Path
3. ดับเบิลคลิก **`RUN.bat`** เพื่อสร้าง `.venv`, ติดตั้งไลบรารี และเปิด Studio อัตโนมัติ

เปิดด้วยคำสั่งได้เช่นกัน:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe studio.py
```

ไฟล์วิดีโออยู่ใน `output` หรือพาธที่เลือกในโปรแกรม

## FFmpeg

```powershell
winget install Gyan.FFmpeg
```

โปรแกรมค้นหาจาก `PATH`, ตัวแปร `FFMPEG_EXE` และโฟลเดอร์ Downloads อัตโนมัติ

## โหมด

- **Circle Battle / Spikes / Open Ring / Trail Draw** — บอลเด้งในวงกลม ช่องเปิด หนาม การแตกตัว และเสียง
- **Merge Ball** — บอลตกและรวมระดับ พร้อมเสียง Merge และ Victory
- **Ball Drop Shatter** — บอลตกใส่หนาม แตกเป็นโฟม เลือกรูปและเสียง ตั้งสคริปต์ขนาด และจำกัดก้อนฟิสิกส์ได้

## ค่าที่แนะนำ

| ค่า | แนะนำ |
|---|---:|
| ความละเอียด | 1080 × 1920 |
| FPS | 60 |
| ระยะเวลา | 30 วินาที |
| โฟมคำนวณจริงสูงสุด | 300–600 |
| ลบโฟมเมื่อถึงพื้น | เปิด |

ถ้าเรนเดอร์ช้า ให้ลด FPS เป็น 60 ลดโฟมคำนวณจริงเป็น 300–400 และเปิดลบโฟมเมื่อถึงพื้น

## โครงสร้าง

```text
RUN.bat             เปิดโปรแกรมและติดตั้งอัตโนมัติ
studio.py           จุดเริ่ม UI
main.py             Renderer โหมดวงกลม
ui/                 Studio V2
engines/            เอนจิน Circle, Merge และ Drop
audio/              ระบบเสียง
render/             FFmpeg และการส่งออก
patterns/           แพทเทิร์น JSON
melodies/           เมโลดี้
tests/               ชุดทดสอบ
```

## ทดสอบ

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## สร้าง EXE

ดับเบิลคลิก `build_exe.bat` ผลลัพธ์อยู่ที่ `dist\BallRenderer.exe`
