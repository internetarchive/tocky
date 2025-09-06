type LLMModel = {
    provider: 'openai';
    model: string;
    input_price_pm: number;
    cached_input_price_pm: number | null;
    output_price_pm: number;
    knowledge_cutoff: string;
    supports_temperature: boolean;
    supports_batch: boolean;
    can_input_text: boolean;
    can_input_images: boolean;
    can_input_audio: boolean;
    can_output_text: boolean;
    can_output_images: boolean;
    is_deprecated: boolean;
    supports_chat_completion_api: boolean;
    supports_responses_api: boolean;
    supports_streaming: boolean;
    supports_reasoning: boolean;
    context_window_tokens: number | null;
    max_output_tokens: number | null;
}

type TockyConf = {
    LLM_MODELS: LLMModel[];
    OCR_ENGINES: any[];
    APPLICATION_ROOT: string;
}

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

