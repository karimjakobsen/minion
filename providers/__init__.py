from typing import TypedDict, List, Optional

class Item(TypedDict, total=False):
    title: str
    url: Optional[str]
    summary: Optional[str]
    rendered: str

class Section(TypedDict):
    heading: str
    items: List[Item]
