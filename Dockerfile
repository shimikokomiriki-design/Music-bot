FROM python:3.11-slim

WORKDIR /app

# ติดตั้ง ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# คัดลอกไฟล์ทั้งหมดเข้า container
COPY . .

# ติดตั้ง python packages
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
