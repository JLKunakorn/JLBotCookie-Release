# JLmain V2.0.0 Premium - Build EXE

โฟลเดอร์นี้เป็นชุด staging สำหรับ build exe ลูกค้าเท่านั้น

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\build_release.ps1
```

ไฟล์ผลลัพธ์จะอยู่ที่:

```text
dist\JLmain_V2.0.0_Premium.exe
dist\JLmain_V2.0.0_Premium.zip
```

## ข้อสำคัญ

- ห้ามใส่ไฟล์ secret หรือไฟล์ระบบหลังบ้านเข้ามาในโฟลเดอร์นี้
- `license_config.json` ในโฟลเดอร์นี้เป็น config สำหรับ release
- สคริปต์ build ไม่ฝังไฟล์ `.py` เป็น data ใน exe
- ก่อนปล่อยใหัรัน tests, ตรวจ ZIP และทดสอบเปิด EXE ทุกครั้ง
