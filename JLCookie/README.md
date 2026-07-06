# JLmain - V1.0 Premium

โปรเจคนี้รันจาก source ที่แก้ไขได้แล้ว ทั้ง GUI และ bot engine

## วิธีใช้

รันจาก source:

```bat
python run.py
```

หรือดับเบิลคลิก:

```bat
run.bat
```

build exe ใหม่:

```bat
build_exe.bat
```

## Dependencies

ต้องใช้ Python 3.12 และแพ็กเกจหลัก:

```bat
pip install opencv-python numpy keyboard pyinstaller customtkinter
```

`customtkinter` ควรเป็นเวอร์ชัน 5.2 ขึ้นไป

ถ้าจะเปิดระบบ license/key ให้ติดตั้งเพิ่ม:

```bat
pip install cryptography
```

## ไฟล์หลัก

| ไฟล์ | รายละเอียด |
| --- | --- |
| `JLmain.py` | GUI ใหม่ด้วย CustomTkinter ธีมช็อกโกแลตเข้ม |
| `bot.py` | เอนจิ้นบอท State Machine + ADB + OpenCV |
| `run.py` / `run.bat` | ตัวรันจาก source |
| `build_exe.bat` | ตัว build exe ด้วย PyInstaller |
| `license_core.py` | client ระบบ key แบบ online verify + signed token cache |
| `license_config.json.example` | ตัวอย่าง config สำหรับเปิดระบบ key ตอน build ตัวขายจริง |
| `license_server/cloudflare/` | Worker + D1 schema สำหรับ license server แบบ stock key |
| `tools/make_license_keypair.py` | ตัวสร้าง Ed25519 keypair สำหรับ server/client |
| `assets/app.ico` | ไอคอนโปรแกรม Windows |
| `templates/ui/jlbot_face.png` | มาสคอตใน banner ของ GUI |
| `templates/` | รูป template สำหรับ OpenCV |
| `adb_bundle/` | adb สำรองที่ bundle มากับโปรแกรม |

## สถานะ GUI

GUI ใหม่ใช้ CustomTkinter และไม่มีเครดิตผู้ทำเดิมในหน้าจอแล้ว เหลือเฉพาะชื่อแอปกับเวอร์ชัน:

- `V1.0 Premium`
- มาสคอต `JL Bot Cookie`
- เลือกอีมูเลเตอร์และ instance
- ตั้งค่าขั้นสูงแบบยุบ/ขยาย
- สวิตช์ตัวเลือกการเล่น
- ปุ่มเริ่ม/หยุดขนาดใหญ่
- แถบเหรียญ
- log panel

## Build Note

ตอน build exe ต้องเก็บ assets ของ CustomTkinter ด้วย:

```bat
--collect-all customtkinter
--collect-all darkdetect
--icon assets\app.ico
```

ไฟล์ `build_exe.bat` ตั้งค่านี้ไว้แล้ว

## License Note

ค่าเริ่มต้นยังเป็น dev mode เพื่อไม่ให้พังระหว่างพัฒนา ถ้าจะทำตัวขายจริงให้:

1. deploy `license_server/cloudflare`
2. copy `license_config.release.json` เป็น `license_config.json`
3. ใส่ `api_url`, `public_key_hex`, และตั้ง `required` เป็น `true`
4. build exe ใหม่ แล้วค่อยแจก

ฝั่ง server ใช้แนวทาง stock key: mint key เก็บไว้ก่อน แล้วเรียก `/api/admin/deliver` หรือ `/api/admin/deliver-key` หลังร้านเช็คการจ่ายเงินผ่าน เวลาของ key จะเริ่มนับตอน delivery API สำเร็จ
