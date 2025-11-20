import requests
import json

BOT_TOKEN = "8558479211:AAFwxFXqsm8NufHC5fwc3L3wxatbMAQ1Zio"
CHANNEL_ID = "-1003363597143"

# 최근 업데이트 가져오기
url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
response = requests.get(url)
data = response.json()

print("=" * 60)
print("채널 메시지 확인")
print("=" * 60)

if data.get("ok") and data.get("result"):
    channel_posts = []
    for update in data["result"]:
        if "channel_post" in update:
            post = update["channel_post"]
            chat_id = post["chat"]["id"]
            if str(chat_id) == CHANNEL_ID:
                channel_posts.append({
                    "message_id": post["message_id"],
                    "text": post.get("text", post.get("caption", "미디어 메시지")),
                    "date": post["date"]
                })
    
    if channel_posts:
        print(f"\n채널에서 {len(channel_posts)}개의 메시지를 찾았습니다:")
        for post in channel_posts[-5:]:  # 최근 5개만
            print(f"  - ID: {post['message_id']}, 텍스트: {post['text'][:50]}")
    else:
        print("\n채널 메시지를 찾을 수 없습니다.")
        print("\n확인 사항:")
        print("1. 봇이 채널의 관리자로 추가되어 있는지")
        print("2. 채널에 최근 메시지가 있는지")
        print("3. 채널 ID가 올바른지")
    
    print("\n" + "=" * 60)
    print("최근 업데이트 (채널 포스트):")
    for update in data["result"][-3:]:
        if "channel_post" in update:
            print(json.dumps(update["channel_post"], indent=2, ensure_ascii=False))
else:
    print("업데이트를 가져올 수 없습니다.")

