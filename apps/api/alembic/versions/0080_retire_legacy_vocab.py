"""Retire the old beginner catalog and its saved Learning entries.

Revision ID: 0080_retire_legacy_vocab
Revises: 0079_learning_practice

The product explicitly removes the old words, groups, and associated practice
history. The frozen keep set below must not import a future mutable catalog.
Existing progress for the retained entries and class daily goals are preserved.
"""

import json
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0080_retire_legacy_vocab"
down_revision = "0079_learning_practice"
branch_labels = None
depends_on = None

KEPT_CATALOG = {
    "en": {
        "titles": (
            "Useful conversation expressions",
            "Everyday phrasal verbs",
            "Everyday idioms",
            "Common proverbs",
        ),
        "decks": (
            "3846eecb-ea05-5bad-b1f2-6207faa53d10",
            "bb8e17c6-f0ec-5b88-b4b8-b57e1d627537",
            "6419228d-8a78-53b1-9d1f-0312fda68bf9",
            "feab861e-e2e2-5a6e-90d7-b5760a9bdfdd",
        ),
        "entries": (
            "b8d37116-9b6a-51b8-a844-d3f15f9591cc",
            "04d9a5cc-8697-5daf-9fbe-19868f0ce72e",
            "0642bcbd-4e88-58f7-bb1e-1e34c6435d99",
            "72a2a9fb-59f5-5a19-9b86-d6c05447bd20",
            "fd64998b-8df0-5ad4-bc0f-796f16952e66",
            "cecdb29e-9814-516e-9534-bd7c651dac2d",
            "7bedfd64-abf7-596d-bf0a-f8d2d2e00eca",
            "a5ecd336-8e4c-5c95-bc16-3d1cfb494c21",
            "1dd8e7c8-f3d7-5507-a250-eefef6b26d57",
            "f863c4b8-0efc-5f5f-b1dc-58d496aed425",
            "cce12b98-04f6-5b8e-97ab-d34a823e1fac",
            "e9e4ec2d-fe7e-5b1f-a5fc-583ef33b9a96",
            "5ed0a455-e6be-57f7-99bc-c642d2f72285",
            "c0f82a2c-3801-5c6a-a9ad-15e5c2e60d93",
            "a6d5bdce-cd1b-5c33-980d-35700e80f51b",
            "58e14ff2-593a-5f49-9214-6460634185b8",
            "fbdcb84b-e94b-56d8-af72-85f70f7cfa07",
            "ab9354ef-062d-5dd6-a836-494d61543bb3",
            "2fa909c5-b249-5f73-b0a7-50eeac06f9ba",
            "656762bc-da28-5618-8f0d-31057c57284c",
            "a8389771-69be-57e9-b485-6ceb850a720f",
            "308adc50-bd5e-5ff0-b3af-20e6d469aff9",
            "76f5c344-2fd1-5556-b156-87a2d5fa23ac",
            "9cdda375-c15e-52ec-b054-9a0c27ea2ec7",
            "80b5bb78-9797-5ce0-8f3f-21f6aceb5fc5",
            "99cec5f0-d87f-50f9-9915-59455a7236ac",
            "c92043f8-1dd6-5e31-97f5-59853c6b09d2",
            "3c0e67f4-c8a5-5436-8bc7-36ad7fb2f561",
            "4e3a81ad-5e5e-5c00-9416-2707c3b5c97a",
            "224de172-b4b2-5207-ae00-45891a75c697",
            "c25c1101-083a-5312-baae-4cc4d457b033",
            "6a94fbd8-285e-5bea-95ef-049dcf7f0b3a",
            "50a24f14-a526-5082-8c2d-7ebd3de8b0a4",
            "a5a822d2-171d-50aa-adc4-8b91e9da59c6",
            "8c90e60f-4e2c-5adf-af3b-7a1586a43073",
            "21914fd7-2f4c-517d-965d-85f78812ab9b",
            "39a4e076-2c12-5c43-ba98-777f5d215a8d",
            "c6acaf43-b43f-5f03-be88-302e13f8b11b",
            "a64eb78a-0559-5059-bad9-3604c7b3a55b",
            "f32b14c2-18ba-542b-a5c7-ffe52043da79",
        ),
    },
    "es": {
        "titles": ("Everyday Idioms", "Everyday Proverbs"),
        "decks": ("c8e1b9de-8f28-53f1-9070-6ca547ea34d9", "f85dcc70-7b6d-5526-82e2-2d5f9133043c"),
        "entries": (
            "024a1b0a-c482-59d1-9c6a-626520182bc5",
            "3f179c65-1ee8-5605-82b6-4d20ab9136cd",
            "84b35402-9f7e-5515-a873-e8dd8e3dc02d",
            "0aa083e5-cc6c-5b20-b31a-6f87c24d701c",
            "bbafa8ae-7f44-558b-a97c-7c73678082eb",
            "3666327c-97a0-5e4a-9610-04359b965351",
            "3a627f20-1abe-5d50-9d40-a6afd9b66cce",
            "0f25d988-f788-5044-bd27-d83032465bd1",
            "4e8c555a-88cd-5e6f-a96c-29284fe3974d",
            "0fc2d3b6-87f2-5f10-bd87-3014a1916517",
            "e97d356a-ccde-54bb-8070-82cd8c2ae93f",
            "b3574a6e-45c6-512b-8a38-f80443550174",
            "cbd81136-697d-52ca-ab0e-91433ae84735",
            "8e90eeac-ab48-594c-aee7-a8d0b90807ba",
            "b5431c25-6256-509a-9278-9c02ad5cfb93",
            "64880d65-21ba-5e8a-83a5-ab1357032b3e",
            "01064269-ba24-5567-8d7e-4cd099ca6f73",
            "434e932b-e0b9-5c90-a07c-a952c323e08a",
            "991ecbe7-cc10-50de-975c-1ce9ccafb18a",
            "da0d45ff-5e98-5a0e-833d-332f13c19be9",
        ),
    },
}


def _ids(name: str, values: tuple[str, ...]) -> sa.BindParameter:
    return sa.bindparam(
        name,
        [UUID(value) for value in values],
        expanding=True,
        type_=postgresql.UUID(as_uuid=True),
    )


def upgrade() -> None:
    for language, retained in KEPT_CATALOG.items():
        # Delete user rows before catalog deletion can SET their foreign key NULL.
        # Item FKs cascade the retired words' miss and practice events.
        op.execute(
            sa.text(
                "DELETE FROM project_items AS item USING projects AS project "
                "WHERE item.project_id = project.id AND item.user_id = project.user_id "
                "AND project.kind IN ('language', 'vocabulary') "
                "AND lower(trim(COALESCE(project.target_language, 'en'))) = :language "
                "AND (item.catalog_entry_id IS NULL OR item.catalog_entry_id NOT IN :entries)"
            )
            .bindparams(language=language)
            .bindparams(_ids("entries", retained["entries"]))
        )
        op.execute(
            sa.text(
                "DELETE FROM vocab_entries AS entry USING vocab_decks AS deck "
                "WHERE entry.deck_id = deck.id AND deck.target_language = :language "
                "AND entry.id NOT IN :entries"
            )
            .bindparams(language=language)
            .bindparams(_ids("entries", retained["entries"]))
        )
        op.execute(
            sa.text(
                "DELETE FROM vocab_decks WHERE target_language = :language AND id NOT IN :decks"
            )
            .bindparams(language=language)
            .bindparams(_ids("decks", retained["decks"]))
        )
        op.execute(
            sa.text(
                "UPDATE projects SET learning_path = CAST(:path AS jsonb) "
                "WHERE kind IN ('language', 'vocabulary') "
                "AND lower(trim(COALESCE(target_language, 'en'))) = :language"
            ).bindparams(language=language, path=json.dumps(retained["titles"]))
        )


def downgrade() -> None:
    raise RuntimeError(
        "Retired vocabulary and its practice history cannot be restored by downgrade."
    )
