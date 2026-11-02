"""How many chats one account keeps pinned.

The drawer reads every pin on each open, so the pins are a bounded list: pinning past
this is refused (chat's ``PinLimitError``), and the drawer's read stops here.
"""

MAX_PINNED_CHATS = 50
