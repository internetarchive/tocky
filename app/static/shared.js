// @ts-check
const TockyShared = {};

TockyShared.CONF = window.TOCKY_CONF;

TockyShared.config = Vue.reactive({
    darkMode: localStorage.getItem('tocky--dark-mode') === 'true',
    authenticated: false,
});

TockyShared.DETECTORS = {
    ocr_detector: {
        name: "OCR Detector",
        value: "ocr_detector",
        description: "Uses text extracted from the book pages, combined with manual heuristics to detect the TOC pages.",
        options: {
            allow_reocr: {
                value: true,
            },
            ocr_engine: {
                value: "azure",
                options: TockyShared.CONF.OCR_ENGINES,
            }
        }
    },
    ai_vision_detector: {
        name: "AI Vision Detector",
        value: "ai_vision_detector",
        description: "Uses AI with vision capabilities to visually detect the TOC pages.",
        options: {
            model: {
                value: 'gpt-4o-mini',
                options: [
                    "gpt-4o-mini"
                ]
            },
            max_tokens: {
                value: 200,
            }
        }
    },
    manual_detector: {
        name: "Manual Detector",
        value: "manual_detector",
        description: '"Why don\'t you just tell me where the TOC is?"',
        options: {
            leaf_numbers: {
                value: [],
                
                get value_str() {
                    return this.value.join(",");
                },
                set value_str(value) {
                    this.value = value.split(",").map(x => x.trim()).filter(x => x).map(x => parseFloat(x));
                },
            }
        }
    }
};

TockyShared.EXTRACTORS = {
    ai_extractor: {
        name: "AI Extractor",
        value: "ai_extractor",
        description: "Sends the OCR from the TOC pages to AI to extract in a structured format.",
        options: {
            model: {
                value: 'gpt-4o-mini',
                options: [
                    "gpt-4o-mini",
                    "gpt-3.5-turbo",
                ]
            },
            max_sent_tokens: {
                value: 1000,
            },
            redo_ocr: {
                value: true,
            },
            ocr_engine: {
                value: "azure",
                options: TockyShared.CONF.OCR_ENGINES,
            },
            extraction_format: {
                value: "json",
                options: [
                    "json",
                    "markdown",
                ]
            },
        }
    },
    ai_vision_extractor: {
        name: "AI Vision Extractor",
        value: "ai_vision_extractor",
        description: "Sends the raw images of the TOC pages to AI to 'read' and extract in a structured format.",
        options: {
            model: {
                value: 'gpt-4o-mini',
                options: [
                    "gpt-4o-mini",
                    "gpt-3.5-turbo",
                ]
            },
            extraction_format: {
                value: "json",
                options: [
                    "json",
                    "markdown",
                ]
            },
        }
    },
};

TockyShared.DEFAULT_DETECTOR = TockyShared.DETECTORS.ocr_detector;
TockyShared.DEFAULT_EXTRACTOR = TockyShared.EXTRACTORS.ai_extractor;

TockyShared.getActiveUserName = function () {
    /* Read the session cookie to determine current user */
    return document.cookie.match(/session=([^%]+)/)?.[1];
}

TockyShared.apiSubmit = async function (base_url, data) {
    if (!TockyShared.getApiKey(false)) {
        alert("Please provide a Tocky API key");
        return;
    }

    const detector = TockyShared.DETECTORS[data.detector?.type || TockyShared.DEFAULT_DETECTOR.value];
    if (!detector) {
        throw new Error(`Invalid detector type: ${data.detector.type}`);
    }
    const extractor = TockyShared.EXTRACTORS[data.extractor?.type || TockyShared.DEFAULT_EXTRACTOR.value];
    if (!extractor) {
        throw new Error(`Invalid extractor type: ${data.extractor.type}`);
    }

    const res = await fetch(`${base_url}/submit?background=true`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            'X-API-Key': TockyShared.getApiKey(),
        },
        body: JSON.stringify({
            ...data,
            detector: {
                type: detector.value,
                options: Object.fromEntries(
                    Object.entries(detector.options)
                        .map(([key, value]) => [key, (data.detector?.options && key in data.detector.options) ? data.detector.options[key] : value.value])
                )
            },
            extractor: {
                type: extractor.value,
                options: Object.fromEntries(
                    Object.entries(extractor.options)
                        .map(([key, value]) => [key, (data.extractor?.options && key in data.extractor.options) ? data.extractor.options[key] : value.value])
                )
            },
        })
    });
    if (!res.ok) {
        throw new Error("Failed to extract TOC");
    }
    return await res.json();
};


TockyShared.jobStateToPrimeVueSeverity = function (state) {
    if (state === 'Done' || state === 'Completed') {
        return 'success';
    }
    if (state === 'Errored') {
        return 'danger';
    }
    if (state === 'To Review') {
        return 'help';
    }
    if (state === 'Skipped') {
        return 'secondary';
    }
    return 'info';
};

TockyShared.StateTag = {
    template: `
        <p-tag
            :value="state"
            :class="{'p-tag-help': jobStateToPrimeVueSeverity(state) === 'help'}"
            :severity="jobStateToPrimeVueSeverity(state)"
        ></p-tag>
    `,
    props: {
        state: String,
    },
    methods: {
        jobStateToPrimeVueSeverity: TockyShared.jobStateToPrimeVueSeverity,
    },
    mounted() {
        registerStyleTag('tocky-state-tag', `
            .p-tag-help {
                background: var(--p-purple-100);
                color: var(--p-purple-700);
            }

            .tocky-dark-mode .p-tag-help {
                background: color-mix(in srgb,var(--p-purple-500),transparent 84%);
                color: var(--p-purple-300);
            }
        `);
    }
};

TockyShared.CopyButton = {
    template: `
        <p-button
            class="tocky-copy-button"
            text
            :icon="\`pi \${copied ? 'pi-check' : 'pi-copy'}\`"
            @click="copyToClipboard(text)"
            v-tooltip.top="\`Copy to clipboard\`"
            :label="copied ? 'Copied!' : ''"
        ></p-button>
    `,
    props: {
        text: String,
    },
    data() {
        return {
            copied: false,
        };
    },
    methods: {
        copyToClipboard(text) {
            navigator.clipboard.writeText(text);
            this.copied = true;
            setTimeout(() => this.copied = false, 2000);
        },
    },
};

class Rect {
    /**
     * @param {number} x1 - The x-coordinate of the left edge.
     * @param {number} y1 - The y-coordinate of the top edge.
     * @param {number} x2 - The x-coordinate of the right edge.
     * @param {number} y2 - The y-coordinate of the bottom edge.
     */
    constructor(x1, y1, x2, y2) {
        this.x1 = x1;
        this.y1 = y1;
        this.x2 = x2;
        this.y2 = y2;
    }

    get width() {
        return this.x2 - this.x1;
    }

    get height() {
        return this.y2 - this.y1;
    }

    static fromLBRT([left, bottom, right, top]) {
        return new Rect(left, top, right, bottom);
    }

    toString() {
        return `${this.x1},${this.y1},${this.x2},${this.y2}`;
    }

    toCSS(unit = 'px') {
        if (unit === '%') {
            return `left: ${this.x1 * 100}%; top: ${this.y1 * 100}%; width: ${this.width * 100}%; height: ${this.height * 100}%;`;
        } else {
            return `left: ${this.x1}${unit}; top: ${this.y1}${unit}; width: ${this.width}${unit}; height: ${this.height}${unit};`;
        }
    }

    normalize(width, height) {
        // Normalize coordinates to a 0-1 range based on the given width and height
        return new Rect(
            this.x1 / width,
            this.y1 / height,
            this.x2 / width,
            this.y2 / height
        );
    }

    /**
     * @param {Rect[]} rects
     */
    static getBoundingBox(rects) {
        if (rects.length === 0) return null;

        const x1 = Math.min(...rects.map(r => r.x1));
        const y1 = Math.min(...rects.map(r => r.y1));
        const x2 = Math.max(...rects.map(r => r.x2));
        const y2 = Math.max(...rects.map(r => r.y2));

        return new Rect(x1, y1, x2, y2);
    }
}

/**
 * @param {TocEntry[]} tocJson
 * @returns {TaggedWord[]}
 */
function tocJsonToTaggedWords(tocJson) {
    /** @type {TaggedWord[]} */
    const taggedWords = [];
    for (let [index, entry] of Object.entries(tocJson)) {
        for (const field of ["label", "title", "authors", "subtitle", "description", "pagenum"]) {
            if (!(field in entry)) continue;

            if (field === "authors" && entry.authors) {
                for (const [authorIndex, author] of entry.authors.entries()) {
                    for (const word of author.matchAll(/\S+/g) || []) {
                        taggedWords.push({
                            word: word[0],
                            tocEntry: entry,
                            tocPath: `${index}.${field}.${authorIndex}`,
                            tocWordOffset: word.index,
                        });
                    }
                }
            } else {
                for (const word of entry[field].matchAll(/\S+/g) || []) {
                    taggedWords.push({
                        word: word[0],
                        tocEntry: entry,
                        tocPath: `${index}.${field}`,
                        tocWordOffset: word.index,
                    });
                }
            }
        }
    }
    return taggedWords;
}

class OcrTocStitch {
    /**
     * @param {OcrPage[]} ocr
     * @param {TocEntry[]} tocJson
     */
    constructor(ocr, tocJson) {
        const stitchedWords = /** @type {StitchedWord[]} */(tocJsonToTaggedWords(tocJson));

        for (const word of stitchedWords) {
            word.ocrWords = ocr.flatMap(page => page.findAllWords(word.word));
        }

        this.words = stitchedWords;
        const matchedOcrWords = new Set(stitchedWords.flatMap(word => word.ocrWords.map(w => w.id)));

        this.deletedWords = new Set(
            ocr.flatMap(page => page.words)
                .filter(ocrWord => !matchedOcrWords.has(ocrWord.id))
                .map(ocrWord => ocrWord.id)
        );
        this.addedWords = new Set(
            stitchedWords
                .filter(word => word.ocrWords.length === 0)
                .flatMap(word => word.ocrWords.map(w => w.id))
        );
        /** @type {Map<OcrWord, Set<string>>} */
        this.ocrWordToExtraClasses = new Map();
        /** @type {Map<string, OcrWord[]>} */
        this.classToOcrWords = new Map();
    }

    /**
     * @param {OcrWord[]} ocrWords
     * @param {string} cls - The class to set for the OCR word.
     */
    setExtraClass(ocrWords, cls) {
        this.clearExtraClass(cls);
        // then add the new class
        for (const ocrWord of ocrWords) {
            const extraClasses = this.ocrWordToExtraClasses.get(ocrWord) || new Set();
            extraClasses.add(cls);
            this.ocrWordToExtraClasses.set(ocrWord, extraClasses);
            const existingClasses = this.classToOcrWords.get(cls) || [];
            existingClasses.push(ocrWord);
            this.classToOcrWords.set(cls, existingClasses);
        }
    }

    /**
     * @param {string} cls - The class to clear from the OCR words.
     **/
    clearExtraClass(cls) {
        const ocrWords = this.classToOcrWords.get(cls);
        if (!ocrWords) return;

        for (const ocrWord of ocrWords) {
            const extraClasses = this.ocrWordToExtraClasses.get(ocrWord);
            if (extraClasses) {
                extraClasses.delete(cls);
                if (extraClasses.size === 0) {
                    this.ocrWordToExtraClasses.delete(ocrWord);
                } else {
                    this.ocrWordToExtraClasses.set(ocrWord, extraClasses);
                }
            }
        }
        this.classToOcrWords.delete(cls);
    }


    /**
     * @param {TocEntry[]} tocEntries
     */
    getOcrWordsForTocEntries(tocEntries) {
        return tocEntries.flatMap(tocEntry => this.getOcrWordsForTocEntry(tocEntry))
    }

    /**
     * @param {TocEntry} tocEntry
     */
    getOcrWordsForTocEntry(tocEntry) {
        // First check words which only one occurrence in the OCR
        let highConfidenceWords = this.words
            .filter(word => tocEntry == word.tocEntry && word.ocrWords.length <= 1)
            .flatMap(word => word.ocrWords);
        
        if (highConfidenceWords.length === 0) {
            // No luck, try a more relaxed search
            highConfidenceWords = this.words
            .filter(word => tocEntry == word.tocEntry && word.ocrWords.length <= 2)
            .flatMap(word => word.ocrWords);
        }

        const includedWordTexts = new Set(highConfidenceWords.map(word => normalizeOcrWordText(word.text)));

        const allWords = this.words
            .filter(word => tocEntry == word.tocEntry)
            .flatMap(word => word.ocrWords)

        let minWordIndex = highConfidenceWords[0]?.wordIndex;
        let maxWordIndex = highConfidenceWords[highConfidenceWords.length - 1]?.wordIndex;

        // Expand backwards to include mid-confidence words
        for (let i = minWordIndex; i >= Math.max(0, minWordIndex - 5); i--) {
            const word = allWords.find(ocrWord => ocrWord.wordIndex === i);
            if (word && !includedWordTexts.has(normalizeOcrWordText(word.text))) {
                minWordIndex = i;
                highConfidenceWords.unshift(word);
            }
        }

        // Expand forwards to include mid-confidence words
        for (let i = maxWordIndex; i <= Math.min(allWords.length - 1, maxWordIndex + 5); i++) {
            const word = allWords.find(ocrWord => ocrWord.wordIndex === i);
            if (word && !includedWordTexts.has(normalizeOcrWordText(word.text))) {
                maxWordIndex = i;
                highConfidenceWords.push(word);
            }
        }

        const midConfidenceWords = allWords
            .filter(ocrWord => ocrWord.wordIndex >= minWordIndex && ocrWord.wordIndex <= maxWordIndex)
            .filter(ocrWord => !highConfidenceWords.includes(ocrWord) && !includedWordTexts.has(normalizeOcrWordText(ocrWord.text)));

        return _.sortBy([
            ...highConfidenceWords,
            ...midConfidenceWords,
        ], 'wordIndex');
    }

    /**
     * @param {OcrWord[]} ocrWords
     * @returns {{ page: OcrPage, words: OcrWord[] } | undefined}
     */
    findMostMatchingOcrPage(ocrWords) {
        return _.chain(ocrWords)
            .groupBy(word => word.page)
            .map((words, page) => ({
                page,
                count: words.length,
                words: words,
            }))
            .sortBy('count')
            .reverse()
            .find()
            .value();
    }

    /**
     * @param {OcrWord} ocrWord
     */
    getOcrWordCSSClass(ocrWord) {
        if (this.addedWords.has(ocrWord.id)) {
            return 'added';
        }
        if (this.deletedWords.has(ocrWord.id)) {
            return 'deleted';
        }
        return 'matched';
    }

    /**
     * @param {OcrWord} ocrWord
     */
    getOcrWordExtraClasses(ocrWord) {
        const extraClasses = this.ocrWordToExtraClasses.get(ocrWord);
        if (!extraClasses || extraClasses.size === 0) {
            return '';
        }
        return Array.from(extraClasses);
    }
}

class OcrWord {
    /**
     * @param {OcrPage} page - The OCR page containing the word.
     * @param {number} wordIndex - The index of the word in the page's words array.
     * @param {Element} wordElement - The XML element representing a word in the OCR XML.
     * @example `<WORD coords="1388,193,1489,158" x-confidence="98.5">PAGE</WORD>`
     */
    constructor(page, wordIndex, wordElement) {
        this.element = wordElement;
        /** @type {string} */
        this.text = /** @type {string} */(wordElement.textContent);
        /** @type {Rect} */
        this.coords = Rect.fromLBRT(wordElement.getAttribute('coords').split(',').map(parseFloat));
        this.id = `PageLeaf#${page.leafNumber}/Word#${wordIndex}`;
        this.wordIndex = wordIndex;
        this.page = page;
    }
}

class OcrPage {
    /**
     * @param {string} ocrXml - The OCR XML string to parse.
     */
    constructor(ocrXml) {
        // parse the OBJECT as xml
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(ocrXml, "application/xml");
        this.xmlObject = xmlDoc.querySelector('OBJECT');
        // eg `<OBJECT data="file://localhost/var/tmp/autoclean/derive/goodytwoshoes00newyiala/goodytwoshoes00newyiala.djvu" type="image/x.djvu" usemap="goodytwoshoes00newyiala_0001.djvu" width="2454" height="3192">`
        // Leaf number is in usemap, eg `usemap="goodytwoshoes00newyiala_0001.djvu"`
        this.leafNumber = parseInt(this.xmlObject.getAttribute('usemap').match(/_(\d+)\./)[1], 10);
        this.width = parseFloat(this.xmlObject.getAttribute('width'));
        this.height = parseFloat(this.xmlObject.getAttribute('height'));
        this.words = Array.from(this.xmlObject.querySelectorAll('WORD'))
            .map((wordElement, i) => new OcrWord(this, i, wordElement));
    }

    /**
     * @param {string} word
     */
    findAllWords(word) {
        return this.words.filter(ocrWord => normalizeOcrWordText(ocrWord.text) === normalizeOcrWordText(word))
    }
}

/** @param {string} text */
function normalizeOcrWordText(text) {
    return text.toLowerCase().trim().replace(/[.:;,]+$/, '');
}

// v-models
TockyShared.PageSelector = {
    template: `
        <div class="tocky-page-selector" :class="[layout, {'readonly': readonly}]">
            <div
                class="tocky-page-selector__page"
                v-for="(page, index) in getLeafNumbersWithContext()"
                :key="page.number"
            >
                <img
                    loading="lazy"
                    :src="getImageUrl(page.number, index)"
                    :class="{ 'selected': page.selected }"
                    @click="toggleLeafNumber(page.number)"
                >
                <div class="tocky-page-selector__ocr" v-if="ocr && ocr[index]">
                    <span
                        v-for="(word, widx) in ocr[index].words"
                        :key="widx"
                        :class="[stitch?.getOcrWordCSSClass(word), ...(stitch?.getOcrWordExtraClasses(word) || [])]"
                        :style="word.coords.normalize(ocr[index].width, ocr[index].height).toCSS('%')"
                        :title="word.text"
                    ></span>
                </div>
                <p-button
                    as="a"
                    :href="\`https://archive.org/details/\${iaId}/page/leaf\${page.number}\`"
                    target="_blank"
                    icon="pi pi-external-link"
                    size="small"
                    severity="secondary"
                ></p-button>
                <p-tag :severity="page.selected ? 'success': 'secondary'">
                    {{ page.number }}
                </p-tag>
            </div>
        </div>
    `,
    props: {
        getImageUrl: Function,
        modelValue: Array,
        iaId: String,
        /** @type {'grid' | 'vertical'} */
        layout: {
            type: String,
            default: 'grid',
        },
        context: {
            type: Boolean,
            default: true,
        },
        readonly: {
            type: Boolean,
            default: false,
        },
        /**
         * @type {OcrPage[]}
         **/
        ocr: {
            type: Array,
            default: null,
        },
        /**
         * @type {OcrTocStitch[]}
         */
        stitch: {
            type: Object,
            default: null,
        }
    },
    emits: ['update:modelValue'],
    methods: {
        toggleLeafNumber(leafNumber) {
            if (this.readonly) return;

            const index = this.modelValue.indexOf(leafNumber);
            if (index === -1) {
                this.modelValue.push(leafNumber);
                this.modelValue.sort((a, b) => a - b);
            } else {
                this.modelValue.splice(index, 1);
            }
        },
        getLeafNumbersWithContext() {
            return Array.from(this._genLeafNumbersWithContext());
        },
        *_genLeafNumbersWithContext() {
            if (!this.context) {
                for (const number of this.modelValue) {
                    yield {
                        number,
                        selected: true,
                    };
                }
                return;
            }
            const max = Math.max(...this.modelValue);
            for (let i = 0; i <= Math.max(30, max + 2); i++) {
                yield {
                    number: i,
                    selected: this.modelValue.includes(i),
                };
            }
        },
    },
    watch: {
        async layout(newLayout) {
            if (newLayout === 'grid') {
                await this.$nextTick();
                /** @type {HTMLElement} */
                const selectedImg = this.$el.querySelector('.selected');
                if (selectedImg) {
                    selectedImg.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
                }
            }
        }
    },
    mounted() {
        registerStyleTag('tocky-page-selector', `
            .tocky-page-selector {
                min-height: 300px !important;
                width: 100%;
            }

            .tocky-page-selector .p-button {
                position: absolute;
                right: 0;
                top: 0;
                margin: 5px 10px;
                opacity: 0.25;
                transition: opacity 0.2s;
            }
            .tocky-page-selector .p-button:hover {
                opacity: 0.75;
            }

            .tocky-page-selector img {
                border-radius: 5px;
                transition: opacity 0.2s;

                object-fit: cover;
                object-position: top left;
                width: 100%;
                height: 100%;
            }

            .tocky-page-selector:has(.selected) img:not(.selected) {
                opacity: 0.8;
            }
            
            .tocky-page-selector img.selected {
                /** Keep 4px in sync with text layer offset */
                border: 4px solid green;
            }

            .tocky-page-selector.vertical {
                display: flex;
                gap: 8px;
                flex-direction: column;
                align-items: center;
            }

            .tocky-page-selector.grid .tocky-page-selector__page {
                display: inline-block;
                width: 160px;
                height: 160px;
            }

            .tocky-page-selector:not(.readonly) .tocky-page-selector__page {
                cursor: pointer;
            }

            .tocky-page-selector__page {
                position: relative;
            }
            .tocky-page-selector__page .p-tag {
                position: absolute;
                bottom: 12px;
                left: 50%;
                transform: translateX(-50%);
            }
            .tocky-page-selector__ocr {
                position: absolute;
                /** Match selected border */
                inset: 4px;
                mix-blend-mode: multiply;
            }
            .tocky-page-selector__ocr span {
                position: absolute;
                color: transparent;
                border-radius: 3px;
                font-size: 9px;
                line-height: 1em;
                transition: background-color 0.2s;
                --ocr-span-color: var(--p-blue-500);
                background-color: color-mix(in srgb, var(--ocr-span-color) 10%, transparent);
            }

            .tocky-page-selector__ocr span.added {
                --ocr-span-color: var(--p-green-500);
            }
            .tocky-page-selector__ocr span.deleted {
                --ocr-span-color: var(--p-red-500);
                background-color: color-mix(in srgb, var(--ocr-span-color) 50%, transparent);
            }
            .tocky-page-selector__ocr span.matched {
                --ocr-span-color: var(--p-blue-500);
            }
            .tocky-page-selector__ocr span.highlighted {
                background-color: color-mix(in srgb, var(--ocr-span-color) 25%, transparent);
            }
            .tocky-page-selector__ocr span.hovered {
                background-color: color-mix(in srgb, var(--ocr-span-color) 40%, transparent);
            }
            .tocky-page-selector__ocr span.selected {
                outline: 2px solid var(--ocr-span-color);
            }
        `);
    }
};

TockyShared.MiddleTruncate = {
    mounted(el, binding) {
        const text = el.innerText;
        const max = parseInt(binding.value) || 100;
        if (text.length <= max) {
            return;
        }
        el.title = text;
        el.innerText = text.slice(0, Math.floor(max / 2)) + '…' + text.slice(-Math.floor(max / 2));
    }
};

TockyShared.IaLink = {
    template: `
        <p-button-group>
            <p-button small text as="a" :href="\`https://openlibrary.org/ia/\${ocaid}\`" target="_blank" title="Find on OpenLibrary">
                <img src="https://openlibrary.org/favicon.ico" alt="" style="width: 16px; height: 16px;">
            </p-button>
            <p-button small text as="a" :href="\`https://archive.org/details/\${ocaid}\`" target="_blank" title="View on Archive.org">
                <img src="https://archive.org/favicon.ico" alt="" style="width: 16px; height: 16px;">
                <span v-tocky-middle-truncate="40">{{ocaid}}</span>
            </p-button>
            <tocky-copy-button :text="ocaid"></tocky-copy-button>
        </p-button-group>
    `,
    props: {
        ocaid: String,
    },
};

TockyShared.Header = {
    template: `
        <p-menubar class="app-toolbar" :model="nav_options">
            <template #start>
                <h1>Tocky</h1>
            </template>

            <template #end>
                <p-button
                    size="small"
                    :icon="config.darkMode ? 'pi pi-moon' : 'pi pi-sun'"
                    text
                    @click="config.darkMode = !config.darkMode"
                    title="Toggle Dark Mode"
                ></p-button>
                <p-button size="small" :outlined="config.authenticated" @click="authenticate">
                    <i class="pi pi-key"></i>
                    {{ config.authenticated ? 'Edit Key' : 'Set Key' }}
                </p-button>
            </template>
        </p-menubar>
    `,
    data() {
        return {
            nav_options: [
                { label: 'Queue', url: `${TockyShared.CONF.APPLICATION_ROOT}/list`, icon: 'pi pi-list' },
                { label: 'Batches', url: `${TockyShared.CONF.APPLICATION_ROOT}/batches`, icon: 'pi pi-objects-column' },
                { label: 'Submit', url: `${TockyShared.CONF.APPLICATION_ROOT}/submit`, icon: 'pi pi-plus' },
            ],
            config: TockyShared.config,
        };
    },
    watch: {
        'config.darkMode': {
            handler(value) {
                localStorage.setItem('tocky--dark-mode', value);
                document.documentElement.classList.toggle('tocky-dark-mode', value);
            },
            immediate: true,
        },
    },
    methods: {
        authenticate() {
            if (this.config.authenticated) {
                const newKey = prompt("Tocky API key", TockyShared.getApiKey(false));
                if (newKey !== null) {
                    TockyShared.setCookie('TOCKY_API_KEY', newKey);
                }
            } else {
                TockyShared.getApiKey(true);
            }
        },
    },
};

TockyShared.getImageUrl = function(ia_id, leafNumber) {
    return `ia_img?${
        new URLSearchParams({
            id: ia_id,
            leaf: leafNumber,
        }).toString()
    }`;
},

TockyShared.setCookie = function (name, value, days = 365) {
    const d = new Date();
    d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
    const expires = "expires=" + d.toUTCString();
    document.cookie = name + "=" + value + ";" + expires + ";path=/";
};

TockyShared.readCookie = function (key) {
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
        const [name, value] = cookie.split('=');
        if (name.trim() === key) {
            return value;
        }
    }
    return null;
};

TockyShared.getApiKey = function (ask = true) {
    // First check cookie
    const cookie = TockyShared.readCookie('TOCKY_API_KEY');
    if (cookie) {
        TockyShared.config.authenticated = true;
        return cookie;
    }

    // Then check url parameter
    const urlParams = new URLSearchParams(window.location.search);
    const urlKey = urlParams.get('api_key');
    if (urlKey) {
        TockyShared.config.authenticated = true;
        TockyShared.setCookie('TOCKY_API_KEY', urlKey);
        return urlKey;
    }

    // Otherwise ask
    const providedKey = ask && prompt("Tocky API key");
    if (providedKey) {
        TockyShared.config.authenticated = true;
        TockyShared.setCookie('TOCKY_API_KEY', providedKey);
        return providedKey;
    }

    TockyShared.config.authenticated = false;
    return null;
};

// call to update config value
TockyShared.getApiKey(false);

TockyShared.registerComponents = function (app) {
    function upperCamelCaseToKebabCase(str) {
        return str.replace(/([a-z0-9]|(?=[A-Z]))([A-Z])/g, '$1-$2').toLowerCase().slice(1);
    }

    // Configure PrimeVue
    app.use(PrimeVue.Config, {
        theme: {
            preset: PrimeVue.Themes.Aura,
            options: {
                prefix: 'p',
                darkModeSelector: '.tocky-dark-mode',
            }
        }
    });

    // Register all PrimeVue components
    for (const component in PrimeVue) {
        const kebabCase = upperCamelCaseToKebabCase(component);
        app.component(`p-${kebabCase}`, PrimeVue[component]);
    }

    // Register all PrimeVue directives
    app.directive('tooltip', PrimeVue.Tooltip);

    // Register shared components
    app.component('tocky-header', TockyShared.Header);
    app.component('tocky-copy-button', TockyShared.CopyButton);
    app.component('tocky-state-tag', TockyShared.StateTag);
    app.component('tocky-ia-link', TockyShared.IaLink);
    app.component('tocky-page-selector', TockyShared.PageSelector);

    // Register global directives
    app.directive('tocky-middle-truncate', TockyShared.MiddleTruncate);
};

function registerStyleTag(component, css) {
    const styleId = `style-${component}`;
    if (document.getElementById(styleId)) {
        return;
    }

    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = css;
    document.head.appendChild(style);
}

window.TockyShared = TockyShared;
