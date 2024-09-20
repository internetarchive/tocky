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

    const res = await fetch(`${base_url}/submit`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            'X-API-Key': TockyShared.getApiKey(),
        },
        body: JSON.stringify({
            input_book: data.input_book,
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
            }
        })
    });
    if (!res.ok) {
        throw new Error("Failed to extract TOC");
    }
    return await res.json();
};
TockyShared.StateTag = {
    template: `
        <p-tag :value="state" :severity="mapStateToSeverity(state)"></p-tag>
    `,
    props: {
        state: String,
    },
    methods: {
        mapStateToSeverity(state) {
            if (state === 'Done') {
                return 'success';
            }
            if (state === 'Errored') {
                return 'danger';
            }
            return 'info';
        }
    },
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
                padding: 0 5px;
            }
            .tocky-page-selector__page .p-tag {
                position: absolute;
                bottom: 12px;
                left: 50%;
                transform: translateX(-50%);
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
                { label: 'List', url: `${TockyShared.CONF.APPLICATION_ROOT}/list`, icon: 'pi pi-list' },
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
