from dataclasses import dataclass
from typing import Generic, TypeVar

from tocky.utils import ShareableState

@dataclass
class TocEntry:
    level: int
    label: str | None = None
    title: str | None = None
    pagenum: str | None = None
    
    authors: list[str] | None = None
    subtitle: str | None = None
    description: str | None = None

    @staticmethod
    def from_markdown(line: str) -> 'TocEntry':
        """
        >>> TocEntry.from_markdown("* 1 | Introduction | 1")
        TocEntry(level=1, label='1', title='Introduction', pagenum='1')
        >>> TocEntry.from_markdown("** 1.1 | Subsection | 2")
        TocEntry(level=2, label='1.1', title='Subsection', pagenum='2')
        >>> TocEntry.from_markdown("| Chapter 1 | 3")
        TocEntry(level=0, label=None, title='Chapter 1', pagenum='3')
        """
        parts = line.split('|')
        if len(parts) != 4:
            raise ValueError(f"Invalid line: {line}")
        
        def count_stars(s: str) -> int:
            i = 0
            for i, c in enumerate(s):
                if c != '*':
                    return i
            return i

        prefix, title, pagenum = parts
        return TocEntry(
            level=count_stars(prefix.lstrip()) - 1,
            label=prefix.lstrip('*').strip() or None,
            title=title.strip() or None,
            pagenum=pagenum.strip() or None,
        )

    def to_markdown(self) -> str:
        """
        >>> TocEntry(level=1, label='1', title='Introduction', pagenum='1').to_markdown()
        '    ** 1 | Introduction | 1'
        >>> TocEntry(level=2, label='1.1', title='Subsection', pagenum='2').to_markdown()
        '        *** 1.1 | Subsection | 2'
        >>> TocEntry(level=0, label=None, title='Chapter 1', pagenum='3').to_markdown()
        '* | Chapter 1 | 3'
        >>> TocEntry(level=0, label=None, title='Chapter 1', pagenum=None).to_markdown()
        '* | Chapter 1 | '
        >>> TocEntry(level=0, label=None, title=None, pagenum=None).to_markdown()
        '* |  | '
        """
        # Error if any other field is not None
        if self.authors or self.subtitle or self.description:
            raise ValueError("Cannot convert to markdown with authors, subtitle, or description")

        result = ('    ' * self.level) + ('*' * (self.level + 1))
        if self.label:
            result += f' {self.label}'
        result += f" | {self.title} | {self.pagenum or ''}"
        return result.rstrip()

    def to_dict(self) -> dict:
        """
        >>> TocEntry(level=1, label='1', title='Introduction', pagenum='1').to_dict()
        {'level': 1, 'label': '1', 'title': 'Introduction', 'pagenum': '1'}
        """
        # Remove all None
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class TocResponse:
  toc: list[TocEntry]
  prompt_tokens: int
  completion_tokens: int


TParams = TypeVar("TParams")

class AbstractExtractor(Generic[TParams]):
    name: str
    P: TParams
    S: ShareableState
    debug = True
    """
    When debug is set to true, extra helper variables could be set
    """

    def __init__(self):
        self.S = ShareableState()

    toc_raw_ocr: list[str] | None = None
    toc_flat_ocr: list[str] | None = None
    toc_response: TocResponse | None = None

    def predict_cost(self) -> float:
        raise NotImplementedError()

    def extract(self, ocaid: str, detector_result: list[int]) -> list[TocEntry]:
        raise NotImplementedError()
