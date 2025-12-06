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

# 새로 등록된 그룹에 첫 메시지 전송 완료 여부 (group_id: bool)
new_group_first_message_sent: dict = {}

# 비밀번호 입력 대기 중인 사용자 (user_id: group_id)
pending_registrations: dict = {}

# 전송 간격 계산 (초 단위)
send_interval_seconds = (SEND_INTERVAL_HOURS * 3600) + (SEND_INTERVAL_MINUTES * 60)

# 기존 메시지 전송 간격 (10분 = 600초) - 명령어로 변경 가능
EXISTING_MESSAGE_INTERVAL = 600  # 10분

# 재전송 대기 시간 (1시간 = 3600초) - 명령어로 변경 가능
RESEND_WAIT_TIME = 3600  # 1시간

# 전역 변수로 설정값 저장 (명령어로 변경 가능)
current_message_interval = 300  # 5분 (기본값)
current_resend_wait_time = 3600  # 1시간

class TelegramChannelForwarder:
    def __init__(self):
        self.application = None
        self.is_running = False
        self.is_fully_started = False  # 봇이 완전히 시작되었는지 확인
        
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
        
        # 등록된 그룹 확인 및 로그
        if len(registered_group_ids) == 0:
            logger.warning("⚠️ 등록된 그룹이 없습니다. 그룹에서 /월하 명령어로 등록해주세요.")
            logger.info("📋 메시지 전송은 등록된 그룹에만 전송됩니다.")
        else:
            logger.info(f"✅ 등록된 그룹 {len(registered_group_ids)}개: {registered_group_ids}")
            logger.info("📋 이 그룹들에 메시지가 전송됩니다.")
        
        # 파일에서 설정값 불러오기
        await self.load_settings_from_file()
            
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
        
        # 그룹 메시지 핸들러 (그룹 등록용) - /월하 명령어만 처리
        async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """그룹에서 /월하 명령어를 받았을 때 처리 (그룹 등록용)"""
            if not update.message or update.message.chat.type not in ['group', 'supergroup']:
                return
            
            # /월하 명령어 처리 (필터에서 이미 확인했으므로 바로 처리)
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
        
        # /월하 명령어만 처리하도록 필터 설정 (한글 명령어는 MessageHandler 사용)
        # CommandHandler는 한글을 지원하지 않으므로 MessageHandler + Regex 사용
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.GROUPS & filters.Regex(r'^/월하(@\w+)?\s*$'),
            group_message_handler
        ))
        
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
                    logger.info(f"🔐 비밀번호 확인 시도: 사용자 {user_id}, 그룹 {group_id}, 입력값: '{text}'")
                    if text == REGISTER_PASSWORD:
                        logger.info(f"✅ 비밀번호 일치! 그룹 등록 진행 중...")
                        # 그룹 등록
                        if group_id not in registered_group_ids:
                            registered_group_ids.append(group_id)
                            await self.save_groups_to_file()
                            logger.info(f"✅ 새 그룹 등록 완료: {group_id} (총 {len(registered_group_ids)}개, 사용자: {user_id})")
                            logger.info(f"📝 저장된 그룹 목록: {registered_group_ids}")
                            
                            # 사용자에게 성공 메시지
                            try:
                                await self.application.bot.send_message(
                                    chat_id=user_id,
                                    text=f"✅ 그룹 등록이 완료되었습니다!\n그룹 ID: {group_id}\n\n이제 채널 메시지가 이 그룹으로 전송됩니다."
                                )
                            except Exception as e:
                                logger.error(f"사용자 DM 전송 실패: {e}")
                            
                            # 그룹에 성공 메시지
                            try:
                                await self.application.bot.send_message(
                                    chat_id=group_id,
                                    text="✅ 그룹이 등록되었습니다!"
                                )
                            except Exception as e:
                                logger.error(f"그룹 메시지 전송 실패: {e}")
                            
                            # 새 그룹 등록 시 첫 메시지만 즉시 전송 (중복 방지)
                            if channel_message_ids:
                                # 첫 메시지만 즉시 전송
                                first_message_id = channel_message_ids[0]
                                new_group_first_message_sent[group_id] = False  # 첫 메시지 전송 플래그 초기화
                                
                                logger.info(f"🆕 새 그룹 등록 완료: {group_id}")
                                logger.info(f"📤 첫 메시지 즉시 전송 시작 (ID: {first_message_id})")
                                logger.info(f"⏱️ 이후 메시지는 {current_message_interval // 60}분 간격으로 전송됩니다.")
                                
                                if self.is_fully_started:
                                    logger.info(f"✅ 봇이 실행 중입니다. 첫 메시지 즉시 전송합니다.")
                                    asyncio.create_task(self.send_first_message_to_new_group(group_id, first_message_id))
                                else:
                                    logger.info(f"⏳ 봇이 완전히 시작된 후 첫 메시지 전송 예정")
                                    asyncio.create_task(self.send_first_message_to_new_group(group_id, first_message_id))
                            else:
                                logger.warning(f"⚠️ 등록된 메시지가 없습니다. 채널에 메시지를 먼저 보내주세요.")
                        else:
                            logger.info(f"ℹ️ 그룹 {group_id}는 이미 등록되어 있습니다.")
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
            logger.info("🔍 Webhook 상태 확인 중...")
            try:
                # 여러 번 시도하여 확실히 삭제
                webhook_deleted = False
                for attempt in range(10):  # 5회에서 10회로 증가
                    try:
                        webhook_info = await self.application.bot.get_webhook_info()
                        if webhook_info.url:
                            logger.info(f"🔗 Webhook 발견: {webhook_info.url}, 삭제 중... (시도: {attempt + 1}/10)")
                            await self.application.bot.delete_webhook(drop_pending_updates=True)
                            await asyncio.sleep(3)  # 삭제 후 대기 시간 증가
                            # 삭제 확인
                            webhook_info_after = await self.application.bot.get_webhook_info()
                            if not webhook_info_after.url:
                                logger.info("✅ Webhook 삭제 완료 (Polling 모드 사용)")
                                webhook_deleted = True
                                break
                            else:
                                logger.warning(f"⚠️ Webhook 삭제 후에도 여전히 존재합니다. 재시도 중... (시도: {attempt + 1}/10)")
                        else:
                            logger.info("✅ Webhook이 없습니다. Polling 모드 사용 가능")
                            webhook_deleted = True
                            break
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "conflict" in error_msg:
                            wait_time = min(5 + attempt * 2, 15)  # 최대 15초까지 증가
                            logger.warning(f"⚠️ Conflict 에러 발생. {wait_time}초 대기 후 재시도... (시도: {attempt + 1}/10)")
                            await asyncio.sleep(wait_time)
                        elif attempt < 9:
                            wait_time = min(3 + attempt, 10)
                            logger.warning(f"⚠️ Webhook 삭제 시도 {attempt + 1}/10 실패, {wait_time}초 후 재시도...: {e}")
                            await asyncio.sleep(wait_time)
                        else:
                            logger.warning(f"⚠️ Webhook 삭제 최종 실패 (무시하고 계속 진행): {e}")
                            break
                
                if not webhook_deleted:
                    logger.warning("⚠️ Webhook 삭제를 완료하지 못했지만 계속 진행합니다.")
            except Exception as e:
                logger.warning(f"⚠️ Webhook 확인 중 오류 (무시하고 계속 진행): {e}")
            
            # Polling 시작 전 충분한 대기 시간 (배포 중 이전 인스턴스 종료 대기)
            logger.info("⏳ 이전 인스턴스 완전 종료 대기 중... (20초)")
            await asyncio.sleep(20)  # Render 배포 시 이전 인스턴스가 완전히 종료될 때까지 충분한 대기
            
            # 추가 안전 장치: Webhook 재확인 및 삭제 (여러 번 시도)
            for final_attempt in range(3):
                try:
                    webhook_info_final = await self.application.bot.get_webhook_info()
                    if webhook_info_final.url:
                        logger.warning(f"⚠️ Webhook이 여전히 존재합니다: {webhook_info_final.url}, 강제 삭제 시도... (시도: {final_attempt + 1}/3)")
                        await self.application.bot.delete_webhook(drop_pending_updates=True)
                        await asyncio.sleep(3)
                    else:
                        logger.info("✅ 최종 확인: Webhook이 없습니다. Polling 모드 사용 가능")
                        break
                except Exception as e:
                    if "conflict" in str(e).lower():
                        logger.warning(f"⚠️ Conflict 에러 발생. {5 * (final_attempt + 1)}초 대기 후 재시도...")
                        await asyncio.sleep(5 * (final_attempt + 1))
                    else:
                        logger.warning(f"⚠️ 최종 Webhook 확인 중 오류 (무시): {e}")
                        break
            
            # Polling 시작 (Conflict 에러는 자동으로 재시도됨)
            logger.info("🚀 Polling 시작 중...")
            max_polling_retries = 5
            polling_retry_delay = 10
            
            for polling_attempt in range(max_polling_retries):
                try:
                    await self.application.updater.start_polling(
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True
                    )
                    logger.info("✅ 봇이 완전히 시작되었습니다!")
                    self.is_fully_started = True  # 봇 시작 완료 플래그 설정
                    break  # 성공하면 루프 종료
                except Exception as e:
                    error_msg = str(e).lower()
                    if "conflict" in error_msg:
                        if polling_attempt < max_polling_retries - 1:
                            wait_time = polling_retry_delay * (polling_attempt + 1)
                            logger.warning(f"⚠️ Polling 시작 중 Conflict 에러 발생 (시도: {polling_attempt + 1}/{max_polling_retries})")
                            logger.info(f"⏳ {wait_time}초 대기 후 재시도... (이전 인스턴스 종료 대기)")
                            await asyncio.sleep(wait_time)
                            # Webhook 다시 삭제 시도
                            try:
                                await self.application.bot.delete_webhook(drop_pending_updates=True)
                                await asyncio.sleep(3)
                            except:
                                pass
                        else:
                            logger.error(f"❌ Polling 시작 최종 실패 (최대 재시도 횟수 초과): {e}")
                            logger.error("💡 해결 방법: 다른 봇 인스턴스(로컬 PC, Replit 등)를 모두 종료하고 다시 시도하세요.")
                            raise
                    else:
                        logger.error(f"❌ Polling 시작 실패: {e}")
                        raise
            
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
            
            old_interval = current_message_interval
            current_message_interval = minutes * 60  # 분을 초로 변환
            logger.info(f"⚙️ 메시지 간격 변경: {old_interval // 60}분 → {minutes}분 (즉시 적용됨)")
            # 설정값을 파일에 저장
            await self.save_settings_to_file()
            await self.send_command_response(update, f"✅ 메시지 간 전송 간격이 {minutes}분으로 설정되었습니다.\n💡 다음 메시지부터 즉시 적용됩니다. (저장 완료)")
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
            
            old_resend = current_resend_wait_time
            current_resend_wait_time = minutes * 60  # 분을 초로 변환
            logger.info(f"⚙️ 재전송 간격 변경: {old_resend // 60}분 → {minutes}분 (다음 사이클부터 적용됨)")
            # 설정값을 파일에 저장
            await self.save_settings_to_file()
            await self.send_command_response(update, f"✅ 같은 메시지 재전송 간격이 {minutes}분으로 설정되었습니다.\n💡 다음 사이클부터 적용됩니다. (저장 완료)")
        except ValueError:
            await self.send_command_response(update, "❌ 잘못된 형식입니다. 숫자를 입력하세요.\n예: /재전송 60")
        except Exception as e:
            logger.error(f"재전송 간격 설정 오류: {e}")
            await self.send_command_response(update, f"❌ 오류 발생: {e}")
    
    async def handle_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """현재 설정 상태 확인 명령어"""
        global current_message_interval, current_resend_wait_time
        import os
        
        interval_min = current_message_interval // 60
        resend_min = current_resend_wait_time // 60
        
        # 등록된 메시지 수 (실제 전송 시 존재하지 않으면 자동 제거됨)
        message_count = len(channel_message_ids)
        
        # 설정 소스 확인
        env_interval = os.environ.get("MESSAGE_INTERVAL_SECONDS")
        env_resend = os.environ.get("RESEND_WAIT_TIME_SECONDS")
        source_info = ""
        if env_interval or env_resend:
            source_info = "\n💡 설정 소스: 환경 변수 (Render 재시작 후에도 유지)"
        else:
            source_info = "\n💡 설정 소스: 파일 (Render 재시작 시 초기화될 수 있음)"
            source_info += "\n   영구 저장을 원하면 Render 대시보드에서 환경 변수 설정 권장"
        
        status_text = f"""📊 현재 봇 설정 상태

⏱️ 메시지 간 전송 간격: {interval_min}분 ({current_message_interval}초)
🔄 같은 메시지 재전송 간격: {resend_min}분 ({current_resend_wait_time}초)
📝 등록된 메시지 수: {message_count}개{source_info}

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
                logger.warning("⚠️ 메시지가 없습니다.")
                return
            
            message_id = message.message_id
            logger.info(f"📥 채널 메시지 수신: ID={message_id}, 채널={message.chat.id}")
            
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
                    logger.info(f"⏳ 메시지 {message_id}는 {wait_minutes}분 전에 전송되었습니다. {resend_min}분 대기 중... (새 메시지이지만 재전송 간격 내)")
                    # 새 메시지이지만 재전송 간격 내이면 스킵 (다음 사이클에서 전송됨)
                    # 하지만 channel_message_ids에는 추가해야 함
                    if message_id not in channel_message_ids:
                        channel_message_ids.append(message_id)
                        await self.save_message_ids_to_file()
                        logger.info(f"📨 메시지 ID 추가됨 (다음 사이클에서 전송): {message_id}")
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
                    logger.info(f"🚀 새 메시지 즉시 전송 시도 {attempt + 1}/{max_retries} (ID: {message_id})")
                    success = await self.forward_message(message_data)
                    
                    if success:
                        # 전송 성공 시 기록
                        sent_messages[message_id] = current_time
                        
                        # 메시지 ID를 채널 메시지 목록에 추가 (없으면)
                        if message_id not in channel_message_ids:
                            channel_message_ids.append(message_id)
                            logger.info(f"📨 새 메시지 ID 추가: {message_id} (총 {len(channel_message_ids)}개)")
                            # 파일에 자동 저장 (Render에서도 영구 저장)
                            await self.save_message_ids_to_file()
                            logger.info(f"💾 메시지 ID 목록이 파일에 저장되었습니다.")
                        
                        logger.info(f"✅ 새 메시지 즉시 전송 완료 (ID: {message_id})")
                        return  # 성공하면 종료
                    else:
                        logger.warning(f"⚠️ 전송 실패 (success=False): {message_id}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)  # 1초 대기 후 재시도
                        else:
                            # 실패해도 메시지 ID는 추가 (다음 사이클에서 재시도)
                            if message_id not in channel_message_ids:
                                channel_message_ids.append(message_id)
                                await self.save_message_ids_to_file()
                                logger.info(f"📨 전송 실패했지만 메시지 ID 추가됨 (다음 사이클에서 재시도): {message_id}")
                except Exception as e:
                    logger.error(f"❌ 전송 시도 {attempt + 1}/{max_retries} 실패: {e}", exc_info=True)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # 1초 대기 후 재시도
                    else:
                        logger.error(f"❌ 최종 전송 실패, 메시지 ID는 추가하여 다음 사이클에서 재시도: {e}")
                        # 실패해도 메시지 ID는 추가 (다음 사이클에서 재시도)
                        if message_id not in channel_message_ids:
                            channel_message_ids.append(message_id)
                            await self.save_message_ids_to_file()
                            logger.info(f"📨 전송 실패했지만 메시지 ID 추가됨 (다음 사이클에서 재시도): {message_id}")
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
    
    async def forward_message(self, msg_data: dict, skip_first_message_check: bool = False):
        """개별 메시지를 모든 등록된 그룹으로 전달 (텔레그램 forward API 사용)
        
        Args:
            msg_data: 전송할 메시지 데이터
            skip_first_message_check: True이면 첫 메시지 스킵 로직을 사용하지 않음 (사이클에서 사용)
        """
        global registered_group_ids, new_group_first_message_sent, channel_message_ids
        
        if not registered_group_ids:
            logger.warning("등록된 그룹이 없습니다. 그룹에서 /월하 명령어를 사용하세요.")
            return None
        
        success_count = 0
        failed_groups = []
        
        # 첫 메시지인지 확인 (중복 방지) - skip_first_message_check가 False일 때만
        is_first_message = (not skip_first_message_check and channel_message_ids and msg_data['message_id'] == channel_message_ids[0])
        
        for group_id in registered_group_ids:
            # 첫 메시지이고 새로 등록된 그룹에 이미 전송했다면 스킵 (중복 방지)
            # 단, skip_first_message_check가 True이면 스킵하지 않음 (사이클에서는 모든 메시지 전송)
            if is_first_message and not skip_first_message_check and new_group_first_message_sent.get(group_id, False):
                logger.info(f"ℹ️ 그룹 {group_id}에 첫 메시지는 이미 전송되었습니다. 스킵합니다. (정상 동작)")
                success_count += 1  # 이미 전송된 것이므로 성공으로 카운트
                continue
            # 타임아웃 에러 재시도를 위한 루프
            max_retries = 3
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    if retry_count > 0:
                        logger.info(f"🔄 메시지 전달 재시도 {retry_count}/{max_retries - 1}: 채널={msg_data['chat_id']}, 메시지ID={msg_data['message_id']}, 그룹={group_id}")
                        await asyncio.sleep(2 * retry_count)  # 재시도 간격 증가
                    else:
                        logger.info(f"📤 메시지 전달 시도: 채널={msg_data['chat_id']}, 메시지ID={msg_data['message_id']}, 그룹={group_id}")
                    
                    # 메시지 전송 전에 봇이 그룹에 실제로 있는지 확인 (그룹 연동 확인)
                    try:
                        bot_member = await self.application.bot.get_chat_member(
                            chat_id=group_id,
                            user_id=self.application.bot.id
                        )
                        
                        # 봇이 그룹에서 제거되었거나 추가되지 않은 경우
                        if bot_member.status in ['left', 'kicked']:
                            logger.error(f"❌ 봇이 그룹 {group_id}에 없습니다. (상태: {bot_member.status})")
                            logger.error(f"   → 그룹이 아직 연동되지 않았거나 봇이 제거되었습니다.")
                            if group_id in registered_group_ids:
                                logger.warning(f"⚠️ 등록 목록에서 제거합니다: {group_id}")
                                registered_group_ids.remove(group_id)
                                await self.save_groups_to_file()
                            failed_groups.append(group_id)
                            break
                        
                        # 봇이 그룹에 있는지 확인 (member, administrator 등)
                        if bot_member.status not in ['member', 'administrator', 'creator']:
                            logger.warning(f"⚠️ 봇의 그룹 상태가 이상합니다: {bot_member.status} (그룹: {group_id})")
                            logger.warning(f"   → 메시지 전송을 시도하지만 실패할 수 있습니다.")
                            
                    except Exception as member_error:
                        error_msg = str(member_error).lower()
                        if "chat not found" in error_msg or "bot was kicked" in error_msg or "bot was blocked" in error_msg or "user not found" in error_msg:
                            logger.error(f"❌ 그룹 {group_id}을 찾을 수 없거나 봇이 제거되었습니다.")
                            logger.error(f"   → 그룹이 아직 연동되지 않았거나 봇이 제거되었습니다.")
                            if group_id in registered_group_ids:
                                logger.warning(f"⚠️ 등록 목록에서 제거합니다: {group_id}")
                                registered_group_ids.remove(group_id)
                                await self.save_groups_to_file()
                            failed_groups.append(group_id)
                            break
                        else:
                            # 네트워크 오류 등은 경고만 하고 계속 진행
                            logger.warning(f"⚠️ 그룹 멤버 확인 중 오류 발생 (계속 진행): {member_error}")
                    
                    # 텔레그램의 forward_message API를 사용하여 원본 메시지를 그대로 전달
                    logger.info(f"📤 forward_message API 호출: 채널={msg_data['chat_id']}, 메시지ID={msg_data['message_id']}, 그룹={group_id}")
                    result = await self.application.bot.forward_message(
                        chat_id=group_id,
                        from_chat_id=msg_data['chat_id'],
                        message_id=msg_data['message_id']
                    )
                    
                    # result 객체 확인
                    if result is None:
                        logger.error(f"❌ 메시지 전달 실패: result가 None입니다 (그룹: {group_id}, ID: {msg_data['message_id']})")
                        if retry_count < max_retries - 1:
                            retry_count += 1
                            continue
                        else:
                            failed_groups.append(group_id)
                            break
                    
                    if not hasattr(result, 'message_id') or result.message_id is None:
                        logger.error(f"❌ 메시지 전달 실패: message_id가 없습니다 (그룹: {group_id}, ID: {msg_data['message_id']})")
                        logger.error(f"   result 객체: {result}")
                        if retry_count < max_retries - 1:
                            retry_count += 1
                            continue
                        else:
                            failed_groups.append(group_id)
                            break
                    
                    forwarded_message_id = result.message_id
                    logger.info(f"✅ forward_message API 성공: 전달된 메시지 ID={forwarded_message_id}, 그룹={group_id}")
                    
                    # forward_message API가 성공했지만, 실제로 메시지가 전송되었는지 추가 확인
                    # 특히 그룹이 연동되기 전에 호출된 경우 실제 전송이 안 될 수 있음
                    await asyncio.sleep(1)  # 메시지 전송 완료 대기
                    
                    # 그룹 상태를 다시 확인하여 봇이 여전히 그룹에 있는지 확인
                    try:
                        verify_bot_member = await self.application.bot.get_chat_member(
                            chat_id=group_id,
                            user_id=self.application.bot.id
                        )
                        
                        # 봇이 그룹에서 제거된 경우
                        if verify_bot_member.status in ['left', 'kicked']:
                            logger.error(f"❌ 메시지 전송 후 봇이 그룹 {group_id}에서 제거되었습니다.")
                            logger.error(f"   → 메시지가 실제로 전송되지 않았을 수 있습니다.")
                            if retry_count < max_retries - 1:
                                retry_count += 1
                                logger.info(f"🔄 재시도 예정... (재시도 횟수: {retry_count}/{max_retries - 1})")
                                continue
                            else:
                                logger.error(f"❌ 최종 전송 실패: 봇이 그룹에 없습니다")
                                failed_groups.append(group_id)
                                break
                        
                        # 그룹 정보도 확인 (그룹이 존재하는지)
                        verify_chat = await self.application.bot.get_chat(chat_id=group_id)
                        logger.debug(f"✅ 그룹 확인 완료: {verify_chat.title} (그룹 ID: {group_id})")
                        
                    except Exception as verify_error:
                        error_msg = str(verify_error).lower()
                        if "chat not found" in error_msg or "bot was kicked" in error_msg or "bot was blocked" in error_msg:
                            logger.error(f"❌ 메시지 전송 후 그룹 {group_id} 확인 실패: 그룹을 찾을 수 없거나 봇이 제거되었습니다.")
                            logger.error(f"   → 메시지가 실제로 전송되지 않았을 수 있습니다.")
                            if group_id in registered_group_ids:
                                logger.warning(f"⚠️ 등록 목록에서 제거합니다: {group_id}")
                                registered_group_ids.remove(group_id)
                                await self.save_groups_to_file()
                            if retry_count < max_retries - 1:
                                retry_count += 1
                                logger.info(f"🔄 재시도 예정... (재시도 횟수: {retry_count}/{max_retries - 1})")
                                continue
                            else:
                                logger.error(f"❌ 최종 전송 실패: 그룹을 찾을 수 없습니다")
                                failed_groups.append(group_id)
                                break
                        else:
                            # 네트워크 오류 등은 경고만 하고 계속 진행 (메시지는 전송되었을 가능성이 높음)
                            logger.warning(f"⚠️ 그룹 확인 중 오류 발생 (메시지는 전송되었을 것으로 간주): {verify_error}")
                    
                    # 모든 확인이 완료되었으므로 메시지 전송 성공으로 간주
                    logger.info(f"✅ 메시지 전달 성공 확인! (원본 ID: {msg_data['message_id']}, 전달된 메시지 ID: {forwarded_message_id}, 그룹: {group_id})")
                    
                    success_count += 1
                    success = True
                    # API 제한을 피하기 위해 약간의 지연
                    await asyncio.sleep(0.3)
                    break  # 성공 시 루프 종료
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    full_error = str(e)
                    
                    # 타임아웃 에러는 재시도
                    if ("timed out" in error_msg or "timeout" in error_msg) and retry_count < max_retries - 1:
                        logger.warning(f"⏱️ 타임아웃 발생 (시도: {retry_count + 1}/{max_retries}). 재시도 중...")
                        retry_count += 1
                        continue  # 재시도
                    # 그룹을 찾을 수 없거나 봇이 제거된 경우 목록에서 제거 (재시도 안 함)
                    elif "chat not found" in error_msg or "bot was kicked" in error_msg or "bot was blocked" in error_msg:
                        logger.warning(f"그룹 {group_id}을 찾을 수 없거나 봇이 제거되었습니다. 목록에서 제거합니다.")
                        if group_id in registered_group_ids:
                            registered_group_ids.remove(group_id)
                            await self.save_groups_to_file()
                            logger.info(f"💾 그룹 제거 후 목록이 파일에 저장되었습니다: {registered_group_ids}")
                        failed_groups.append(group_id)
                        break  # 재시도 안 함
                    elif "forbidden" in error_msg:
                        logger.warning(f"그룹 {group_id}에서 권한이 없습니다. (메시지 전송 권한 필요)")
                        failed_groups.append(group_id)
                        break  # 재시도 안 함
                    else:
                        # 다른 에러도 재시도 (최대 횟수까지)
                        if retry_count < max_retries - 1:
                            logger.warning(f"⚠️ 메시지 전달 실패 (시도: {retry_count + 1}/{max_retries}): {full_error}. 재시도 중...")
                            retry_count += 1
                            continue  # 재시도
                        else:
                            logger.error(f"❌ 메시지 전달 최종 실패 (그룹: {group_id}, ID: {msg_data['message_id']}): {full_error}")
                            failed_groups.append(group_id)
                            break  # 최대 재시도 횟수 초과
        
        if success_count > 0:
            logger.info(f"메시지 전달 완료: {success_count}개 그룹에 전송됨 (실패: {len(failed_groups)}개)")
        else:
            logger.error(f"모든 그룹에 메시지 전달 실패")
        
        return success_count > 0
    
    
    async def load_message_ids_from_file(self):
        """파일에서 메시지 ID 목록 불러오기 (중복 제거)"""
        global channel_message_ids
        try:
            from pathlib import Path
            ids_file = Path(__file__).parent / 'message_ids.txt'
            logger.info(f"메시지 ID 파일 경로: {ids_file.absolute()}")
            
            if ids_file.exists():
                loaded_ids = set()  # 중복 제거를 위해 set 사용
                file_content = []
                with open(ids_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        file_content.append(line)
                        # 주석이나 빈 줄 건너뛰기
                        if line and not line.startswith('#'):
                            try:
                                msg_id = int(line)
                                loaded_ids.add(msg_id)  # set에 추가 (자동 중복 제거)
                            except ValueError as ve:
                                logger.debug(f"라인 '{line}'을 정수로 변환 실패: {ve}")
                                continue
                
                # 기존 리스트와 병합하면서 중복 제거
                before_count = len(channel_message_ids)
                channel_message_ids = list(set(channel_message_ids) | loaded_ids)  # 중복 제거된 합집합
                after_count = len(channel_message_ids)
                new_count = after_count - before_count
                
                logger.info(f"파일 내용 (처음 10줄): {file_content[:10]}")
                if new_count > 0:
                    logger.info(f"파일에서 메시지 ID {new_count}개를 새로 불러왔습니다. (총 {after_count}개, 중복 제거됨)")
                    logger.info(f"로드된 메시지 ID 목록: {sorted(channel_message_ids)}")
                elif after_count > 0:
                    logger.info(f"파일에서 메시지 ID를 불러왔지만 모두 이미 등록되어 있습니다. (총 {after_count}개)")
                else:
                    logger.warning(f"파일에서 메시지 ID를 불러왔지만 등록된 메시지가 없습니다. (파일 내용: {file_content})")
            else:
                logger.warning(f"message_ids.txt 파일이 없습니다. 경로: {ids_file.absolute()}")
        except Exception as e:
            logger.error(f"메시지 ID 파일 읽기 실패: {e}", exc_info=True)
    
    async def save_message_ids_to_file(self):
        """메시지 ID 목록을 파일에 저장 (봇 재시작 시에도 유지됨, Render에서도 자동 저장, 중복 제거)"""
        global channel_message_ids
        max_retries = 3
        retry_delay = 1
        
        # 저장 전에 중복 제거
        channel_message_ids = list(set(channel_message_ids))  # 중복 제거
        
        for attempt in range(max_retries):
            try:
                from pathlib import Path
                ids_file = Path(__file__).parent / 'message_ids.txt'
                file_path = str(ids_file.absolute())
                
                with open(ids_file, 'w', encoding='utf-8') as f:
                    f.write("# 채널에 있는 메시지 ID 목록\n")
                    f.write("# 한 줄에 하나씩 메시지 ID만 입력\n")
                    f.write("# 봇이 자동으로 관리하므로 수동 수정 불필요\n\n")
                    for msg_id in sorted(channel_message_ids):
                        f.write(f"{msg_id}\n")
                
                # 파일이 제대로 저장되었는지 확인
                if ids_file.exists():
                    file_size = ids_file.stat().st_size
                    logger.info(f"💾 메시지 ID {len(channel_message_ids)}개를 파일에 저장했습니다 (경로: {file_path}, 크기: {file_size} bytes)")
                    logger.info(f"📋 저장된 메시지 ID: {sorted(channel_message_ids)}")
                    return  # 성공하면 종료
                else:
                    raise Exception("파일이 생성되지 않았습니다.")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ 메시지 ID 파일 저장 시도 {attempt + 1}/{max_retries} 실패, 재시도 중...: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ 메시지 ID 파일 저장 최종 실패 ({max_retries}회 시도): {e}", exc_info=True)
    
    async def load_groups_from_file(self):
        """파일에서 등록된 그룹 ID 목록 불러오기"""
        global registered_group_ids
        try:
            from pathlib import Path
            groups_file = Path(__file__).parent / 'registered_groups.txt'
            if groups_file.exists():
                loaded_count = 0
                loaded_groups = []
                with open(groups_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if line not in registered_group_ids:
                                registered_group_ids.append(line)
                                loaded_groups.append(line)
                                loaded_count += 1
                if loaded_count > 0:
                    logger.info(f"✅ 파일에서 그룹 ID {loaded_count}개를 불러왔습니다: {loaded_groups}")
                    logger.info(f"📋 현재 등록된 그룹 총 {len(registered_group_ids)}개: {registered_group_ids}")
                else:
                    logger.info(f"📋 파일에서 불러온 그룹이 없습니다. 현재 등록된 그룹: {len(registered_group_ids)}개")
            else:
                # 파일이 없으면 config의 기본 그룹만 사용
                logger.info(f"⚠️ registered_groups.txt 파일이 없습니다. config.py의 기본 그룹을 사용합니다.")
                logger.info(f"📋 현재 등록된 그룹: {len(registered_group_ids)}개 - {registered_group_ids}")
        except Exception as e:
            logger.error(f"❌ 그룹 ID 파일 읽기 실패: {e}", exc_info=True)
    
    async def save_groups_to_file(self):
        """등록된 그룹 ID 목록을 파일에 저장 (Render에서도 자동 저장, 재배포 없이 유지됨)"""
        global registered_group_ids
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                from pathlib import Path
                groups_file = Path(__file__).parent / 'registered_groups.txt'
                file_path = str(groups_file.absolute())
                
                with open(groups_file, 'w', encoding='utf-8') as f:
                    f.write("# 등록된 그룹 ID 목록\n")
                    f.write("# 한 줄에 하나씩 그룹 ID만 입력\n")
                    f.write("# 그룹에서 /월하 명령어로 자동 추가됨\n\n")
                    for group_id in registered_group_ids:
                        f.write(f"{group_id}\n")
                
                # 파일이 제대로 저장되었는지 확인
                if groups_file.exists():
                    file_size = groups_file.stat().st_size
                    logger.info(f"💾 그룹 ID {len(registered_group_ids)}개를 파일에 저장했습니다 (경로: {file_path}, 크기: {file_size} bytes)")
                    logger.info(f"📋 저장된 그룹 목록: {registered_group_ids}")
                    return  # 성공하면 종료
                else:
                    raise Exception("파일이 생성되지 않았습니다.")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ 그룹 ID 파일 저장 시도 {attempt + 1}/{max_retries} 실패, 재시도 중...: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ 그룹 ID 파일 저장 최종 실패 ({max_retries}회 시도): {e}", exc_info=True)
    
    async def load_settings_from_file(self):
        """설정값 불러오기 (우선순위: 환경 변수 > 파일 > 기본값)"""
        global current_message_interval, current_resend_wait_time
        import os
        
        # 1. 환경 변수에서 먼저 확인 (Render 대시보드에서 설정한 값)
        env_interval = os.environ.get("MESSAGE_INTERVAL_SECONDS")
        env_resend = os.environ.get("RESEND_WAIT_TIME_SECONDS")
        
        if env_interval:
            try:
                current_message_interval = int(env_interval)
                logger.info(f"✅ 환경 변수에서 설정 로드: 메시지 간격 = {current_message_interval // 60}분")
            except ValueError:
                logger.warning(f"⚠️ 환경 변수 MESSAGE_INTERVAL_SECONDS 파싱 실패: {env_interval}")
        
        if env_resend:
            try:
                current_resend_wait_time = int(env_resend)
                logger.info(f"✅ 환경 변수에서 설정 로드: 재전송 간격 = {current_resend_wait_time // 60}분")
            except ValueError:
                logger.warning(f"⚠️ 환경 변수 RESEND_WAIT_TIME_SECONDS 파싱 실패: {env_resend}")
        
        # 2. 환경 변수가 없으면 파일에서 로드
        if not env_interval or not env_resend:
            try:
                from pathlib import Path
                settings_file = Path(__file__).parent / 'settings.txt'
                if settings_file.exists():
                    with open(settings_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                if '=' in line:
                                    key, value = line.split('=', 1)
                                    key = key.strip()
                                    value = value.strip()
                                    try:
                                        if key == 'message_interval' and not env_interval:
                                            current_message_interval = int(value)
                                            logger.info(f"✅ 파일에서 설정 로드: 메시지 간격 = {current_message_interval // 60}분 ({current_message_interval}초)")
                                        elif key == 'resend_wait_time' and not env_resend:
                                            current_resend_wait_time = int(value)
                                            logger.info(f"✅ 파일에서 설정 로드: 재전송 간격 = {current_resend_wait_time // 60}분 ({current_resend_wait_time}초)")
                                    except ValueError:
                                        logger.warning(f"⚠️ 설정값 파싱 실패: {key}={value}")
                else:
                    logger.info(f"⚠️ settings.txt 파일이 없습니다.")
            except Exception as e:
                logger.error(f"❌ 설정 파일 읽기 실패: {e}", exc_info=True)
        
        logger.info(f"📋 최종 적용된 설정: 메시지 간격={current_message_interval // 60}분, 재전송 간격={current_resend_wait_time // 60}분")
    
    async def save_settings_to_file(self):
        """설정값을 파일에 저장 (메시지 간격, 재전송 간격) - Render 재시작 시 유지"""
        global current_message_interval, current_resend_wait_time
        import os
        max_retries = 3
        retry_delay = 1
        
        # 파일에 저장 (서비스 실행 중에는 유지됨)
        for attempt in range(max_retries):
            try:
                from pathlib import Path
                settings_file = Path(__file__).parent / 'settings.txt'
                file_path = str(settings_file.absolute())
                
                with open(settings_file, 'w', encoding='utf-8') as f:
                    f.write("# 봇 설정값 (초 단위)\n")
                    f.write("# 메시지 간 전송 간격 (초)\n")
                    f.write(f"message_interval={current_message_interval}\n")
                    f.write("# 같은 메시지 재전송 간격 (초)\n")
                    f.write(f"resend_wait_time={current_resend_wait_time}\n")
                
                # 파일이 제대로 저장되었는지 확인
                if settings_file.exists():
                    file_size = settings_file.stat().st_size
                    logger.info(f"💾 설정값을 파일에 저장했습니다 (경로: {file_path}, 크기: {file_size} bytes)")
                    logger.info(f"📋 저장된 설정: 메시지 간격={current_message_interval // 60}분, 재전송 간격={current_resend_wait_time // 60}분")
                    break  # 성공하면 루프 종료
                else:
                    raise Exception("파일이 생성되지 않았습니다.")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ 설정 파일 저장 시도 {attempt + 1}/{max_retries} 실패, 재시도 중...: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ 설정 파일 저장 최종 실패 ({max_retries}회 시도): {e}", exc_info=True)
        
        # 참고: 환경 변수는 Python에서 직접 변경할 수 없으므로
        # Render 대시보드에서 수동으로 설정해야 합니다.
        # 환경 변수 설정 방법 안내 로그
        logger.info(f"💡 참고: Render 재시작 후에도 설정을 유지하려면 Render 대시보드의 Environment Variables에서 다음을 설정하세요:")
        logger.info(f"   MESSAGE_INTERVAL_SECONDS={current_message_interval}")
        logger.info(f"   RESEND_WAIT_TIME_SECONDS={current_resend_wait_time}")
    
    async def send_first_message_to_new_group(self, group_id: str, message_id: int):
        """새로 등록된 그룹에 첫 메시지만 즉시 전송 (중복 방지)"""
        global new_group_first_message_sent
        
        try:
            # 봇이 완전히 시작될 때까지 대기 (최대 60초, 배포 시간 고려)
            max_wait_time = 60
            wait_interval = 2
            waited = 0
            
            while not self.is_fully_started and waited < max_wait_time:
                await asyncio.sleep(wait_interval)
                waited += wait_interval
                if waited % 10 == 0:  # 10초마다 로그
                    logger.info(f"봇 시작 대기 중... ({waited}/{max_wait_time}초)")
            
            if not self.is_fully_started:
                logger.warning(f"봇이 {max_wait_time}초 내에 시작되지 않았습니다. 첫 메시지 전송을 건너뜁니다.")
                return
            
            # application이 초기화되었는지 확인
            if not self.application or not self.application.bot:
                logger.warning("봇 application이 초기화되지 않았습니다. 첫 메시지 전송을 건너뜁니다.")
                return
            
            # 추가 안정성 확인: 봇이 실제로 작동하는지 테스트
            try:
                await asyncio.sleep(3)  # 배포 완료 후 안정화 대기
                await self.application.bot.get_me()
            except Exception as e:
                logger.warning(f"봇 상태 확인 실패, 전송을 건너뜁니다: {e}")
                return
            
            # 이미 전송했는지 확인 (중복 방지)
            if new_group_first_message_sent.get(group_id, False):
                logger.info(f"그룹 {group_id}에 첫 메시지는 이미 전송되었습니다.")
                return
            
            message_data = {
                'chat_id': int(SOURCE_CHANNEL_ID),
                'message_id': message_id,
                'date': None
            }
            
            # 재시도 로직 (최대 3회)
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                try:
                    # 특정 그룹에만 전송
                    result = await self.application.bot.forward_message(
                        chat_id=group_id,
                        from_chat_id=message_data['chat_id'],
                        message_id=message_data['message_id']
                    )
                    
                    # 전송 완료 플래그 설정
                    new_group_first_message_sent[group_id] = True
                    logger.info(f"[새 그룹 첫 메시지] 그룹 {group_id}에 전송 완료 (ID: {message_id})")
                    break  # 성공하면 재시도 루프 종료
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # 메시지가 존재하지 않는 경우 재시도 불필요
                    if "message to forward not found" in error_msg or "message not found" in error_msg:
                        logger.warning(f"메시지 {message_id}가 채널에 존재하지 않습니다. 건너뜁니다.")
                        break
                    
                    # 네트워크 오류나 일시적 오류인 경우 재시도
                    if attempt < max_retries - 1:
                        logger.warning(f"첫 메시지 전송 실패 (그룹: {group_id}, ID: {message_id}, 시도 {attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(f"첫 메시지 전송 최종 실패 (그룹: {group_id}, ID: {message_id}): {e}")
            
        except Exception as e:
            logger.error(f"첫 메시지 전송 중 오류: {e}", exc_info=True)
    
    async def send_existing_messages_to_new_group(self, group_id: str):
        """새로 등록된 그룹에 기존 메시지들을 전송 (봇이 완전히 시작되고 배포가 완료된 후)"""
        try:
            # 봇이 완전히 시작될 때까지 대기 (최대 60초, 배포 시간 고려)
            max_wait_time = 60
            wait_interval = 2
            waited = 0
            
            while not self.is_fully_started and waited < max_wait_time:
                await asyncio.sleep(wait_interval)
                waited += wait_interval
                if waited % 10 == 0:  # 10초마다 로그
                    logger.info(f"봇 시작 대기 중... ({waited}/{max_wait_time}초)")
            
            if not self.is_fully_started:
                logger.warning(f"봇이 {max_wait_time}초 내에 시작되지 않았습니다. 기존 메시지 전송을 건너뜁니다.")
                return
            
            # application이 초기화되었는지 확인
            if not self.application or not self.application.bot:
                logger.warning("봇 application이 초기화되지 않았습니다. 기존 메시지 전송을 건너뜁니다.")
                return
            
            # 추가 안정성 확인: 봇이 실제로 작동하는지 테스트
            try:
                await asyncio.sleep(3)  # 배포 완료 후 안정화 대기
                # 간단한 API 호출로 봇 상태 확인
                await self.application.bot.get_me()
            except Exception as e:
                logger.warning(f"봇 상태 확인 실패, 전송을 건너뜁니다: {e}")
                return
            
            if not channel_message_ids:
                return
            
            logger.info(f"그룹 {group_id}에 기존 메시지 {len(channel_message_ids)}개 전송 시작 (첫 메시지만 즉시, 나머지는 10분 간격)...")
            
            for idx, message_id in enumerate(channel_message_ids, 1):
                message_data = {
                    'chat_id': int(SOURCE_CHANNEL_ID),
                    'message_id': message_id,
                    'date': None
                }
                
                # 재시도 로직 (최대 3회)
                max_retries = 3
                retry_delay = 2  # 재시도 간격 (초)
                
                for attempt in range(max_retries):
                    try:
                        # 특정 그룹에만 전송
                        result = await self.application.bot.forward_message(
                            chat_id=group_id,
                            from_chat_id=message_data['chat_id'],
                            message_id=message_data['message_id']
                        )
                        
                        logger.info(f"[기존 메시지 {idx}/{len(channel_message_ids)}] 그룹 {group_id}에 전송 완료 (ID: {message_id})")
                        break  # 성공하면 재시도 루프 종료
                        
                    except Exception as e:
                        error_msg = str(e).lower()
                        
                        # 메시지가 존재하지 않는 경우 재시도 불필요
                        if "message to forward not found" in error_msg or "message not found" in error_msg:
                            logger.warning(f"메시지 {message_id}가 채널에 존재하지 않습니다. 건너뜁니다.")
                            break
                        
                        # 네트워크 오류나 일시적 오류인 경우 재시도
                        if attempt < max_retries - 1:
                            logger.warning(f"기존 메시지 전송 실패 (그룹: {group_id}, ID: {message_id}, 시도 {attempt + 1}/{max_retries}): {e}")
                            await asyncio.sleep(retry_delay)
                        else:
                            logger.error(f"기존 메시지 전송 최종 실패 (그룹: {group_id}, ID: {message_id}): {e}")
                
                # 첫 메시지는 즉시 전송, 나머지는 10분 간격으로 전송
                if idx < len(channel_message_ids):
                    interval_min = current_message_interval // 60
                    logger.info(f"다음 메시지까지 {interval_min}분 대기 중...")
                    await asyncio.sleep(current_message_interval)
            
            logger.info(f"그룹 {group_id}에 기존 메시지 전송 완료")
        except Exception as e:
            logger.error(f"기존 메시지 전송 중 오류: {e}", exc_info=True)
    
    async def send_existing_messages_sequentially(self):
        """기존 채널 메시지를 순차적으로 무한 반복 전송 (10분 간격)"""
        import time
        
        # 파일에서 기존 메시지 ID 불러오기 (봇 재시작 시에도 유지됨)
        await self.load_message_ids_from_file()
        
        # 중복 제거 (혹시 모를 중복 방지)
        global channel_message_ids
        before_dedup = len(channel_message_ids)
        channel_message_ids = list(set(channel_message_ids))
        after_dedup = len(channel_message_ids)
        if before_dedup != after_dedup:
            logger.warning(f"⚠️ 중복된 메시지 ID {before_dedup - after_dedup}개를 제거했습니다. (총 {before_dedup}개 → {after_dedup}개)")
            await self.save_message_ids_to_file()  # 중복 제거된 목록 저장
        
        # getUpdates는 Conflict 오류를 일으킬 수 있으므로 제거
        # 새 메시지는 handle_channel_message에서 자동으로 추가됨
        
        logger.info(f"현재 등록된 메시지: {len(channel_message_ids)}개 (파일에서 불러옴, 중복 제거됨)")
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
                
                # 등록된 그룹이 없으면 사이클을 시작하지 않음
                if not registered_group_ids:
                    logger.warning("⚠️ 등록된 그룹이 없습니다. 메시지 전송을 건너뜁니다.")
                    logger.info("📋 그룹에서 /월하 명령어로 등록해주세요.")
                    await asyncio.sleep(60)  # 1분마다 다시 확인
                    continue
                
                logger.info(f"채널 메시지 {len(channel_message_ids)}개를 {current_message_interval // 60}분 간격으로 무한 반복 전송 시작...")
                logger.info(f"📋 등록된 그룹 {len(registered_group_ids)}개에 전송: {registered_group_ids}")
                
                cycle = 1
                while self.is_running and channel_message_ids:  # 메시지가 있을 때만 사이클 실행
                    # 등록된 그룹이 있는지 다시 확인
                    if not registered_group_ids:
                        logger.warning("⚠️ 등록된 그룹이 없어졌습니다. 사이클을 중단합니다.")
                        break
                    
                    logger.info(f"=== {cycle}번째 사이클 시작 (총 {len(channel_message_ids)}개 메시지) ===")
                    logger.info(f"📋 전송할 메시지 ID 목록: {sorted(channel_message_ids)}")
                    
                    # 사이클 시작 시 첫 메시지 스킵 플래그 초기화 (모든 메시지를 정상적으로 전송하기 위해)
                    # 첫 메시지 스킵 로직은 새 그룹 등록 시에만 필요하므로, 사이클에서는 모든 메시지를 전송해야 함
                    global new_group_first_message_sent
                    for group_id in registered_group_ids:
                        if new_group_first_message_sent.get(group_id, False):
                            logger.debug(f"그룹 {group_id}의 첫 메시지 스킵 플래그 초기화 (사이클 시작)")
                    new_group_first_message_sent.clear()
                    
                    for idx, message_id in enumerate(channel_message_ids, 1):
                        if not self.is_running:
                            logger.warning("봇이 중지되어 메시지 전송을 중단합니다.")
                            return
                        
                        logger.info(f"🔄 메시지 {idx}/{len(channel_message_ids)} 처리 시작 (ID: {message_id})")
                        message_data = {
                            'chat_id': int(SOURCE_CHANNEL_ID),
                            'message_id': message_id,
                            'date': None
                        }
                        
                        try:
                            # forward_message는 성공 시 True, 실패 시 False 반환
                            # 사이클에서는 첫 메시지 스킵 로직을 사용하지 않음 (모든 메시지 전송)
                            success = await self.forward_message(message_data, skip_first_message_check=True)
                            
                            if success:
                                # 전송 성공 시 기록 (로그용)
                                sent_messages[message_id] = time.time()
                                logger.info(f"✅ [사이클 {cycle}, {idx}/{len(channel_message_ids)}] 메시지 전송 완료 (ID: {message_id})")
                            else:
                                # 전송 실패 시 재시도 (최대 3회)
                                logger.warning(f"⚠️ [사이클 {cycle}, {idx}/{len(channel_message_ids)}] 메시지 전송 실패 (ID: {message_id}). 재시도 중...")
                                retry_success = False
                                for retry in range(3):
                                    await asyncio.sleep(2)  # 2초 대기 후 재시도
                                    retry_success = await self.forward_message(message_data, skip_first_message_check=True)
                                    if retry_success:
                                        logger.info(f"✅ 재시도 성공! (ID: {message_id}, 시도: {retry + 1}/3)")
                                        sent_messages[message_id] = time.time()
                                        break
                                    else:
                                        logger.warning(f"⚠️ 재시도 실패 (ID: {message_id}, 시도: {retry + 1}/3)")
                                
                                if not retry_success:
                                    logger.error(f"❌ [사이클 {cycle}, {idx}/{len(channel_message_ids)}] 메시지 전송 최종 실패 (ID: {message_id}). 다음 메시지로 진행합니다.")
                            
                            # 마지막 메시지가 아니면 설정된 간격만큼 대기
                            # 주의: current_message_interval은 전역 변수이므로 설정 변경 시 즉시 반영됨
                            if idx < len(channel_message_ids):
                                # 현재 설정값을 다시 읽어서 최신 값 사용 (설정 변경 즉시 반영)
                                interval_min = current_message_interval // 60
                                interval_sec = current_message_interval
                                logger.info(f"⏳ 다음 메시지까지 {interval_min}분 ({interval_sec}초) 대기 중... (현재 설정값 적용)")
                                try:
                                    await asyncio.sleep(current_message_interval)
                                    logger.info(f"✅ 대기 완료. 다음 메시지 전송 시작...")
                                except Exception as sleep_error:
                                    logger.error(f"❌ 대기 중 오류 발생: {sleep_error}", exc_info=True)
                                    # 오류가 발생해도 다음 메시지로 진행
                                    await asyncio.sleep(1)  # 최소 1초 대기 후 계속
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
                                interval_min = current_message_interval // 60
                                interval_sec = current_message_interval
                                logger.info(f"⏳ 다음 메시지까지 {interval_min}분 ({interval_sec}초) 대기 중... (오류 후)")
                                await asyncio.sleep(current_message_interval)
                                logger.info(f"✅ 대기 완료. 다음 메시지 전송 시작... (오류 후)")
                    
                    # 한 사이클 완료 후 재전송 대기 시간만큼 대기 후 다시 시작
                    # 메시지가 없으면 사이클 종료
                    if not channel_message_ids:
                        logger.info("등록된 메시지가 없어 사이클을 종료합니다.")
                        break
                    
                    # 사이클 간 재전송 대기 시간 적용
                    resend_wait_min = current_resend_wait_time // 60
                    resend_wait_sec = current_resend_wait_time
                    logger.info(f"✅ {cycle}번째 사이클 완료! (총 {len(channel_message_ids)}개 메시지 전송 완료)")
                    logger.info(f"⏳ 다음 사이클까지 {resend_wait_min}분 ({resend_wait_sec}초) 대기 중...")
                    await asyncio.sleep(current_resend_wait_time)
                    logger.info(f"✅ 대기 완료! {cycle + 1}번째 사이클 시작합니다...")
                    cycle += 1
                    
            except Exception as e:
                logger.error(f"기존 메시지 가져오기 중 오류: {e}", exc_info=True)
                await asyncio.sleep(60)  # 오류 발생 시 1분 후 재시도
    
    async def send_messages_to_group_callback(self, context: ContextTypes.DEFAULT_TYPE):
        """주기적으로 메시지를 전송하는 콜백"""
        await self.send_messages_to_group()

def run_keepalive_server():
    """KeepAlive 웹서버를 별도 스레드에서 실행 (Render에서도 작동)"""
    try:
        from keepalive import run_keepalive
        import threading
        import os
        # Render에서는 PORT 환경변수를 사용 (자동 할당됨)
        port = int(os.environ.get('PORT', 8080))
        logger.info(f"KeepAlive 서버 시작: 포트 {port} (PORT 환경변수: {os.environ.get('PORT', '없음')})")
        keepalive_thread = threading.Thread(target=run_keepalive, args=(port,), daemon=True)
        keepalive_thread.start()
        logger.info(f"✅ KeepAlive 서버가 시작되었습니다. (Render/UptimeRobot용, 포트: {port})")
        logger.info(f"🌐 KeepAlive URL: http://0.0.0.0:{port}/")
    except Exception as e:
        logger.warning(f"⚠️ KeepAlive 서버 시작 실패: {e} (봇은 정상 작동합니다)")

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

