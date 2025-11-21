import os

# 텔레그램 봇 토큰 (환경변수 우선, 없으면 기본값)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8558479211:AAFwxFXqsm8NufHC5fwc3L3wxatbMAQ1Zio")

# 소스 채널 ID (비공개 채널) (환경변수 우선, 없으면 기본값)
SOURCE_CHANNEL_ID = os.environ.get("SOURCE_CHANNEL_ID", "-1003363597143")

# 대상 그룹 ID (메시지를 전달할 그룹) - 여러 그룹 지원
# 환경변수에서 읽거나 기본값 사용
TARGET_GROUP_IDS_ENV = os.environ.get("TARGET_GROUP_IDS", "")
if TARGET_GROUP_IDS_ENV:
    # 쉼표로 구분된 그룹 ID들을 리스트로 변환
    TARGET_GROUP_IDS = [gid.strip() for gid in TARGET_GROUP_IDS_ENV.split(",")]
else:
    # 기본값
    TARGET_GROUP_IDS = [
        "-1003369712631",  # 기존 그룹
        # 여기에 다른 그룹 ID를 추가하세요
    ]

# 전송 간격 (시간 단위, 기본값: 0시간)
SEND_INTERVAL_HOURS = float(os.environ.get("SEND_INTERVAL_HOURS", "0.0"))

# 전송 간격 (분 단위로도 설정 가능, 기본값: 1분)
SEND_INTERVAL_MINUTES = float(os.environ.get("SEND_INTERVAL_MINUTES", "1.0"))

