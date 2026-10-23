"""Choices for the profile "look" every account can customize: avatar colour,
avatar icon, avatar frame and profile banner. Plain data with no app imports, so
models, routes and templates can all use it."""

# key -> (label, gradient start, gradient end)
AVATAR_COLORS = {
    'ocean':    ('Ocean',    '#2563eb', '#06b6d4'),
    'sunset':   ('Sunset',   '#f97316', '#ec4899'),
    'forest':   ('Forest',   '#15803d', '#84cc16'),
    'grape':    ('Grape',    '#7c3aed', '#c026d3'),
    'ember':    ('Ember',    '#dc2626', '#f59e0b'),
    'mint':     ('Mint',     '#059669', '#22d3ee'),
    'gold':     ('Gold',     '#b45309', '#facc15'),
    'midnight': ('Midnight', '#1e293b', '#64748b'),
}

# Font Awesome solid icon names (rendered as `fas fa-<name>`).
AVATAR_ICONS = [
    'laptop', 'desktop', 'microchip', 'screwdriver-wrench', 'robot', 'gamepad',
    'headset', 'rocket', 'user-astronaut', 'bolt', 'code', 'cat',
    'dog', 'mug-hot', 'music', 'star',
]

# key -> label. The look of each lives in static/css/profile.css (.pf-banner--<key>).
AVATAR_FRAMES = {
    'none':  'Clean',
    'ring':  'Ring',
    'glow':  'Glow',
    'pulse': 'Pulse',
}

BANNERS = {
    'aurora':    'Aurora',
    'circuit':   'Circuit board',
    'sunset':    'Sunset',
    'ocean':     'Deep sea',
    'nebula':    'Nebula',
    'blueprint': 'Blueprint',
    'matrix':    'Matrix',
    'carbon':    'Carbon',
}

DEFAULT_COLOR = {'customer': 'ocean', 'technician': 'ember', 'admin': 'mint'}
DEFAULT_BANNER = {'customer': 'aurora', 'technician': 'circuit', 'admin': 'matrix'}
DEFAULT_FRAME = 'ring'

DISPLAY_NAME_MAX = 60
HEADLINE_MAX = 120
AVATAR_MAX_BYTES = 3 * 1024 * 1024
AVATAR_MIME = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}


def pick(value, allowed, default):
    """`value` if it is one of `allowed`, else `default`."""
    return value if value in allowed else default
