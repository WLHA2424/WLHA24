import asyncio
import logging
import sys
from datetime import datetime
from queue import Queue
from typing import List
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, SOURCE_CHANNEL_ID, TARGET_GROUP_IDS, SEND_INTERVAL_HOURS, SEND_INTERVAL_MINUTES, REGISTER_PASSWORD

# Windows에서 이벤트 루프 정책 설정
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 로깅 설정 (UTF-8 인코딩 + 파일 저장)
import sys
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 로그 파일과 콘솔 모두에 출력
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Conflict 에러는 자동 재시도되므로 로그 레벨을 낮춤
logging.getLogger('telegram.ext.Updater').setLevel(logging.WARNING)

# 메시지 큐
message_queue: Queue = Queue()

# 전송한 메시지 추적 (메시지 ID: 전송 시간)
sent_messages: dict = {}

# 채널의 모든 메시지 ID 저장 (반복 전송용)
channel_message_ids: List[int] = []

# 등록된 그룹 ID 목록 (동적으로 추가 가능)
registered_group_ids: List[str] = []

# 비밀번호 입력 대기 중인 사용자 (user_id: group_id)
pending_registrations: dict = {}

# 전송 간격 계산 (초 단위)
send_interval_seconds = (SEND_INTERVAL_HOURS * 3600) + (SEND_INTERVAL_MINUTES * 60)

# 기존 메시지 전송 간격 (10분 = 600초) - 명령어로 변경 가능
EXISTING_MESSAGE_INTERVAL = 600  # 10분

# 재전송 대기 시간 (1시간 = 3600초) - 명령어로 변경 가능
RESEND_WAIT_TIME = 3600  # 1시간

# 전역 변수로 설정값 저장 (명령어로 변경 가능)
current_message_interval = 600  # 10분
current_resend_wait_time = 3600  # 1시간

class TelegramChannelForwarder:
    def __init__(self):
        self.application = None
        self.is_running = False
        
    async def start(self):
        """봇 시작"""
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
        if not SOURCE_CHANNEL_ID:
            raise ValueError("SOURCE_CHANNEL_ID가 설정되지 않았습니다.")
        if not TARGET_GROUP_IDS:
            raise ValueError("TARGET_GROUP_IDS가 설정되지 않았습니다.")
        
        # 초기 그룹 ID 등록
        global registered_group_ids
        registered_group_ids = list(TARGET_GROUP_IDS)  # config에서 설정한 그룹들
        
        # 파일에서 저장된 그룹 목록 불러오기
        await self.load_groups_from_file()
        
        logger.info(f"등록된 그룹: {len(registered_group_ids)}개 - {registered_group_ids}")
            
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # 채널 포스트 핸들러 등록 (비공개 채널용)
        # 채널 포스트는 update.channel_post로 들어옴
        from telegram.ext import MessageHandler, filters
        
        # 채널 포스트를 받기 위한 핸들러
        # python-telegram-bot에서 채널 포스트는 별도로 처리해야 함
        async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """채널 포스트를 처리하는 핸들러"""
            try:
                # 채널 포스트가 있고, 지정한 채널 ID와 일치하는지 확인
                if update.channel_post:
                    channel_id = update.channel_post.chat.id
                    message_id = update.channel_post.message_id
                    
                    if str(channel_id) == str(SOURCE_CHANNEL_ID):
                        # 명령어 처리 (텍스트 메시지인 경우)
                        if update.channel_post.text:
                            text = update.channel_post.text.strip()
                            
                            # 명령어 처리
                            if text.startswith('/interval') or text.startswith('/간격'):
                                await self.handle_interval_command(update, context, text)
                                return
                            elif text.startswith('/resend') or text.startswith('/재전송'):
                                await self.handle_resend_command(update, context, text)
                                return
                            elif text.startswith('/설정') or text.startswith('/셋팅') or text.startswith('/status'):
                                await self.handle_status_command(update, context)
                                return
                        
                        # 일반 메시지 처리
                        logger.info(f"[채널 ID 일치!] 메시지 처리 시작...")
                        await self.handle_channel_message(update, context)
                    else:
                        logger.warning(f"[채널 ID 불일치] {channel_id} != {SOURCE_CHANNEL_ID}")
                elif update.edited_channel_post:
                    # 수정된 채널 포스트도 처리
                    channel_id = update.edited_channel_post.chat.id
                    if str(channel_id) == str(SOURCE_CHANNEL_ID):
                        logger.info(f"[수정된 채널 포스트] 처리 시작...")
                        await self.handle_channel_message(update, context)
            except Exception as e:
                logger.error(f"채널 포스트 핸들러 오류: {e}", exc_info=True)
        
        # 모든 업데이트를 받는 핸들러 추가 (가장 높은 우선순위)
        from telegram.ext import TypeHandler
        
        # 채널 포스트를 받기 위한 핸들러 (채널 포스트만 처리)
        async def all_updates_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """채널 포스트만 처리 (그룹 메시지는 제외)"""
            # 채널 포스트나 수정된 채널 포스트만 처리
            if update.channel_post or update.edited_channel_post:
                await channel_post_handler(update, context)
        
        self.application.add_handler(TypeHandler(Update, all_updates_handler), group=-1)
        
        # 그룹 메시지 핸들러 (그룹 등록용)
        async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """그룹에서 메시지를 받았을 때 처리 (그룹 등록용)"""
            if update.message and update.message.chat.type in ['group', 'supergroup']:
                text = update.message.text
                # 텔레그램 봇 명령어는 /월하 또는 /월하@botusername 형식으로 올 수 있음
                if text:
                    # @botusername 부분 제거하고 명령어만 추출
                    command = text.split()[0].split('@')[0].strip() if text.split() else ""
                    logger.info(f"그룹 메시지 수신: chat_id={update.message.chat.id}, user_id={update.message.from_user.id}, text={text}, command={command}")
                    
                    if command == '/월하':
                        group_id = str(update.message.chat.id)
                        user_id = update.message.from_user.id
                        logger.info(f"/월하 명령어 감지: 그룹={group_id}, 사용자={user_id}")
                    
                    # 이미 등록된 그룹인지 확인
                    if group_id in registered_group_ids:
                        await self.application.bot.send_message(
                            chat_id=group_id,
                            text=f"ℹ️ 이 그룹은 이미 등록되어 있습니다.\n그룹 ID: {group_id}"
                        )
                        return
                    
                    # 비밀번호 입력 대기 상태로 설정
                    pending_registrations[user_id] = group_id
                    
                    # 그룹에 안내 메시지
                    await self.application.bot.send_message(
                        chat_id=group_id,
                        text="🔐 그룹 등록을 위해 비밀번호가 필요합니다."
                    )
                    
                    # 사용자에게 DM으로 비밀번호 요청
                    try:
                        await self.application.bot.send_message(
                            chat_id=user_id,
                            text=f"🔐 그룹 등록을 위한 비밀번호를 입력해주세요.\n그룹 ID: {group_id}\n\n비밀번호를 입력하세요:"
                        )
                        logger.info(f"비밀번호 입력 대기: 사용자 {user_id}, 그룹 {group_id}")
                    except Exception as e:
                        logger.error(f"DM 전송 실패 (사용자 {user_id}): {e}")
                        # DM을 보낼 수 없으면 그룹에 안내
                        await self.application.bot.send_message(
                            chat_id=group_id,
                            text="❌ 봇과의 개인 대화를 먼저 시작해주세요.\n(봇에게 아무 메시지나 보내면 됩니다)"
                        )
                        if user_id in pending_registrations:
                            del pending_registrations[user_id]
        
        self.application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, group_message_handler))
        
        # 개인 메시지 핸들러 (비밀번호 입력용)
        async def private_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """개인 메시지를 받았을 때 처리 (비밀번호 확인용)"""
            if update.message and update.message.chat.type == 'private':
                user_id = update.message.from_user.id
                text = update.message.text.strip() if update.message.text else ""
                
                # 비밀번호 입력 대기 중인 사용자인지 확인
                if user_id in pending_registrations:
                    group_id = pending_registrations[user_id]
                    
                    # 비밀번호 확인
                    if text == REGISTER_PASSWORD:
                        # 그룹 등록
                        if group_id not in registered_group_ids:
                            registered_group_ids.append(group_id)
                            await self.save_groups_to_file()
                            logger.info(f"새 그룹 등록: {group_id} (총 {len(registered_group_ids)}개, 사용자: {user_id})")
                            
                            # 그룹에 성공 메시지
                            try:
                                await self.application.bot.send_message(
                                    chat_id=group_id,
                                    text="✅ 그룹이 등록되었습니다!"
                                )
                            except:
                                pass
                            
                            # 기존 메시지가 있으면 즉시 전송
                            if channel_message_ids:
                                logger.info(f"새 그룹 등록: {group_id}, 기존 메시지 {len(channel_message_ids)}개 즉시 전송 시작")
                                asyncio.create_task(self.send_existing_messages_to_new_group(group_id))
                        else:
                            await self.application.bot.send_message(
                                chat_id=user_id,
                                text=f"ℹ️ 이 그룹은 이미 등록되어 있습니다.\n그룹 ID: {group_id}"
                            )
                        
                        # 대기 상태 제거
                        del pending_registrations[user_id]
                    else:
                        # 비밀번호 오류
                        await self.application.bot.send_message(
                            chat_id=user_id,
                            text="❌ 비밀번호가 올바르지 않습니다.\n다시 입력해주세요:"
                        )
                        logger.warning(f"잘못된 비밀번호 입력 시도: 사용자 {user_id}, 그룹 {group_id}")
        
        self.application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, private_message_handler))
        
        logger.info("채널 포스트 핸들러가 등록되었습니다.")
        logger.info("그룹 메시지 핸들러가 등록되었습니다. (그룹에서 /월하 명령어 사용 가능, 비밀번호 필요)")
        logger.info("개인 메시지 핸들러가 등록되었습니다. (비밀번호 입력용)")
        
        self.is_running = True
        
        logger.info(f"봇이 시작되었습니다. 전송 간격: {SEND_INTERVAL_HOURS}시간 {SEND_INTERVAL_MINUTES}분")
        logger.info(f"채널 ID: {SOURCE_CHANNEL_ID}, 등록된 그룹: {len(registered_group_ids)}개")
        
        # 스케줄러는 사용하지 않음 (기존 메시지는 send_existing_messages_sequentially에서 처리)
        # 새 메시지는 즉시 전송하고, 기존 메시지는 10분 간격으로 무한 반복 전송
        logger.info("메시지 전송 스케줄러는 사용하지 않습니다. (즉시 전송 + 10분 간격 반복 전송)")
        
        logger.info("봇이 실행 중입니다. 채널 메시지를 기다리는 중...")
        
        # Windows 이벤트 루프 문제 해결을 위해 직접 관리
        try:
            await self.application.initialize()
            await self.application.start()
            
            # Webhook이 설정되어 있으면 삭제 (Conflict 방지)
            try:
                # 여러 번 시도하여 확실히 삭제
                for attempt in range(3):
                    try:
                        webhook_info = await self.application.bot.get_webhook_info()
                        if webhook_info.url:
                            logger.info(f"Webhook 발견: {webhook_info.url}, 삭제 중...")
                            await self.application.bot.delete_webhook(drop_pending_updates=True)
                            await asyncio.sleep(1)  # 삭제 후 잠시 대기
                        logger.info("Webhook 삭제 완료 (Polling 모드 사용)")
                        break
                    except Exception as e:
                        if attempt < 2:
                            logger.warning(f"Webhook 삭제 시도 {attempt + 1}/3 실패, 재시도 중...: {e}")
                            await asyncio.sleep(2)
                        else:
                            logger.warning(f"Webhook 삭제 최종 실패 (무시): {e}")
            except Exception as e:
                logger.warning(f"Webhook 확인 중 오류 (무시): {e}")
            
            # Polling 시작 전 잠시 대기 (다른 인스턴스 종료 대기)
            await asyncio.sleep(2)
            
            await self.application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            logger.info("봇이 완전히 시작되었습니다!")
            
            # 기존 채널 메시지를 순차적으로 전송하는 작업 시작
            asyncio.create_task(self.send_existing_messages_sequentially())
            
            logger.info("채널 메시지를 기다리는 중...")
            
            # 무한 대기
            try:
                while True:
                    await asyncio.sleep(3600)  # 1시간마다 체크
            except KeyboardInterrupt:
                logger.info("종료 신호를 받았습니다...")
        finally:
            try:
                await self.application.stop()
                await self.application.shutdown()
            except:
                pass
    
    async def handle_interval_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """메시지 간 전송 간격 설정 명령어 처리"""
        global current_message_interval
        
        try:
            parts = text.split()
            if len(parts) < 2:
                await self.send_command_response(update, "사용법: /간격 [분]\n예: /간격 10 (10분 간격)")
                return
            
            minutes = int(parts[1])
            if minutes < 1:
                await self.send_command_response(update, "간격은 1분 이상이어야 합니다.")
                return
            
            current_message_interval = minutes * 60  # 분을 초로 변환
            logger.info(f"메시지 간 전송 간격이 {minutes}분으로 변경되었습니다.")
            await self.send_command_response(update, f"✅ 메시지 간 전송 간격이 {minutes}분으로 설정되었습니다.")
        except ValueError:
            await self.send_command_response(update, "❌ 잘못된 형식입니다. 숫자를 입력하세요.\n예: /간격 10")
        except Exception as e:
            logger.error(f"간격 설정 오류: {e}")
            await self.send_command_response(update, f"❌ 오류 발생: {e}")
    
    async def handle_resend_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """같은 메시지 재전송 간격 설정 명령어 처리"""
        global current_resend_wait_time
        
        try:
            parts = text.split()
            if len(parts) < 2:
                await self.send_command_response(update, "사용법: /재전송 [분]\n예: /재전송 60 (60분 = 1시간 간격)")
                return
            
            minutes = int(parts[1])
            if minutes < 1:
                await self.send_command_response(update, "간격은 1분 이상이어야 합니다.")
                return
            
            current_resend_wait_time = minutes * 60  # 분을 초로 변환
            logger.info(f"같은 메시지 재전송 간격이 {minutes}분으로 변경되었습니다.")
            await self.send_command_response(update, f"✅ 같은 메시지 재전송 간격이 {minutes}분으로 설정되었습니다.")
        except ValueError:
            await self.send_command_response(update, "❌ 잘못된 형식입니다. 숫자를 입력하세요.\n예: /재전송 60")
        except Exception as e:
            logger.error(f"재전송 간격 설정 오류: {e}")
            await self.send_command_response(update, f"❌ 오류 발생: {e}")
    
    async def handle_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """현재 설정 상태 확인 명령어"""
        global current_message_interval, current_resend_wait_time
        
        interval_min = current_message_interval // 60
        resend_min = current_resend_wait_time // 60
        
        # 등록된 메시지 수 (실제 전송 시 존재하지 않으면 자동 제거됨)
        message_count = len(channel_message_ids)
        
        status_text = f"""📊 현재 봇 설정 상태

⏱️ 메시지 간 전송 간격: {interval_min}분
🔄 같은 메시지 재전송 간격: {resend_min}분
📝 등록된 메시지 수: {message_count}개

명령어:
/간격 [분] - 메시지 간 전송 간격 설정
/재전송 [분] - 같은 메시지 재전송 간격 설정
/설정 - 현재 설정 확인"""
        
        await self.send_command_response(update, status_text)
    
    async def send_command_response(self, update: Update, message: str):
        """명령어 응답을 비공개 채널에 전송"""
        try:
            # 비공개 채널에 응답 전송
            await self.application.bot.send_message(
                chat_id=SOURCE_CHANNEL_ID,
                text=message
            )
        except Exception as e:
            logger.error(f"명령어 응답 전송 실패: {e}")
    
    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """채널에서 메시지를 받았을 때 처리"""
        try:
            # 채널 포스트는 update.channel_post에 있음
            message = update.channel_post or update.message
            
            if not message:
                logger.warning("메시지가 없습니다.")
                return
            
            message_id = message.message_id
            logger.info(f"채널 메시지 수신: ID={message_id}, 채널={message.chat.id}")
            
            # 설정된 재전송 간격 내에 이미 전송한 메시지인지 확인
            import time
            current_time = time.time()
            if message_id in sent_messages:
                last_sent_time = sent_messages[message_id]
                time_since_sent = current_time - last_sent_time
                
                if time_since_sent < current_resend_wait_time:
                    wait_remaining = current_resend_wait_time - time_since_sent
                    wait_minutes = int(wait_remaining / 60)
                    resend_min = current_resend_wait_time // 60
                    logger.info(f"메시지 {message_id}는 {wait_minutes}분 전에 전송되었습니다. {resend_min}분 대기 중...")
                    return
            
            # 메시지 정보 저장 (전달에 필요한 최소 정보만)
            message_data = {
                'chat_id': int(SOURCE_CHANNEL_ID),
                'message_id': message_id,
                'date': message.date.isoformat() if message.date else None
            }
            
            # 즉시 전송 (재시도 포함)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self.forward_message(message_data)
                    # 전송 성공 시 기록
                    sent_messages[message_id] = current_time
                    
                    # 메시지 ID를 채널 메시지 목록에 추가 (없으면)
                    if message_id not in channel_message_ids:
                        channel_message_ids.append(message_id)
                        logger.info(f"새 메시지 ID 추가: {message_id} (총 {len(channel_message_ids)}개)")
                        # 파일에 저장
                        await self.save_message_ids_to_file()
                    
                    logger.info(f"메시지 즉시 전송 완료 (ID: {message_id})")
                    return  # 성공하면 종료
                except Exception as e:
                    logger.warning(f"전송 시도 {attempt + 1}/{max_retries} 실패: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # 1초 대기 후 재시도
                    else:
                        logger.error(f"최종 전송 실패, 큐에 추가: {e}")
                        message_queue.put(message_data)
            
        except Exception as e:
            logger.error(f"메시지 처리 중 오류 발생: {e}", exc_info=True)
    
    async def send_messages_to_group(self):
        """큐에 있는 메시지들을 그룹으로 전송"""
        if message_queue.empty():
            logger.debug("전송할 메시지가 없습니다.")
            return
        
        messages_to_send: List[dict] = []
        
        # 큐에서 모든 메시지 가져오기
        while not message_queue.empty():
            messages_to_send.append(message_queue.get())
        
        if not messages_to_send:
            return
        
        try:
            for msg_data in messages_to_send:
                await self.forward_message(msg_data)
                # API 제한을 피하기 위해 약간의 지연
                await asyncio.sleep(0.5)
            
            logger.info(f"{len(messages_to_send)}개의 메시지를 그룹으로 전송했습니다.")
            
        except Exception as e:
            logger.error(f"메시지 전송 중 오류 발생: {e}")
            # 오류 발생 시 메시지를 다시 큐에 넣기
            for msg_data in messages_to_send:
                message_queue.put(msg_data)
    
    async def forward_message(self, msg_data: dict):
        """개별 메시지를 모든 등록된 그룹으로 전달 (텔레그램 forward API 사용)"""
        global registered_group_ids
        
        if not registered_group_ids:
            logger.warning("등록된 그룹이 없습니다. 그룹에서 /월하 명령어를 사용하세요.")
            return None
        
        success_count = 0
        failed_groups = []
        
        for group_id in registered_group_ids:
            try:
                logger.info(f"메시지 전달 시도: 채널={msg_data['chat_id']}, 메시지ID={msg_data['message_id']}, 그룹={group_id}")
                
                # 텔레그램의 forward_message API를 사용하여 원본 메시지를 그대로 전달
                result = await self.application.bot.forward_message(
                    chat_id=group_id,
                    from_chat_id=msg_data['chat_id'],
                    message_id=msg_data['message_id']
                )
                logger.info(f"메시지 전달 성공! (ID: {msg_data['message_id']}, 그룹: {group_id})")
                
                # 전달한 메시지를 고정 (pin)
                try:
                    forwarded_message_id = result.message_id
                    await self.application.bot.pin_chat_message(
                        chat_id=group_id,
                        message_id=forwarded_message_id
                    )
                    logger.info(f"메시지 고정 완료! (그룹: {group_id}, 메시지 ID: {forwarded_message_id})")
                except Exception as pin_error:
                    logger.warning(f"메시지 고정 실패 (그룹: {group_id}): {pin_error} (봇이 그룹에서 메시지를 고정할 권한이 없을 수 있습니다)")
                
                success_count += 1
                # API 제한을 피하기 위해 약간의 지연
                await asyncio.sleep(0.3)
                
            except Exception as e:
                error_msg = str(e).lower()
                logger.error(f"메시지 전달 실패 (그룹: {group_id}, ID: {msg_data['message_id']}): {error_msg}")
                
                # 그룹을 찾을 수 없거나 봇이 제거된 경우 목록에서 제거
                if "chat not found" in error_msg or "bot was kicked" in error_msg or "bot was blocked" in error_msg:
                    logger.warning(f"그룹 {group_id}을 찾을 수 없거나 봇이 제거되었습니다. 목록에서 제거합니다.")
                    if group_id in registered_group_ids:
                        registered_group_ids.remove(group_id)
                        await self.save_groups_to_file()
                    failed_groups.append(group_id)
                elif "forbidden" in error_msg:
                    logger.warning(f"그룹 {group_id}에서 권한이 없습니다. (메시지 전송 권한 필요)")
                    failed_groups.append(group_id)
                else:
                    failed_groups.append(group_id)
        
        if success_count > 0:
            logger.info(f"메시지 전달 완료: {success_count}개 그룹에 전송됨 (실패: {len(failed_groups)}개)")
        else:
            logger.error(f"모든 그룹에 메시지 전달 실패")
        
        return success_count > 0
    
    
    async def load_message_ids_from_file(self):
        """파일에서 메시지 ID 목록 불러오기"""
        try:
            from pathlib import Path
            ids_file = Path(__file__).parent / 'message_ids.txt'
            logger.info(f"메시지 ID 파일 경로: {ids_file.absolute()}")
            
            if ids_file.exists():
                loaded_count = 0
                file_content = []
                with open(ids_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        file_content.append(line)
                        # 주석이나 빈 줄 건너뛰기
                        if line and not line.startswith('#'):
                            try:
                                msg_id = int(line)
                                if msg_id not in channel_message_ids:
                                    channel_message_ids.append(msg_id)
                                    loaded_count += 1
                                    logger.debug(f"메시지 ID {msg_id} 로드됨")
                            except ValueError as ve:
                                logger.debug(f"라인 '{line}'을 정수로 변환 실패: {ve}")
                                continue
                
                logger.info(f"파일 내용 (처음 10줄): {file_content[:10]}")
                if loaded_count > 0:
                    logger.info(f"파일에서 메시지 ID {loaded_count}개를 불러왔습니다. (총 {len(channel_message_ids)}개)")
                    logger.info(f"로드된 메시지 ID 목록: {sorted(channel_message_ids)}")
                else:
                    logger.warning(f"파일에서 메시지 ID를 불러왔지만 등록된 메시지가 없습니다. (파일 내용: {file_content})")
            else:
                logger.warning(f"message_ids.txt 파일이 없습니다. 경로: {ids_file.absolute()}")
        except Exception as e:
            logger.error(f"메시지 ID 파일 읽기 실패: {e}", exc_info=True)
    
    async def save_message_ids_to_file(self):
        """메시지 ID 목록을 파일에 저장 (봇 재시작 시에도 유지됨)"""
        try:
            from pathlib import Path
            ids_file = Path(__file__).parent / 'message_ids.txt'
            with open(ids_file, 'w', encoding='utf-8') as f:
                f.write("# 채널에 있는 메시지 ID 목록\n")
                f.write("# 한 줄에 하나씩 메시지 ID만 입력\n")
                f.write("# 봇이 자동으로 관리하므로 수동 수정 불필요\n\n")
                for msg_id in sorted(channel_message_ids):
                    f.write(f"{msg_id}\n")
            logger.debug(f"메시지 ID {len(channel_message_ids)}개를 파일에 저장했습니다.")
        except Exception as e:
            logger.error(f"메시지 ID 파일 저장 실패: {e}")
    
    async def load_groups_from_file(self):
        """파일에서 등록된 그룹 ID 목록 불러오기"""
        global registered_group_ids
        try:
            from pathlib import Path
            groups_file = Path(__file__).parent / 'registered_groups.txt'
            if groups_file.exists():
                loaded_count = 0
                with open(groups_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if line not in registered_group_ids:
                                registered_group_ids.append(line)
                                loaded_count += 1
                if loaded_count > 0:
                    logger.info(f"파일에서 그룹 ID {loaded_count}개를 불러왔습니다. (총 {len(registered_group_ids)}개)")
            else:
                # 파일이 없으면 config의 기본 그룹만 사용
                logger.info(f"registered_groups.txt 파일이 없습니다. config.py의 기본 그룹을 사용합니다.")
        except Exception as e:
            logger.error(f"그룹 ID 파일 읽기 실패: {e}")
    
    async def save_groups_to_file(self):
        """등록된 그룹 ID 목록을 파일에 저장"""
        global registered_group_ids
        try:
            from pathlib import Path
            groups_file = Path(__file__).parent / 'registered_groups.txt'
            with open(groups_file, 'w', encoding='utf-8') as f:
                f.write("# 등록된 그룹 ID 목록\n")
                f.write("# 한 줄에 하나씩 그룹 ID만 입력\n")
                f.write("# 그룹에서 /월하 명령어로 자동 추가됨\n\n")
                for group_id in registered_group_ids:
                    f.write(f"{group_id}\n")
            logger.debug(f"그룹 ID {len(registered_group_ids)}개를 파일에 저장했습니다.")
        except Exception as e:
            logger.error(f"그룹 ID 파일 저장 실패: {e}")
    
    async def send_existing_messages_to_new_group(self, group_id: str):
        """새로 등록된 그룹에 기존 메시지들을 즉시 전송"""
        try:
            if not channel_message_ids:
                return
            
            logger.info(f"그룹 {group_id}에 기존 메시지 {len(channel_message_ids)}개 즉시 전송 중...")
            
            for idx, message_id in enumerate(channel_message_ids, 1):
                message_data = {
                    'chat_id': int(SOURCE_CHANNEL_ID),
                    'message_id': message_id,
                    'date': None
                }
                
                try:
                    # 특정 그룹에만 전송
                    result = await self.application.bot.forward_message(
                        chat_id=group_id,
                        from_chat_id=message_data['chat_id'],
                        message_id=message_data['message_id']
                    )
                    
                    # 메시지 고정
                    try:
                        await self.application.bot.pin_chat_message(
                            chat_id=group_id,
                            message_id=result.message_id
                        )
                    except:
                        pass
                    
                    logger.info(f"[기존 메시지 {idx}/{len(channel_message_ids)}] 그룹 {group_id}에 전송 완료 (ID: {message_id})")
                    
                    # API 제한을 피하기 위해 약간의 지연
                    if idx < len(channel_message_ids):
                        await asyncio.sleep(1)  # 1초 간격
                        
                except Exception as e:
                    error_msg = str(e).lower()
                    if "message to forward not found" in error_msg or "message not found" in error_msg:
                        logger.warning(f"메시지 {message_id}가 채널에 존재하지 않습니다. 건너뜁니다.")
                    else:
                        logger.error(f"기존 메시지 전송 실패 (그룹: {group_id}, ID: {message_id}): {e}")
            
            logger.info(f"그룹 {group_id}에 기존 메시지 전송 완료")
        except Exception as e:
            logger.error(f"기존 메시지 전송 중 오류: {e}", exc_info=True)
    
    async def send_existing_messages_sequentially(self):
        """기존 채널 메시지를 순차적으로 무한 반복 전송 (10분 간격)"""
        import time
        
        # 파일에서 기존 메시지 ID 불러오기 (봇 재시작 시에도 유지됨)
        await self.load_message_ids_from_file()
        
        # getUpdates는 Conflict 오류를 일으킬 수 있으므로 제거
        # 새 메시지는 handle_channel_message에서 자동으로 추가됨
        
        logger.info(f"현재 등록된 메시지: {len(channel_message_ids)}개 (파일에서 불러옴)")
        if len(channel_message_ids) > 0:
            logger.info(f"등록된 메시지 ID: {sorted(channel_message_ids)}")
        logger.info("이제 비공개 채널에 올라오는 모든 새 메시지를 자동으로 감지하여 순환 전송합니다.")
        logger.info("봇을 재시작해도 등록된 메시지 목록은 유지됩니다.")
        
        # 무한 반복 전송
        while self.is_running:
            try:
                if not channel_message_ids:
                    logger.info("전송할 메시지가 없습니다. 비공개 채널에 새 메시지를 올리면 자동으로 등록됩니다.")
                    await asyncio.sleep(60)  # 1분마다 체크
                    continue
                
                logger.info(f"채널 메시지 {len(channel_message_ids)}개를 {current_message_interval // 60}분 간격으로 무한 반복 전송 시작...")
                
                cycle = 1
                while self.is_running and channel_message_ids:  # 메시지가 있을 때만 사이클 실행
                    logger.info(f"=== {cycle}번째 사이클 시작 (총 {len(channel_message_ids)}개 메시지) ===")
                    
                    for idx, message_id in enumerate(channel_message_ids, 1):
                        if not self.is_running:
                            return
                        
                        message_data = {
                            'chat_id': int(SOURCE_CHANNEL_ID),
                            'message_id': message_id,
                            'date': None
                        }
                        
                        try:
                            await self.forward_message(message_data)
                            # 전송 성공 시 기록 (로그용)
                            sent_messages[message_id] = time.time()
                            logger.info(f"[사이클 {cycle}, {idx}/{len(channel_message_ids)}] 메시지 전송 완료 (ID: {message_id})")
                            
                            # 마지막 메시지가 아니면 설정된 간격만큼 대기
                            if idx < len(channel_message_ids):
                                interval_min = current_message_interval // 60
                                logger.info(f"다음 메시지까지 {interval_min}분 대기 중...")
                                await asyncio.sleep(current_message_interval)
                        except Exception as e:
                            error_msg = str(e).lower()
                            # 메시지가 실제로 존재하지 않는 경우에만 목록에서 제거
                            if "message to forward not found" in error_msg or "message not found" in error_msg:
                                logger.warning(f"메시지 {message_id}가 채널에 존재하지 않습니다. 목록에서 제거합니다.")
                                if message_id in channel_message_ids:
                                    channel_message_ids.remove(message_id)
                                    await self.save_message_ids_to_file()
                            else:
                                # 다른 이유로 실패한 경우 (권한, 네트워크 등)는 제거하지 않음
                                logger.error(f"메시지 전달 실패 (ID: {message_id}): {e} (목록에서 제거하지 않음)")
                            # 실패해도 다음 메시지로 진행
                            if idx < len(channel_message_ids):
                                await asyncio.sleep(current_message_interval)
                    
                    # 한 사이클 완료 후 재전송 대기 시간만큼 대기 후 다시 시작
                    # 메시지가 없으면 사이클 종료
                    if not channel_message_ids:
                        logger.info("등록된 메시지가 없어 사이클을 종료합니다.")
                        break
                    
                    # 사이클 간 재전송 대기 시간 적용
                    resend_wait_min = current_resend_wait_time // 60
                    logger.info(f"=== {cycle}번째 사이클 완료. 다음 사이클까지 {resend_wait_min}분 대기 중... ===")
                    await asyncio.sleep(current_resend_wait_time)
                    cycle += 1
                    
            except Exception as e:
                logger.error(f"기존 메시지 가져오기 중 오류: {e}", exc_info=True)
                await asyncio.sleep(60)  # 오류 발생 시 1분 후 재시도
    
    async def send_messages_to_group_callback(self, context: ContextTypes.DEFAULT_TYPE):
        """주기적으로 메시지를 전송하는 콜백"""
        await self.send_messages_to_group()

def run_keepalive_server():
    """KeepAlive 웹서버를 별도 스레드에서 실행"""
    try:
        from keepalive import run_keepalive
        import threading
        import os
        # Replit에서는 환경 변수 PORT를 사용
        port = int(os.environ.get('PORT', 8080))
        keepalive_thread = threading.Thread(target=run_keepalive, args=(port,), daemon=True)
        keepalive_thread.start()
        logger.info(f"KeepAlive 서버가 시작되었습니다. (Replit 잠자기 방지, 포트: {port})")
    except Exception as e:
        logger.warning(f"KeepAlive 서버 시작 실패: {e}")

def main():
    """메인 함수"""
    # KeepAlive 서버 시작 (Replit용)
    run_keepalive_server()
    
    forwarder = TelegramChannelForwarder()
    
    try:
        asyncio.run(forwarder.start())
    except KeyboardInterrupt:
        logger.info("봇이 종료되었습니다.")
    except Exception as e:
        logger.error(f"봇 실행 중 오류 발생: {e}", exc_info=True)

if __name__ == '__main__':
    main()

