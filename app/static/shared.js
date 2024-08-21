const TockyShared = {};

TockyShared.Header = {
    template: `
        <p-menu-bar class="app-toolbar" :model="nav_options">
            <template #start>
                <h1>Tocky</h1>
            </template>

            <template #end>
                <p-button size="small" :outlined="authenticated" @click="authenticate">
                    <i class="pi pi-key"></i>
                    {{ authenticated ? 'Edit Key' : 'Set Key' }}
                </p-button>
            </template>
        </p-menu-bar>
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

window.TockyShared = TockyShared;
