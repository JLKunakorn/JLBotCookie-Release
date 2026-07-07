# JLmain V1.0.2 Premium - Build EXE

โฟลเดอร์นี้เป็นชุด staging สำหรับ build exe ลูกค้าเท่านั้น

## Build

```bat
build_exe.bat
```

ไฟล์ผลลัพธ์จะอยู่ที่:

```bat
dist\JLmain_V1.0.2_Premium.exe
```

## ข้อสำคัญ

- ห้ามใส่ไฟล์ secret หรือไฟล์ระบบหลังบ้านเข้ามาในโฟลเดอร์นี้
- `license_config.json` ในโฟลเดอร์นี้เป็น config สำหรับ release
- สคริปต์ build ไม่ฝังไฟล์ `.py` เป็น data ใน exe แล้ว
- หลัง build ให้ทดสอบ license popup, countdown, start/stop และ emulator selection อีกครั้ง

