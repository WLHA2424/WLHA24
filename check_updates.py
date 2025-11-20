import requests
import json
from datetime import datetime

BOT_TOKEN = "8558479211:AAFwxFXqsm8NufHC5fwc3L3wxatbMAQ1Zio"
CHANNEL_ID = "-1003363597143"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
response = requests.get(url)
data = response.json()

print("=" * 60)
print("최근 채널 메시지 확인")
print("=" * 60)

if data.get("ok") and data.get("result"):
    channel_posts = []
    for update in data["result"]:
        if "channel_post" in update:
            post = update["channel_post"]
            chat_id = post["chat"]["id"]
            if str(chat_id) == CHANNEL_ID:
                post_time = datetime.fromtimestamp(post["date"])
                channel_posts.append({
                    "message_id": post["message_id"],
                    "text": post.get("text", post.get("caption", "미디어 메시지")),
                    "date": post_time.strftime("%Y-%m-%d %H:%M:%S")
                })
    
    if channel_posts:
        print(f"\n채널에서 {len(channel_posts)}개의 메시지를 찾았습니다:")
        for post in channel_posts[-10:]:  # 최근 10개
            print(f"  - ID: {post['message_id']}, 시간: {post['date']}, 텍스트: {post['text'][:50]}")
    else:
        print("\n채널 메시지를 찾을 수 없습니다.")
else:
    print("업데이트를 가져올 수 없습니다.")

