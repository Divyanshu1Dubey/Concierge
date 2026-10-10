"""
WebSocket consumers for real-time staff chat.

Only authenticated practice staff may connect, and only to a conversation that
belongs to their own practice (agency admins may join any). Patients use the
HTTP widget endpoints instead.
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Conversation, Message

MAX_MESSAGE_LENGTH = 4000


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for a single tenant-scoped conversation."""

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs'].get('conversation_id')
        user = self.scope.get('user')
        if not self.conversation_id or not (user and user.is_authenticated):
            await self.close(code=4401)
            return

        self.conversation = await self.get_authorized_conversation(user, self.conversation_id)
        if self.conversation is None:
            await self.close(code=4403)
            return

        self.room_group_name = f'chat_{self.conversation.id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if getattr(self, 'room_group_name', None):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content):
        message = str(content.get('message', '')).strip()[:MAX_MESSAGE_LENGTH]
        if not message:
            return
        saved = await self.save_staff_message(self.conversation, message)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'sender': 'staff',
                'content': message,
                'timestamp': saved.created_at.isoformat(),
            }
        )

    async def chat_message(self, event):
        await self.send_json(event)

    @database_sync_to_async
    def get_authorized_conversation(self, user, conv_id):
        try:
            conversation = Conversation.objects.filter(id=conv_id).first()
        except Exception:
            return None
        if not conversation:
            return None
        if user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN':
            return conversation
        if user.practice_id and conversation.practice_id == user.practice_id:
            return conversation
        return None

    @database_sync_to_async
    def save_staff_message(self, conversation, content):
        msg = Message.objects.create(conversation=conversation, sender=Message.SENDER_STAFF, content=content)
        Conversation.objects.filter(id=conversation.id).update(last_activity_at=timezone.now())
        return msg
