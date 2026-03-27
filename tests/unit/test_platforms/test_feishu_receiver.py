"""Tests for Feishu event -> IncomingMessage conversion."""

import json

from src.platforms.feishu.receiver import parse_feishu_event


class TestParseFeishuEvent:
    def test_text_message(self) -> None:
        event = {
            "message": {
                "message_id": "om_abc123",
                "message_type": "text",
                "content": json.dumps({"text": "hello world"}),
                "chat_id": "oc_xyz",
                "chat_type": "p2p",
            },
            "sender": {
                "sender_id": {"open_id": "ou_user1", "user_id": ""},
                "sender_type": "user",
            },
        }
        msg = parse_feishu_event(event)
        assert msg is not None
        assert msg.platform == "feishu"
        assert msg.chat_id == "oc_xyz"
        assert msg.message_id == "om_abc123"
        assert msg.user_id == "ou_user1"
        assert msg.text == "hello world"
        assert msg.command is None

    def test_command_message(self) -> None:
        event = {
            "message": {
                "message_id": "om_cmd",
                "message_type": "text",
                "content": json.dumps({"text": "/new --force"}),
                "chat_id": "oc_xyz",
                "chat_type": "p2p",
            },
            "sender": {
                "sender_id": {"open_id": "ou_user1", "user_id": ""},
                "sender_type": "user",
            },
        }
        msg = parse_feishu_event(event)
        assert msg is not None
        assert msg.command == "new"
        assert msg.command_args == ["--force"]
        assert msg.text == "--force"

    def test_mention_stripping(self) -> None:
        event = {
            "message": {
                "message_id": "om_m",
                "message_type": "text",
                "content": json.dumps({"text": "@_user_1 do something"}),
                "chat_id": "oc_xyz",
                "chat_type": "group",
                "mentions": [{"key": "@_user_1", "name": "bot"}],
            },
            "sender": {
                "sender_id": {"open_id": "ou_user2", "user_id": ""},
                "sender_type": "user",
            },
        }
        msg = parse_feishu_event(event)
        assert msg is not None
        assert msg.text == "do something"

    def test_image_message(self) -> None:
        event = {
            "message": {
                "message_id": "om_img",
                "message_type": "image",
                "content": json.dumps({"image_key": "img_key_123"}),
                "chat_id": "oc_xyz",
                "chat_type": "p2p",
            },
            "sender": {
                "sender_id": {"open_id": "ou_user1", "user_id": ""},
                "sender_type": "user",
            },
        }
        msg = parse_feishu_event(event)
        assert msg is not None
        assert len(msg.images) == 1
        assert msg.images[0].file_id == "img_key_123"

    def test_post_message(self) -> None:
        event = {
            "message": {
                "message_id": "om_post",
                "message_type": "post",
                "content": json.dumps({
                    "title": "My Title",
                    "content": [
                        [{"tag": "text", "text": "line 1"}],
                        [{"tag": "text", "text": "line 2"}],
                    ],
                }),
                "chat_id": "oc_xyz",
                "chat_type": "p2p",
            },
            "sender": {
                "sender_id": {"open_id": "ou_user1", "user_id": ""},
                "sender_type": "user",
            },
        }
        msg = parse_feishu_event(event)
        assert msg is not None
        assert "My Title" in msg.text
        assert "line 1" in msg.text
        assert "line 2" in msg.text

    def test_empty_event(self) -> None:
        msg = parse_feishu_event({})
        assert msg is not None
        # Empty message type falls into unsupported branch
        assert msg.message_id == ""

    def test_file_message(self) -> None:
        event = {
            "message": {
                "message_id": "om_file",
                "message_type": "file",
                "content": json.dumps({
                    "file_key": "file_key_abc",
                    "file_name": "report.pdf",
                }),
                "chat_id": "oc_xyz",
                "chat_type": "p2p",
            },
            "sender": {
                "sender_id": {"open_id": "ou_user1", "user_id": ""},
                "sender_type": "user",
            },
        }
        msg = parse_feishu_event(event)
        assert msg is not None
        assert len(msg.files) == 1
        assert msg.files[0].filename == "report.pdf"
