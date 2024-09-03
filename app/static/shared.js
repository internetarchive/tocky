const TockyShared = {};

TockyShared.config = {
    darkMode: localStorage.getItem('tocky--dark-mode') === 'true',
};

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
                options: [
                    "tesseract",
                    "easyocr",
                    "azure",
                ]
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
                options: [
                    "tesseract",
                    "easyocr",
                    "azure",
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
    if (!TockyShared.getApiKey()) {
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

// v-models
TockyShared.PageSelector = {
    template: `
        <div class="tocky-page-selector">
            <div
                class="tocky-page-selector__page"
                v-for="page in getLeafNumbersWithContext()"
                :key="page.number"
            >
                <img
                    loading="lazy"
                    :src="getImageUrl(page.number)"
                    :class="{ 'selected': page.selected }"
                    @click="toggleLeafNumber(page.number)"
                >
                <p-tag :severity="page.selected ? 'success': 'secondary'">
                    {{ page.number }}
                </p-tag>
            </div>
        </div>
    `,
    props: {
        getImageUrl: Function,
        modelValue: Array,
    },
    emits: ['update:modelValue'],
    methods: {
        toggleLeafNumber(leafNumber) {
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


            .tocky-page-selector__page {
                position: relative;
                padding: 0 5px;

                display: inline-block;
                width: 160px;
                height: 160px;
                cursor: pointer;
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

TockyShared.IaLink = {
    template: `
        <p-button-group>
            <p-button small link as="a" :href="\`https://openlibrary.org/ia/\${ocaid}\`" target="_blank" title="Find on OpenLibrary">
                <img src="https://openlibrary.org/favicon.ico" alt="" style="width: 16px; height: 16px;">
            </p-button>
            <p-button small link as="a" :href="\`https://archive.org/details/\${ocaid}\`" target="_blank" title="View on Archive.org">
                <img src="https://archive.org/favicon.ico" alt="" style="width: 16px; height: 16px;">
                {{ocaid}}
            </p-button>
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
                <p-button size="small" :outlined="authenticated" @click="authenticate">
                    <i class="pi pi-key"></i>
                    {{ authenticated ? 'Edit Key' : 'Set Key' }}
                </p-button>
            </template>
        </p-menubar>
    `,
    data() {
        return {
            authenticated: !!TockyShared.getApiKey(false),
            nav_options: [
                // TODO: Should not hard-code the /tocky prefix
                { label: 'List', url: '/tocky/list', icon: 'pi pi-list' },
                { label: 'Submit', url: '/tocky/submit', icon: 'pi pi-plus' },
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
            if (this.authenticated) {
                const newKey = prompt("Tocky API key", TockyShared.getApiKey(false));
                if (newKey !== null) {
                    TockyShared.setCookie('TOCKY_API_KEY', newKey);
                }
            } else {
                TockyShared.getApiKey(true);
            }
            this.authenticated = !!TockyShared.getApiKey(false);
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
    if (cookie) return cookie;

    // Then check url parameter
    const urlParams = new URLSearchParams(window.location.search);
    const urlKey = urlParams.get('api_key');
    if (urlKey) {
        TockyShared.setCookie('TOCKY_API_KEY', urlKey);
        return urlKey;
    }

    // Otherwise ask
    const providedKey = ask && prompt("Tocky API key");
    if (providedKey) {
        TockyShared.setCookie('TOCKY_API_KEY', providedKey);
        return providedKey;
    }

    return null;
};

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
    window.app.component('tocky-header', TockyShared.Header);
    window.app.component('tocky-state-tag', TockyShared.StateTag);
    window.app.component('tocky-ia-link', TockyShared.IaLink);
    window.app.component('tocky-page-selector', TockyShared.PageSelector);
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
