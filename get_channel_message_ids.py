"""
채널에 있는 메시지 ID를 가져오는 스크립트
사용 방법:
1. 이 스크립트를 실행
2. 채널에 메시지를 하나 보냄
3. 출력된 메시지 ID를 message_ids.txt에 복사
"""
import requests
import json

BOT_TOKEN = "8558479211:AAFwxFXqsm8NufHC5fwc3L3wxatbMAQ1Zio"
CHANNEL_ID = "-1003363597143"

print("=" * 60)
print("채널 메시지 ID 가져오기")
print("=" * 60)
print(f"\n채널 ID: {CHANNEL_ID}")
print("\n채널에서 최근 메시지 ID를 가져오는 중...\n")

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
response = requests.get(url, params={"limit": 100})
data = response.json()

if data.get("ok") and data.get("result"):
    message_ids = []
    for update in data["result"]:
        if "channel_post" in update:
            post = update["channel_post"]
            chat_id = post["chat"]["id"]
            if str(chat_id) == CHANNEL_ID:
                message_id = post["message_id"]
                if message_id not in message_ids:
                    message_ids.append(message_id)
    
    if message_ids:
        print(f"\n채널에서 {len(message_ids)}개의 메시지 ID를 찾았습니다:\n")
        for msg_id in sorted(message_ids):
            print(msg_id)
        
        print("\n" + "=" * 60)
        print("이 메시지 ID들을 message_ids.txt 파일에 복사하세요!")
        print("=" * 60)
    else:
        print("\n채널 메시지를 찾을 수 없습니다.")
        print("봇이 채널의 관리자로 추가되어 있는지 확인하세요.")
else:
    print("업데이트를 가져올 수 없습니다.")

