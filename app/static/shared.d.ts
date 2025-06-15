type TocEntry = {
    label: string;
    title: string;
    pagenum: string;
    authors?: string[];
    subtitle?: string;
    description?: string;
}

type TaggedWord = {
    word: string;
    tocEntry: TocEntry;
    tocPath: string;
    tocWordOffset: number;
}

type StitchedWord = TaggedWord & {
    ocrWords: OcrWord[];
}
