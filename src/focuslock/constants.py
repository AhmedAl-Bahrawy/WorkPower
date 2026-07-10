"""Application-wide constants and defaults."""

APP_NAME = "FocusLock"
VERSION = "2.0.0"

DEFAULT_APPS = [
    "steam.exe",
    "steamwebhelper.exe",
    "discord.exe",
    "EpicGamesLauncher.exe",
    "Battle.net.exe",
    "LeagueClient.exe",
    "TwitchUI.exe",
    "Spotify.exe",
]

DEFAULT_SITES = [
    "youtube.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "twitch.tv",
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "netflix.com",
    "discord.com",
]

PRESETS = {
    "Classic (25/5)": (25, 5),
    "Long Focus (50/10)": (50, 10),
    "Short Burst (15/3)": (15, 3),
    "Deep Work (90/20)": (90, 20),
}

SUGGESTED_APPS = {
    "🎮  Games": [
        ("Steam", "steam.exe"),
        ("Steam Helper", "steamwebhelper.exe"),
        ("Epic Games", "EpicGamesLauncher.exe"),
        ("Battle.net", "Battle.net.exe"),
        ("League Client", "LeagueClient.exe"),
        ("Valorant", "VALORANT-Win64-Shipping.exe"),
        ("Minecraft", "Minecraft.exe"),
        ("Roblox", "RobloxPlayerBeta.exe"),
        ("Xbox App", "XboxApp.exe"),
        ("GOG Galaxy", "GalaxyClient.exe"),
    ],
    "💬  Social & Chat": [
        ("Discord", "discord.exe"),
        ("Slack", "slack.exe"),
        ("Microsoft Teams", "ms-teams.exe"),
        ("Telegram", "Telegram.exe"),
        ("WhatsApp", "WhatsApp.exe"),
        ("Signal", "Signal.exe"),
        ("Skype", "Skype.exe"),
    ],
    "🎵  Media & Music": [
        ("Spotify", "Spotify.exe"),
        ("Twitch", "TwitchUI.exe"),
        ("VLC", "vlc.exe"),
        ("iTunes", "iTunes.exe"),
        ("Deezer", "Deezer.exe"),
    ],
    "🌐  Browsers": [
        ("Chrome", "chrome.exe"),
        ("Firefox", "firefox.exe"),
        ("Edge", "msedge.exe"),
        ("Opera", "opera.exe"),
        ("Brave", "brave.exe"),
    ],
    "📱  Other": [
        ("Zoom", "Zoom.exe"),
        ("OBS Studio", "obs64.exe"),
        ("Photoshop", "Photoshop.exe"),
        ("Blender", "blender.exe"),
    ],
}

SUGGESTED_SITES = {
    "📱  Social Media": [
        "twitter.com", "x.com", "instagram.com", "facebook.com",
        "tiktok.com", "reddit.com", "snapchat.com", "linkedin.com",
        "pinterest.com", "tumblr.com",
    ],
    "📺  Video & Streaming": [
        "youtube.com", "twitch.tv", "netflix.com", "hulu.com",
        "disneyplus.com", "primevideo.com", "crunchyroll.com",
        "vimeo.com", "dailymotion.com",
    ],
    "🗞️  News & Forums": [
        "news.ycombinator.com", "medium.com", "9gag.com",
        "buzzfeed.com", "cnn.com", "bbc.com", "theverge.com",
    ],
    "🛒  Shopping": [
        "amazon.com", "ebay.com", "aliexpress.com", "etsy.com",
        "walmart.com",
    ],
    "💬  Messaging": [
        "discord.com", "slack.com", "messenger.com", "whatsapp.com",
    ],
}

THEMES = {
    "dark": {
        "bg": "#0d0d14",
        "surface": "#13131e",
        "sidebar": "#0f0f18",
        "card": "#1a1a2e",
        "card_hover": "#20203a",
        "accent": "#7c6cff",
        "accent_hover": "#9488ff",
        "accent2": "#ff5c7a",
        "success": "#3dd68c",
        "warn": "#f5b942",
        "text": "#ececf4",
        "subtext": "#8b8ba8",
        "muted": "#5c5c78",
        "border": "#252540",
        "input": "#181828",
        "danger": "#ff5c7a",
        "timer_work": "#7c6cff",
        "timer_break": "#3dd68c",
        "timer_bg": "#1a1a2e",
    },
    "light": {
        "bg": "#f0f0f8",
        "surface": "#ffffff",
        "sidebar": "#eaeaf4",
        "card": "#ffffff",
        "card_hover": "#f4f4fc",
        "accent": "#6c63ff",
        "accent_hover": "#5a52e0",
        "accent2": "#e0456a",
        "success": "#2cb67d",
        "warn": "#d4920a",
        "text": "#1a1a2e",
        "subtext": "#5a5a78",
        "muted": "#9898b0",
        "border": "#d8d8ec",
        "input": "#f8f8ff",
        "danger": "#e0456a",
        "timer_work": "#6c63ff",
        "timer_break": "#2cb67d",
        "timer_bg": "#eaeaf4",
    },
}
