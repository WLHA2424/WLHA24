import requests
import json

BOT_TOKEN = "8558479211:AAFwxFXqsm8NufHC5fwc3L3wxatbMAQ1Zio"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
response = requests.get(url)
data = response.json()

print("=" * 50)
print("채널 및 그룹 ID 확인")
print("=" * 50)

if data.get("ok") and data.get("result"):
    channels = []
    groups = []
    
    for update in data["result"]:
        if "message" in update:
            chat = update["message"]["chat"]
            chat_id = chat["id"]
            chat_type = chat["type"]
            chat_title = chat.get("title", chat.get("username", "알 수 없음"))
            
            if chat_type == "channel":
                if chat_id not in [c["id"] for c in channels]:
                    channels.append({"id": chat_id, "title": chat_title})
            elif chat_type in ["group", "supergroup"]:
                if chat_id not in [g["id"] for g in groups]:
                    groups.append({"id": chat_id, "title": chat_title})
    
    if channels:
        print("\n[채널 발견]")
        for channel in channels:
            print(f"  - {channel['title']}: {channel['id']}")
    else:
        print("\n[채널을 찾을 수 없습니다]")
        print("   채널에 테스트 메시지를 보내고 다시 실행하세요.")
    
    if groups:
        print("\n[그룹 발견]")
        for group in groups:
            print(f"  - {group['title']}: {group['id']}")
    else:
        print("\n[그룹을 찾을 수 없습니다]")
        print("   그룹에서 /start 명령어를 입력하고 다시 실행하세요.")
    
    print("\n" + "=" * 50)
    print("전체 응답 데이터:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print("메시지를 찾을 수 없습니다.")
    print("\n다음을 확인하세요:")
    print("1. 채널에 테스트 메시지를 보냈는지")
    print("2. 그룹에서 /start 명령어를 입력했는지")
    print("3. 봇이 채널과 그룹에 제대로 추가되었는지")

