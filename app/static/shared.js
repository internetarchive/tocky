const TockyShared = {};

TockyShared.Header = {
    template: `
        <p-menubar class="app-toolbar" :model="nav_options">
            <template #start>
                <h1>Tocky</h1>
            </template>

            <template #end>
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
                { label: 'List', url: '/list', icon: 'pi pi-list' },
                { label: 'Submit', url: '/submit', icon: 'pi pi-plus' },
            ],
        };
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
    const cookie = TockyShared.readCookie('TOCKY_API_KEY');
    if (!cookie && ask) {
        const providedKey = prompt("Tocky API key");
        if (providedKey) {
            TockyShared.setCookie('TOCKY_API_KEY', providedKey);
            return providedKey;
        }
    }
    return cookie;
};

TockyShared.registerComponents = function (app) {
    function upperCamelCaseToKebabCase(str) {
        return str.replace(/([a-z0-9]|(?=[A-Z]))([A-Z])/g, '$1-$2').toLowerCase().slice(1);
    }

    // Configure PrimeVue
    window.app.use(PrimeVue.Config, {
        theme: {
            preset: PrimeVue.Themes.Aura,
            options: {
                prefix: 'p',
                darkModeSelector: '.never',
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
};

window.TockyShared = TockyShared;
