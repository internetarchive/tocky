
import importlib.resources
import json
import re
from typing import Literal, TypedDict, cast

import yaml

from tocky.extractor import TocEntry


class PromptSample(TypedDict):
    label: str | None
    input: str
    output: list[dict]  # But you know as a dict


# Read from a file
with importlib.resources.open_text("tocky", "prompt_samples.yaml") as f:
    PROMPT_SAMPLES = cast(dict[str, PromptSample], yaml.safe_load(f))

SAMPLE_FORMAT = """
{label}

Input:
```
{input}
```

Output:
```{output_format}
{output}
```
""".strip()

SAMPLE_FORMAT_NO_INPUT = """
{label}

```{output_format}
{output}
```
""".strip()


JSON_INSTRUCTIONS = """
The format you will need to output is JSON of this type:

```ts
Array<{
  level: number,
  label: string | null,
  title: string | null,
  pagenum: string | null,

  // Optional fields not present on most books
  authors: string[] | null,
  subtitle: string | null,
  description: string | null,
}>
```
""".strip()

MARKDOWN_INSTRUCTIONS = """
The format you will need to output is:

```
* {label (optional)} | {title} | {page number}
```
""".strip()

def format_toc(toc: list[TocEntry], extraction_format: Literal["json", "markdown"]) -> str:
    if extraction_format == "json":
        return '\n'.join([
            '[',
            '  ' + ',\n  '.join(json.dumps(entry.to_dict()) for entry in toc),
            ']',
        ])
    elif extraction_format == "markdown":
        return '\n'.join([
            chapter.to_markdown()
            for chapter in toc
        ])
    else:
        raise ValueError(f"Unknown extraction format: {extraction_format}")
   

def format_prompt_sample(sample: PromptSample, extraction_format: Literal["json", "markdown"], show_input=True) -> str:
    template = SAMPLE_FORMAT if show_input else SAMPLE_FORMAT_NO_INPUT
    input_str = sample["input"].strip('\n')
    input_str = re.sub(r'^\|', '', input_str, flags=re.MULTILINE)
    output_toc = [TocEntry(**entry) for entry in sample["output"]]

    return template.format(
        label=sample.get("label", ""),
        input=input_str,
        output=format_toc(output_toc, extraction_format),
        output_format="" if extraction_format == "markdown" else extraction_format,
    ).strip()

def build_system_prompt(prompt_template: str, extraction_format: Literal["json", "markdown"], show_input=True) -> str:
    format_instructions = JSON_INSTRUCTIONS if extraction_format == "json" else MARKDOWN_INSTRUCTIONS
    return prompt_template.format(
        format_instructions=format_instructions,
        PROMPT_SAMPLES={
            sample_id: format_prompt_sample(sample, extraction_format, show_input)
            for sample_id, sample in PROMPT_SAMPLES.items()
        }
    )

def process_extracted_output(output: str, extraction_format: Literal["json", "markdown"]) -> list[TocEntry]:
    toc_str = output.strip().strip('`')
    if extraction_format == 'json':
      if toc_str.startswith('json'):
        # Skip first line
        toc_str = '\n'.join(toc_str.split('\n')[1:])
      return [
        TocEntry(**entry)
        for entry in json.loads(toc_str)
      ]
    elif extraction_format == 'markdown':
      def clean_line(line: str) -> str:
        pipes = len(line.split('|')) - 1
        m = re.search(r'^ *\*+', line)
        if not m:
          return line
        stars = m.group()
        rest = line[m.span()[1]:]
        if pipes == 0:
          return f'{stars} | {rest.strip()} |'
        elif pipes == 1:
          return f'{stars} | {rest.strip()}'
        elif pipes == 2:
          return line
        elif pipes == 3:
          return line.replace('|', ' ', 1)
        else:
          # Not good
          return line

      return [
        TocEntry.from_markdown(clean_line(line))
        for line in toc_str.split('\n')
      ]
    else:
      raise ValueError(f"Unknown extraction format: {extraction_format}")
