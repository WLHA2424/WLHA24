# 텔레그램 채널-그룹 메시지 전달 봇

비공개 텔레그램 채널에 올라온 메시지를 특정 그룹으로 주기적으로 전달하는 봇입니다.

## 기능

- 비공개 채널의 메시지를 자동으로 감지
- 기존 메시지를 10분 간격으로 무한 반복 전송
- 새 메시지는 즉시 전송
- 한번 전송한 메시지는 1시간 동안 재전송하지 않음

## 설치

```bash
pip install -r requirements.txt
```

## 설정

`.env` 파일을 생성하고 다음 내용을 입력:

```
BOT_TOKEN=your_bot_token
SOURCE_CHANNEL_ID=your_channel_id
TARGET_GROUP_ID=your_group_id
SEND_INTERVAL_HOURS=0
SEND_INTERVAL_MINUTES=1
```

## 실행

```bash
python bot.py
```
