"""Schedule models preserve their existing DB contracts."""

from app.models.orm import Chat, TodoItem


def test_schedule_model_preserves_table_and_foreign_keys() -> None:
    assert TodoItem.__tablename__ == "todo_items"
    assert {
        column.name: next(iter(column.foreign_keys)).target_fullname
        for column in TodoItem.__table__.columns
        if column.foreign_keys
    } == {
        "user_id": "users.id",
        "chat_id": "chats.id",
    }
    assert "project_id" not in TodoItem.__table__.columns
    assert "project_id" not in Chat.__table__.columns
    assert "quiz_mode" not in Chat.__table__.columns
