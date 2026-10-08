"""
WebSocket consumers for real-time chat.
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
import json
from .models import Conversation, Message
from apps.ai_service.engine import AIEngine


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for real-time chat."""

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs'].get('conversation_id')
        self.room_group_name = f'chat_{self.conversation_id}' if self.conversation_id else 'chat_global'

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content):
        message = content.get('message', '')
        email = content.get('email', '')

        # Get or create conversation
        conversation = await self.get_or_create_conversation(self.conversation_id, email)

        # Save user message
        await self.save_message(conversation, 'user', message)

        # Send user message to group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'sender': 'user',
                'content': message,
                'timestamp': str(conversation.last_activity_at),
            }
        )

        # Get AI response
        engine = AIEngine()
        result = engine.chat(message)

        # Save AI message
        await self.save_message(
            conversation, 'ai', result.get('content', ''),
            intent=result.get('intent', ''),
            confidence=result.get('confidence', 0.0),
        )

        # Send AI response to group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'sender': 'ai',
                'content': result.get('content', ''),
                'intent': result.get('intent', ''),
                'confidence': result.get('confidence', 0.0),
            }
        )

    async def chat_message(self, event):
        await self.send_json(event)

    @database_sync_to_async
    def get_or_create_conversation(self, conv_id, email):
        if conv_id:
            return Conversation.objects.get(id=conv_id)
        return Conversation.objects.create(patient_email=email)

    @database_sync_to_async
    def save_message(self, conversation, sender, content, intent='', confidence=0.0):
        return Message.objects.create(
            conversation=conversation,
            sender=sender,
            content=content,
            intent=intent,
            confidence=confidence,
        )
